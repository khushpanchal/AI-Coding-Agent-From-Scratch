# Phase 3 — File Tools

**Five file tools with a real sandbox. The agent gets a scalpel instead of a hammer.**

Phase 2 gave the agent `bash`, which can technically already do file work — `cat` a file, `sed` an edit. So why add dedicated file tools at all? That question is the whole design rationale for this phase, and the answer is more interesting than "it's tidier."

> New here? Start with the [project README](../README.md), then [phase 1](../phase-1-foundation/) and [phase 2](../phase-2-agent-loop/).

## Why not just use bash?

Four reasons, each a real engineering constraint:

**Precision without loading everything.** "Read lines 3 through 8 of this file" is awkward through a shell, and `cat` drags the entire file into the context window — which you pay for on every subsequent turn. `read_file` takes `offset` and `limit` and returns exactly those lines.

**A system API instead of a subprocess.** These tools call Python's file APIs directly. No shell parsing, no quoting hazards, no escaping bugs when a filename contains a space or a quote.

**Concurrency you can control.** Once later phases run several subagents in parallel against the same files, shell redirection gives you no way to coordinate. A function call does.

**Safety you can actually enforce** — the big one, below.

```
   bash                          file tools
   ────                          ──────────
   spawn a shell                 call a Python API
   string in, string out         typed arguments
   whole file or clumsy sed      offset/limit slices
   goes anywhere on disk         confined to the workspace
   blocklist (leaky)             path containment (not leaky)
```

## What this phase adds

```
                    ┌──────────────────────────────────────┐
  your prompt  ───► │ cli.py — registers 6 tools now       │
                    └──────────────────┬───────────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
                    │ core/loop.py    ★ UNCHANGED ★        │
                    │ call model → dispatch → append → ... │
                    └──────────────────┬───────────────────┘
                                       ▼
                    ┌──────────────────────────────────────┐
                    │ tools/registry.py                    │
                    │ name → (schema, handler)             │
                    └──────┬────────────────────────┬──────┘
                           ▼                        ▼
              ┌────────────────────┐   ┌─────────────────────────────┐
              │ tools/bash.py      │   │ tools/files.py    ★ NEW ★   │
              │ blunt instrument   │   │ read_file    offset/limit   │
              └─────────┬──────────┘   │ write_file   creates dirs   │
                        │              │ edit_file    exact match    │
                        │              │ list_files   glob           │
                        │              │ search_files regex          │
                        │              └──────────────┬──────────────┘
                        │                             │ every path
                        ▼                             ▼ goes through
              ┌───────────────────────────────────────────────────────┐
              │ tools/safety.py                                       │
              │  is_dangerous_command()  ← bash only    (blocklist)   │
              │  truncate_output()       ← both         (50K cap)     │
              │  safe_path()   ★ NEW ★   ← file tools   (containment) │
              └───────────────────────────────────────────────────────┘
```

**The headline fact: `core/loop.py` is byte-identical to phase 2.** So are all the provider files, `streaming.py`, `inspector.py`, `config.py`, and `bash.py`. Adding five capabilities touched `cli.py` (imports, system prompt, five `register()` calls) and `safety.py`. Nothing else.

That's the tool registry seam doing its job. The loop asks *"did the model request any tools?"* — it never learns what the tools are.

## The idea that matters: sandboxing lives in code, not in the prompt

You can write "only touch files inside the project" in your system prompt. The model will usually comply. *Usually* is not a security boundary — and if the agent is running in a folder near something that matters, "usually" is how databases get deleted.

`safe_path()` in `tools/safety.py` makes it impossible instead:

```python
resolved = (WORKSPACE / file_path).resolve()
if not resolved.is_relative_to(WORKSPACE):
    raise ValueError(...)
```

**The order is the whole trick.** `.resolve()` runs *first* — collapsing `..` segments and following symlinks — and only then is the result compared against the workspace root. Checking the string before resolving it is the classic path-traversal bug: `safe/../../../etc/passwd` looks like it starts with `safe/`.

`WORKSPACE` is frozen at import from `os.getcwd()`, so the sandbox is **wherever you launched the agent**. Run it from your home directory and you have sandboxed the agent to your home directory.

### An honest limitation

**`bash` does not call `safe_path`.** File tools are contained; the shell is only blocklisted. The agent can still `cat /etc/passwd` through bash.

These are two controls with genuinely different strength:

| | Mechanism | Guarantee |
|---|---|---|
| `is_dangerous_command` | matches strings against a blocklist | leaky by construction — there's always another phrasing |
| `safe_path` | computes the real path and compares | not leaky, for what it covers |

Worth understanding the difference, because it's the difference between enumerating badness and containing it.

## The five tools

| Tool | Required args | Notes |
|------|---------------|-------|
| `read_file` | `path` | Optional `offset`/`limit`. Returns line-numbered content. |
| `write_file` | `path`, `content` | Creates parent directories. |
| `edit_file` | `path`, `old_string`, `new_string` | Match must be **unique**. |
| `list_files` | `pattern` | Glob, e.g. `**/*.py`. |
| `search_files` | `pattern` | Regex across file contents, like grep. |

**Why five tools and not one `file_op` tool?** Because they need different arguments. A single union tool would have to make every field optional, and then validating "edit needs `old_string`" becomes the handler's job — which is exactly the validation the registry already does for free from the schema.

### `edit_file` refuses ambiguity on purpose

If the search text appears zero times, or more than once, the edit is rejected with a message like *"Provide more surrounding context to make it unique."*

That string is not for you. It goes back into the conversation as a tool result, which means **the error message is the model's next prompt.** Phrasing it as an instruction — naming the next action rather than just stating "ambiguous" — is what lets the model recover on its own. Same self-correcting contract the registry established in phase 2.

## Schemas: the description *is* the API

The model never sees your Python. It sees the schema. The name is nearly cosmetic — rename `write_file` to `wf` and everything still works — but delete the description and the model stops reaching for the tool correctly.

Note that descriptions carry *behavioural* instructions, not just types:

> "Use this to understand existing code before modifying it."

That's a policy smuggled into a type declaration, and it's how you steer tool selection.

## Run it

`WORKSPACE` is your current directory, so run the agent from a scratch folder — not from this repo — unless you want it writing here.

```bash
mkdir -p /tmp/agent-demo && cd /tmp/agent-demo
PYTHONPATH=/path/to/phase-3-file-tools \
  /path/to/phase-3-file-tools/venv/bin/python -m agent.cli
```

### Try this

| Type this | What you should see |
|---|---|
| `create calculator.py with add and divide functions, handle divide by zero` | `[tool: write_file]`, then a real file on disk |
| `read lines 3 to 6 of calculator.py` | `[tool: read_file]` with `offset=3, limit=4` — it did **not** read the whole file |
| `list all python files` | `[tool: list_files]` with `pattern=**/*.py` |
| `search for "def " in python files` | `calculator.py:3: def add(x, y):` |
| `read ../../../../etc/passwd` | **the sandbox demo** — `Error: Path ... resolves outside the workspace` |

That last one is the phase in one line. The model genuinely tried; the code said no.

## What's missing

Two pressures are building. Every session starts by re-explaining your project conventions — "use logging, not print" — and every tool result stays in the conversation forever, growing the context you pay for on every single turn. [Phase 4](../phase-4-smart-context/) addresses both.
