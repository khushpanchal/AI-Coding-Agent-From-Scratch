# Phase 4 — Smart Context

**Project instructions that load themselves, and three layers of context compression.**

This phase solves two problems that have been quietly accumulating since phase 1.

**Problem one: you keep repeating yourself.** Every session you re-explain the same conventions — use logging not print, snake_case, this test runner. It works, and it's tedious, and you pay for those tokens every time you type them.

**Problem two: the conversation grows forever.** Remember from phase 1 that the model is stateless, so the *entire* history is re-sent on every call. Add phase 3's file tools and a single `read_file` on a big file parks thousands of tokens in the conversation permanently — re-sent on every turn after that, forever.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## Part 1 — `AGENTS.md`

Write your project's rules in a file. The agent reads it at startup and prepends it to the system prompt.

```
 SESSION START
 ┌────────────────────────────────────────────────────────┐
 │ memory/agents_md.py                                    │
 │   walk up: ./AGENTS.md, ../AGENTS.md, … up to /        │
 │   then   : ~/.agent/AGENTS.md                          │
 │   concatenate, nearest first, each with a header       │
 └───────────────────────┬────────────────────────────────┘
                         │
                         ▼
        system_prompt = SYSTEM_PROMPT + "\n\n" + agents_md
                         │
                         ▼
        ┌────────────────────────────────────────┐
        │ a plain string — NOT in `messages`     │
        │ the provider re-injects it on EVERY    │
        │ call, exactly as in phase 1            │
        └────────────────────────────────────────┘
```

Three scopes are searched: your project directory, every parent directory up to the filesystem root, and a user-global `~/.agent/AGENTS.md`. All of them apply, concatenated nearest-first.

**Nearest-first is a convention, not a rule.** Nothing resolves contradictions between two files. If a parent directory says "use tabs" and your project says "use spaces," the model decides based on ordering and wording. Hard precedence is something you would have to build.

Because it lives in the system prompt and not in `messages`, two things follow:

- **`/clear` does not erase your project rules.** This is exactly why phase 1 kept the system prompt out of the message list.
- **There is no file watcher.** Edit `AGENTS.md` and you must restart the agent. Deliberate simplicity, but worth knowing before you wonder why your change did nothing.

## Part 2 — three layers of compression

The layers are best understood as a **hierarchy of cost**:

```
┌──────────┬────────────────────────┬──────────────┬────────────────────────────┐
│ Layer    │ When it fires          │ Costs a      │ What it does               │
│          │                        │ model call?  │                            │
├──────────┼────────────────────────┼──────────────┼────────────────────────────┤
│ 1 Micro  │ every single iteration │ NO — free    │ all but the last 3 tool    │
│          │                        │ string swap  │ results → a placeholder    │
├──────────┼────────────────────────┼──────────────┼────────────────────────────┤
│ 2 Auto   │ estimated tokens pass  │ YES, one     │ whole history → a summary  │
│          │ the threshold          │              │ + an acknowledgement       │
├──────────┼────────────────────────┼──────────────┼────────────────────────────┤
│ 3 Manual │ you type /compact, or  │ YES, one     │ identical to Layer 2,      │
│          │ the model calls the    │ (same code)  │ on demand                  │
│          │ `compact` tool         │              │                            │
└──────────┴────────────────────────┴──────────────┴────────────────────────────┘
```

Layers 2 and 3 are literally the same function — three triggers, one code path.

### The loop changed, barely

For the first time since phase 2, `core/loop.py` is modified. The entire change is five lines at the top of each iteration:

```python
for i in range(max_iterations):
    micro_compact(messages)                          # Layer 1 — free

    if should_auto_compact(messages):                # Layer 2 — costs a call
        messages[:] = auto_compact(messages, provider)

    ... everything below is untouched ...
```

The loop's *shape* is still exactly what it was in phase 2: call the model, dispatch tools, append results, repeat. What phase 4 adds is a **pre-call pipeline slot** — a place where per-turn mechanisms can run before the model is invoked. That slot is the pattern later phases reuse.

### Layer 1: free compression

Tool results are the fattest thing in the conversation and the least useful once acted upon. So every iteration, `micro_compact` finds all `role: "tool"` messages, keeps the most recent three intact, and overwrites the rest:

```
BEFORE                              AFTER
──────                              ─────
user:      "list the files"         user:      "list the files"
assistant: [calls list_files]       assistant: [calls list_files]      ← kept
tool:      <4KB of file names>      tool:      "[Previous tool result
                                                 — see context above]"  ← replaced
```

**No model call. Just string replacement.** That's what makes it affordable to run on every single turn.

Notice what survives: the assistant's *tool call* stays, only the *result* is dropped. Intent is small and permanent; output is large and re-derivable. The model still knows it ran `list_files` — and if it needs the answer again, it can just run it again. Which, as it happens, is more correct anyway, since a cached file listing goes stale the moment someone adds a file.

The tradeoff is real and irreversible: that content is **gone**, not stored elsewhere. There is no retrieval path.

### Layer 2: expensive compression

When the conversation crosses the threshold, the agent asks the model to summarise the whole history, then replaces it with exactly two messages: a summary and an acknowledgement. (Two, rather than one, to preserve user/assistant alternation — some models require it.)

If summarisation fails, a canned fallback sentence is used. **Compaction failing must never kill the session.**

This is lossy in a way worth stating plainly: a summary is the *model's* judgement about what mattered. It may drop the sentence you cared about most. That's not a bug to fix, it's the nature of the technique.

### Estimating tokens without a tokenizer

```python
len(json.dumps(messages)) // 4
```

Four characters per token, roughly. That's why `/tokens` says **estimated**.

A real tokenizer would be more accurate and would drag a model-specific dependency into a provider-agnostic module. This number only decides *when a threshold trips* — being off by 20% just moves the trigger point slightly. Cheap and approximately right beats precise and coupled.

### The 7th tool: the agent compacts itself

`compact` is registered as a normal tool, so the model can decide on its own that the context is getting heavy and clean it up.

The implementation is the interesting part — the handler is a **closure over the agent's own message list**:

```python
def setup_tools(provider, messages_ref):
    def handle_compact():
        new = manual_compact(messages_ref, provider)
        messages_ref.clear()
        messages_ref.extend(new)
    registry.register(COMPACT_SCHEMA, handle_compact)
```

Two details that matter:

**Why `setup_tools` now takes arguments.** In phase 3 it took none. A tool that edits the agent's own memory needs a handle on that memory, and the registry only passes model-supplied JSON arguments — so the reference has to be captured at registration time. This is also why `setup_tools()` is now called *after* `messages` exists.

**Why `.clear()` and `.extend()` instead of `messages_ref = new`.** Rebinding the parameter name would just point a local variable at a new list and leave the REPL's actual list untouched. The agent would compact a list nobody reads. The same discipline appears in the loop as `messages[:] = auto_compact(...)`.

## Two sharp edges worth knowing

**Auto-compaction can swallow the turn's own prompt.** Layer 2 fires at the *top* of an iteration — after your message is already in `messages`. If it triggers on that turn, your brand-new prompt gets summarised into the blob along with everything else.

**The threshold won't trigger on a small local model.** It's set to 100,000 tokens, which is more than `qwen2.5:7b-instruct` can use. In practice only `/compact` and the `compact` tool exercise that path here. The number is arbitrary — lower it if you want to watch Layer 2 fire.

## Run it

```bash
mkdir -p /tmp/agent-demo4 && cd /tmp/agent-demo4
printf '# Project rules\n\n- Always use snake_case for function names.\n- Use logging, not print.\n' > AGENTS.md
PYTHONPATH=/path/to/phase-4-smart-context \
  /path/to/phase-4-smart-context/venv/bin/python -m agent.cli
```

### Try this

| Type this | What you should see |
|---|---|
| *(at startup)* | `Loaded AGENTS.md project instructions.` |
| `write a python function that logs a message` | it uses `logging` and `snake_case` — **rules you never typed this session** |
| `/tokens` | `Estimated tokens: ~210` |
| `/debug` | 4 rows: `user / assistant / tool / assistant` |
| `/compact` | `Context compressed.` (pauses — this one calls the model) |
| `/debug` again | **2 rows**: the summary and the acknowledgement |
| `/tokens` again | a smaller number |
| `/inspect` | the system message now contains your `AGENTS.md` — proof it's injected on *every* call |
| edit `AGENTS.md`, ask again | no change until you restart — no file watcher |

**To watch Layer 1 work:** run four or more tool calls (`list all files`, `read X`, `search for def`, `list all py files`), then `/debug`. The oldest tool rows will read `[Previous tool result — see context above]` while the last three keep their content.

## New commands

```
/compact   Compress the conversation now (calls the model)
/tokens    Show the estimated token count
/debug     Show the message list — roles and first 80 characters
```

## What's missing

`AGENTS.md` has the same problem it solved: it grows. Every rule you add costs tokens on every call, forever, whether or not it's relevant to what you're doing right now. [Phase 5](../phase-5-skills/) splits that into two layers — always-loaded names, on-demand bodies — which is what skills are.
