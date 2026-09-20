# AI Coding Agent

**Build a CLI AI coding agent from scratch — one phase at a time, in plain Python.**

No frameworks. No agent SDK. Just a loop, some tools, and a model — so that by the end you understand exactly how an AI coding agent works, because you built every line of it.

Each phase is a self-contained, runnable folder that adds exactly one capability. Run phase 1 and phase 5 side by side and diff them to see precisely what changed.

---

## What an agent actually is

A language model can only produce text. It cannot read your file, run your tests, or tell you the time. On its own it is a well-read person locked in a room with no phone.

An **agent** is the thin layer that lets it act — and that layer is a loop:

```
   you type a request
          │
          ▼
   send the whole conversation to the model
          │
          ▼
   ╔═══════════════════════╗
   ║ did it ask for a tool?║
   ╚═══╦═══════════════╦═══╝
   NO  ║               ║  YES
  ┌────▼─────┐         ▼
  │ done —   │   ┌──────────────────────────┐
  │ show the │   │ YOUR CODE runs the tool, │
  │ answer   │   │ appends the result       │
  └──────────┘   └────────────┬─────────────┘
                              │
              loop back ──────┘
```

That's about thirty lines of Python, and **it never changes**. Every advanced capability here — file editing, context compression, planning, subagents — is a mechanism bolted *around* that loop, never inside it.

Two things that surprise most engineers, both covered in depth in the phase where they bite:

- **The model is stateless; memory is something you build.** A conversation feels continuous only because you re-send the entire history every call. It's one Python list. → [Phase 1](phase-1-foundation/)
- **The model never executes anything — your code does.** It emits a request; you decide whether to honor it. Every security property lives on your side. → [Phase 2](phase-2-agent-loop/)

## How a request flows, end to end

You type *"read calculator.py and fix the divide-by-zero bug"*. Here is everything that happens, and where each phase plugs in.

**Before you type anything**, startup builds seven objects and one list:

```
  provider   which model, and the only code that knows a vendor exists   [p1]
  skills     scans skills/*/SKILL.md — names and descriptions only       [p5]
  tasks      an empty task board                                         [p6]
  background an empty mailbox                                            [p8]
  team       an empty roster                                             [p9]
  worktrees  a git worktree manager                                     [p11]
  tools      14 tools, each a schema + a handler                      [p2-11]

  system_prompt = base + skill index + AGENTS.md        one string    [p4,p5]
                  ^ a SEPARATE argument on every call, never stored
  messages = []                    <-- THE ONLY MEMORY IN THE SYSTEM      [p1]
```

**Then the turn runs:**

```
  YOU: "read calculator.py and fix the divide-by-zero bug"
       |
       v  cli.py appends {"role": "user", ...} to messages
  +--------------------------------------------------------------+
  |                    ITERATION 1                                |
  |                                                               |
  |  PRE-CALL PIPELINE (runs before every model call)             |
  |    micro_compact      blank tool results older than 3    [p4] |
  |    auto_compact?      summarise if the history is huge   [p4] |
  |    drain mailbox      any finished background work?      [p8] |
  |    task tick          nag if a task has gone stale       [p6] |
  |                        |                                      |
  |                        v                                      |
  |  CALL THE MODEL with three SEPARATE arguments:                |
  |    messages  the conversation                                 |
  |    system    base + skills + AGENTS.md                        |
  |    tools     14 schemas                                       |
  |                        |                                      |
  |                        v                                      |
  |  MODEL: "I want read_file(calculator.py)"                     |
  |         (it only ASKS -- it never executes anything)          |
  |                        |                                      |
  |                        v                                      |
  |  YOUR CODE runs it:                                           |
  |    registry validates the arguments against the schema   [p2] |
  |    safe_path() keeps it inside the workspace             [p3] |
  |    read the file, truncate if huge                       [p3] |
  |                        |                                      |
  |                        v                                      |
  |  append {"role": "tool", "content": "1  def add..."}          |
  +---------------------------- loop back ------------------------+
       |
       v
  ITERATION 2   model now SEES the file -> asks for edit_file
                edit applied (or an error message it can act on)
       |
       v
  ITERATION 3   model replies with PLAIN TEXT, no tool calls
                -> the loop RETURNS. This is the only exit.
```

**The loop exits when the model stops asking for tools** — not when the task is verified correct. Nothing checks the fix.

If the request were bigger, the model would reach for different tools, and each one attaches at the same single seam:

```
  "review this properly"        -> load_skill    body arrives as a tool result   [p5]
  "do this in 5 steps"          -> task          state lives outside messages    [p6]
  "find every caller of X"      -> subagent      a child loop; only the summary
                                                 comes back                      [p7]
  "audit while I keep working"  -> background_run returns instantly; the result
                                                 arrives via the mailbox         [p8]
  "hire two devs, build these"  -> team          named workers who remember   [p9,p10]
  "try two approaches"          -> worktree      a second real directory        [p11]
```

Every one of those is one `register(schema, handler)` call. **The loop never learned any of them exist.**

## Phases

Each folder runs on its own and has its own README with the full walkthrough.

| Phase | Folder | What it adds | Tools |
|-------|--------|--------------|-------|
| **1** | [`phase-1-foundation`](phase-1-foundation/) | CLI REPL, pluggable provider layer, token streaming | 0 |
| **2** | [`phase-2-agent-loop`](phase-2-agent-loop/) | The agent loop, tool registry, bash tool, safety guards | 1 |
| **3** | [`phase-3-file-tools`](phase-3-file-tools/) | File read/write/edit, glob/grep, path sandboxing | 6 |
| **4** | [`phase-4-smart-context`](phase-4-smart-context/) | Three-layer context compression, project instructions file | 7 |
| **5** | [`phase-5-skills`](phase-5-skills/) | Dynamic skill loading | 8 |
| **6** | [`phase-6-planning`](phase-6-planning/) | Task list with dependencies | 9 |
| **7** | [`phase-7-subagents`](phase-7-subagents/) | Subagents with isolated context | 10 |
| **8** | [`phase-8-background`](phase-8-background/) | Delegate without waiting: a thread, a `quiet` flag, a mailbox | 12 |
| **9** | [`phase-9-teams`](phase-9-teams/) | Named workers who remember across tasks | 13 |
| **10** | [`phase-10-autonomous`](phase-10-autonomous/) | Stop assigning — publish a queue, workers pull | 13 |
| **11** | [`phase-11-isolation`](phase-11-isolation/) | Git worktrees: a folder per experiment | 14 |

Plus one side quest, deliberately off the ladder:

| | Folder | What it is |
|---|---|---|
| **Lab** | [`lab-streaming-tool-execution`](lab-streaming-tool-execution/) | A measured benchmark of one production optimization: start running a tool the instant its request finishes streaming, instead of waiting for the model to stop typing. |

Note the tool count goes `0 → 1 → 6 → 7 → 8 → 9 → 10 → 12 → 13 → 13 → 14`. The repeated 13 is not a typo: phase 10 adds no new tool and changes the protocol behind an existing one. **A phase adds a capability, not necessarily a tool.**

Component diagrams and the design of each phase live in [ARCHITECTURE.md](ARCHITECTURE.md).

## How the code is organized

Every phase shares the same skeleton:

```
agent/
├── cli.py         Owns your input, the `messages` list, and slash commands.
├── core/          config · loop · streaming · inspector
├── providers/     The ONLY vendor-aware code. base · registry · ollama
└── tools/         The extension point. registry · bash · safety
```

Two seams make it extensible, and everything else follows:

- **`providers/base.py`** — nothing outside `providers/` knows which model vendor you use. A new one is one subclass.
- **`tools/registry.py`** — a new tool is a schema, a function, and one `register()` call. `loop.py` never changes. Not once, in eleven phases.

## Quick start

**Prerequisites:** Python 3.10+, [Ollama](https://ollama.com) running (`ollama serve`), and a model pulled:

```bash
ollama pull qwen2.5:7b-instruct    # ~4.7 GB
```

Everything runs locally. No API keys, no per-token cost.

Two phases need a little more:

- **Phases 9 and 10 run several agents at once.** Ollama serialises requests per model by default, so they will queue and look hung. Set `OLLAMA_NUM_PARALLEL=2` first — `launchctl setenv OLLAMA_NUM_PARALLEL 2` on macOS (then restart Ollama), or `OLLAMA_NUM_PARALLEL=2 ollama serve`. RAM scales with parallelism × context length.
- **Phase 11 needs a git repository with at least one commit** in the directory you run it from.

```bash
cd phase-2-agent-loop
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m agent.cli
```

Phases are namespace packages with no `__init__.py`, so run them from the phase directory, or set `PYTHONPATH` to it. Note that the agent sandboxes file operations to the directory you launch from — run it in a scratch folder if you don't want it writing into this repo.

Then ask it `what is the time now?` and watch it choose a shell command nobody hardcoded. Type `/inspect` to see every call made to the model — the tool call and its result sitting between two model calls. That's the loop, made visible, and it's the most useful thing here for understanding what's going on.

## Commands

```
/help    /clear    /model    /inspect    /clear-inspect    /quit
```

## Using a different model

The model is set in `agent/core/config.py`; any Ollama model with tool-calling support works. For a hosted provider, write one `BaseProvider` subclass and return it from `providers/registry.py` — that's the whole change.

## A note on safety

This agent runs shell commands on your machine. The guards in `tools/safety.py` are a **blocklist**, which is a speed bump rather than a sandbox — it enumerates bad strings, and there's always one more phrasing it hasn't seen. Real containment restricts what a process can *reach*, not what its command *looks like*. Later phases move that way with path sandboxing.

Until then: run it on code you can afford to lose, and read what it proposes before letting it run.

## License

MIT
