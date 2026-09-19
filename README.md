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
| **8** | *planned* | Non-blocking background subagents | 12 |
| **9** | *planned* | Named teammates with memory across tasks | 13 |
| **10** | *planned* | Teammates pulling from a shared queue | 13 |
| **11** | *planned* | Git worktree isolation per experiment | 14 |

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

```bash
cd phase-2-agent-loop
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m agent.cli
```

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
