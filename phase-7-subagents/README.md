# Phase 7 — Subagents

**Spawn a child agent with its own context, let it work, keep only the answer.**

This is the first phase where the agent creates another agent. It sounds like the biggest architectural leap in the project. The loop file doesn't change by a single byte.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## The problem: exploration is expensive and mostly noise

Ask "which files call this API?" and the agent runs `search_files`, reads six files, greps again, reads three more. Every one of those results lands in `messages` and is re-sent on every subsequent call.

You wanted one sentence. You paid for fifteen tool results and you're still carrying them.

Phase 4's compression helps eventually, but it's cleanup after the fact — the tokens were already spent, and the useful conclusion is now buried among the debris that produced it.

**What you actually want is to throw away the trajectory and keep the conclusion.**

## The design: three things swapped, one engine reused

```
  ┌─────────────────────────── PARENT AGENT ────────────────────────────┐
  │ messages = [ ...long history... ]        tools = 10                 │
  │                                                                     │
  │   model emits tool_call: subagent(prompt=..., agent_type="explore") │
  │                    │                                                │
  │                    ▼                                                │
  │   ToolRegistry.dispatch("subagent", args)                           │
  │                    │                                                │
  │                    ▼   handle_subagent — a CLOSURE over `provider`  │
  └────────────────────┼────────────────────────────────────────────────┘
                       ▼
  ┌──────────────────── run_subagent() ────────────────────────────────┐
  │                                                                    │
  │   messages = [{"role": "user", "content": prompt}]  ← FRESH, len 1 │
  │   tools    = _make_subagent_tools(agent_type)       ← DIFFERENT SET│
  │   system   = "You are a focused subagent..."        ← DIFFERENT    │
  │                                                                    │
  │   ┌──────────── THE SAME agent_loop FUNCTION ──────────────┐      │
  │   │ max_iterations = 30   (parent uses 50)                 │      │
  │   │ no task_manager ⇒ no nag (the parameter defaults None) │      │
  │   │ child runs N tool calls; all N results accumulate      │      │
  │   │ in the CHILD's message list                            │      │
  │   └────────────────────────────────────────────────────────┘      │
  │                                                                    │
  │   walk reversed(messages), take the last assistant TEXT  ← FILTER  │
  │   every tool call and every tool result is DISCARDED               │
  │   return that one string                                           │
  └────────────────────┬───────────────────────────────────────────────┘
                       ▼
  parent appends exactly ONE message:  {"role": "tool", "content": summary}
```

Three orthogonal things are swapped at the call site, and nothing else:

| Swapped | Gives you |
|---|---|
| `messages` — a fresh one-item list | **context isolation** |
| `tools` — a different registry | **privilege control** |
| `system` — a different prompt | **role** |

The engine is the same function. `core/loop.py` is byte-identical to phase 6.

## Why the loop needed no changes

Think about what the loop actually does: call a model, dispatch tools, append results, repeat. It takes `provider`, `messages`, `tools`, `system` as **parameters**. It holds no global state and reaches for nothing outside its arguments.

A function like that is *already* re-entrant. Calling it from inside a tool handler is just... calling a function.

```
  agent_loop (parent)
      └─► dispatch("subagent")
              └─► run_subagent()
                      └─► agent_loop (child)    ← same function, different arguments
```

This is the payoff for a decision made back in phase 2 — keeping the loop parameterised instead of reaching for module state. Recursion came for free, five phases later. **Good interfaces buy you capabilities you didn't design for.**

## Tool sets are the privilege boundary

```
  explore  → 4 tools:  bash, read_file, list_files, search_files
  general  → 6 tools:  the above + write_file, edit_file
```

An `explore` subagent **cannot write files**. Not because it's told not to — because `write_file` was never registered in its registry. The model can't call a tool it was never given.

This is the same principle as phase 3's `safe_path`: a capability the code doesn't offer is stronger than an instruction the model is asked to follow. Here it's applied to tools rather than paths.

Note the gap that remains, consistent with earlier phases: `explore` still has `bash`, and `bash` can write files. The privilege boundary is real but not airtight, for the same reason the workspace sandbox isn't.

## The summary filter is where the savings come from

After the child finishes, `run_subagent` walks its messages backwards and returns the **last assistant text**. Everything else is dropped on the floor.

```
  CHILD did:                            PARENT receives:
  ──────────                            ───────────────
  user:      "list and summarise"
  assistant: [calls list_files]
  tool:      <directory listing>   ──►  tool: "The directory contains a single
  assistant: [calls read_file]                 Python file, calculator.py, which
  tool:      <full file contents>              defines add, divide and run..."
  assistant: "The directory contains…"
  └── 6 messages, thousands of tokens ──┘   └── 1 message, ~40 tokens ──┘
```

Verified by running it: the parent's history afterwards is **4 messages**, and the child's two tool calls and two tool results are nowhere in it.

The child's system prompt works hard to make that summary useful — it explicitly forbids tool-call syntax, verbatim file contents, byte counts, and step-by-step replays, and asks for 1–3 sentences about *what was accomplished*. The compression here isn't an algorithm; it's a prompt.

## What you're actually trading

Be clear-eyed about this: **subagents do not save tokens overall.** The child's conversation costs real tokens — often more than doing the work inline, since it re-reads context the parent already had.

What you save is **parent context**, which is the scarce resource. You're moving spend from a budget that persists for the whole session into one that's discarded immediately.

Three phases, three ways of spending the same budget:

| Phase | What gets deferred or discarded | What it costs |
|---|---|---|
| 5 skills | the knowledge *body* | one extra round-trip when needed |
| 6 planning | the plan *state* (moved outside `messages`) | a tool schema + periodic nag |
| 7 subagents | the entire child *trajectory* | a whole extra conversation |

## Run it

```bash
mkdir -p /tmp/agent-demo7 && cd /tmp/agent-demo7
PYTHONPATH=/path/to/phase-7-subagents \
  /path/to/phase-7-subagents/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `use a subagent with agent_type explore to list the files here and summarise them` | nested tool output — the child's calls appear, indented |
| `/debug` | **the payoff**: ~4 messages. The child's tool calls and results are absent |
| `use a general subagent to create utils.py with a square function` | the child writes a real file |
| ask an `explore` subagent to write a file | it can't — `write_file` isn't in its registry |

The `/debug` row is the phase. Watch a dozen operations happen, then look at the parent's memory and find almost nothing there.

## What's missing

The parent **blocks** while the child works. Delegate three investigations and they run one after another, with you watching a frozen prompt. The child loop is already isolated and self-contained — the only thing standing between this and real concurrency is whether the parent waits. That, and giving a child a name it keeps between tasks, is where the next phases go.
