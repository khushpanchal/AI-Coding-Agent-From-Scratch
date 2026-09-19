# AI Coding Agent

**Build a CLI AI coding agent from scratch — one phase at a time, in plain Python.**

No frameworks. No LangChain, no agent SDK. Just a loop, some tools, and a model — so that by the end you understand exactly how an AI coding agent works, because you built every line of it.

Each phase is a self-contained, runnable folder. Each one adds exactly one capability while keeping everything from the previous phases working, so you can run phase 1 and phase 5 side by side and diff them to see precisely what changed.

---

## Start here: what is an agent, really?

A large language model can only do one thing: **produce text.** It cannot read your file, run your tests, or tell you what time it is. On its own it is a very well-read person locked in a room with no phone and no windows.

An **agent** is the thin layer that lets that model act on the world. And the surprising part — the thing worth internalizing before you read any code — is how thin that layer actually is:

```
       ┌──────────────────────────────────────────────┐
       │  you type a request                          │
       └───────────────────┬──────────────────────────┘
                           ▼
       ┌──────────────────────────────────────────────┐
       │  send the whole conversation to the model    │
       └───────────────────┬──────────────────────────┘
                           ▼
                  ╔════════════════════╗
                  ║ did it ask to use  ║
                  ║ a tool?            ║
                  ╚═══╦════════════╦═══╝
                 NO   ║            ║   YES
            ┌─────────▼──┐         ▼
            │  done —    │   ┌─────────────────────────┐
            │  show the  │   │ YOUR CODE runs the tool │
            │  answer    │   │ append the result to    │
            └────────────┘   │ the conversation        │
                             └───────────┬─────────────┘
                                         │
                      loop back ─────────┘
```

That is the agent loop. It is about thirty lines of Python, and it does not change. Every advanced capability in this project — file editing, context compression, planning, subagents, parallel teammates — is a mechanism bolted *around* that loop, never inside it.

If you take one idea from this repository, take that one.

## Two ideas that surprise most engineers

**1. The model is stateless. Memory is something you build.**

There is no session on the server. The model remembers nothing between calls. A conversation feels continuous only because the client re-sends the *entire* history on every single request. In this codebase that history is one Python list:

```python
messages: list[dict] = []
```

Clearing that list is amnesia. There is nothing else to erase. This also explains a cost you will feel later: the list grows forever, and you pay for every token of it on every turn — which is exactly why context compression becomes necessary rather than optional.

**2. The model never executes anything. Your code does.**

This is the most misunderstood part of agent design. When a model "uses a tool," it does not run anything. It emits a structured request — *"I would like to run: `date`"* — and hands it back to you. Your code decides whether to honor it.

```
   MODEL                        YOUR CODE
   ─────                        ─────────
   "run: date"      ─────►      validate the arguments
                                check it against safety rules
                                actually execute it     ← the real world is touched here
                                truncate the output
                    ◄─────      hand back a plain string
   turn that result
   into a sentence
```

Every security property an agent has lives on the right-hand side of that diagram. The model is a planner; your code is the one holding the knife.

## Why one generic tool beats ten specific ones

Give the agent a single `bash` tool and ask it *"what time is it?"* — it will answer correctly, having decided on its own to run `date`. Nobody wrote code for that.

The model has read an enormous amount of technical material; it already knows shell commands, `git`, `grep`, package managers. You are not teaching it *what* to run. You are giving it a way to *run* things at all. That is where the leverage comes from, and it is why this project starts with one broad tool instead of a catalogue of narrow ones.

---

## Phases

Each phase is a folder you can run on its own.

| Phase | Folder | What it adds | Tools |
|-------|--------|--------------|-------|
| **1** | `phase-1-foundation` | CLI REPL, pluggable provider layer, token streaming | 0 |
| **2** | `phase-2-agent-loop` | The agent loop, tool registry, bash tool, safety guards | 1 |
| **3** | *planned* | File read/write/edit, glob/grep, path sandboxing | 6 |
| **4** | *planned* | Three-layer context compression, project instructions file | 7 |
| **5** | *planned* | Dynamic skill loading | 8 |
| **6** | *planned* | Task list with dependencies | 9 |
| **7** | *planned* | Subagents with isolated context | 10 |
| **8** | *planned* | Non-blocking background subagents | 12 |
| **9** | *planned* | Named teammates with memory across tasks | 13 |
| **10** | *planned* | Teammates pulling from a shared queue | 13 |
| **11** | *planned* | Git worktree isolation per experiment | 14 |

See [ARCHITECTURE.md](ARCHITECTURE.md) for the component diagrams and the full design of each phase.

## How the code is organized

Every phase shares the same skeleton, which is worth learning once:

```
agent/
├── cli.py            THE TURN OWNER
│                     Reads your input, owns the `messages` list,
│                     handles slash commands, hands work to the loop.
│
├── core/
│   ├── config.py     Which model, which host.
│   ├── loop.py       THE AGENT LOOP (from phase 2 on).
│   │                 Call model → run tools → append → repeat.
│   ├── streaming.py  Prints tokens as they arrive; returns the
│   │                 assembled response at the end.
│   └── inspector.py  X-RAY. Records the exact payload sent on the
│                     wire, so `/inspect` shows truth, not intention.
│
├── providers/        THE ONLY VENDOR-AWARE CODE
│   ├── base.py       The contract: chat, chat_stream, name.
│   ├── registry.py   Factory — config in, provider instance out.
│   └── ollama.py     One implementation. Translates our format
│                     to the vendor's and back.
│
└── tools/            THE EXTENSION POINT (from phase 2 on)
    ├── registry.py   register(schema, handler) + dispatch by name.
    ├── bash.py       A tool = a schema the model reads + a
    │                 function your code runs.
    └── safety.py     Guards applied before execution.
```

Two seams make this extensible, and everything else follows from them:

- **`providers/base.py` is the vendor seam.** Nothing outside `providers/` knows which model company you are using. Supporting a new one means writing one subclass — no caller changes, because no caller ever knew.
- **`tools/registry.py` is the capability seam.** A new tool is a schema plus a function plus one `register()` call. `loop.py` never changes. Not once, in eleven phases.

## Quick start

**Prerequisites**

- Python 3.10+
- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- A model pulled: `ollama pull qwen2.5:7b-instruct` (about 4.7 GB)

Everything runs locally. No API keys, no accounts, no per-token cost.

**Run a phase**

```bash
cd phase-2-agent-loop
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m agent.cli
```

Then try:

```
> what is the time now?
```

You will see a `[tool: bash] command=date` line — the model choosing a command nobody hardcoded — followed by a sentence written from its output.

**Then type `/inspect`.** This is the single most useful thing in the project for understanding what is happening. It shows every call made to the model, with the exact messages sent and received, including the tool call and the tool result sitting between two model calls. The loop becomes visible.

## Commands

```
/help           Show available commands
/clear          Clear conversation history
/model          Show the current provider and model
/inspect        Show every model call's input and output
/clear-inspect  Clear inspector records (independent of /clear)
/quit           Exit
```

## Swapping in a different model

The model is set in `agent/core/config.py`. Any Ollama model that supports tool calling will work:

```bash
ollama pull llama3.1:8b
```

To use a hosted provider instead, write one subclass of `BaseProvider` in `agent/providers/` and return it from `registry.py`. That is the entire change.

## A note on safety

This agent runs shell commands on your machine. The guards in `tools/safety.py` are a **command blocklist**, and a blocklist is a speed bump, not a sandbox — it enumerates known-bad strings, and there is always one more phrasing it has not seen. Real containment restricts what a process can *reach* (allowed paths, a container, an unprivileged user), not what its command *looks like*.

Later phases move in that direction with path sandboxing. Until then, run this on code you can afford to lose, and read what it proposes before you let it run.

## License

MIT
