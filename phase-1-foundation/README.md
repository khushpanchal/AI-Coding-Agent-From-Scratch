# Phase 1 — Foundation

**A streaming chat REPL with a pluggable model provider. No tools yet.**

This phase deliberately builds an agent that cannot *do* anything. That sounds like a strange place to start, but it isolates the one concept everything else depends on — how a stateless model appears to remember a conversation — before tools arrive and complicate the picture.

> New here? Read the [project README](../README.md) first for what an agent is and why the loop matters.

## What this phase builds

```
┌──────────────────────────────────────────────────────────┐
│ cli.py          OWNS THE TURN AND THE MEMORY             │
│                 while True: read input                   │
│                 slash command? handle locally, continue  │
│                 otherwise: append to `messages`, send    │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│ providers/registry.py    FACTORY                         │
│                          config dict → provider instance │
│                          imports the SDK lazily, so you  │
│                          only pay for the one you use    │
└──────────────────┬───────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│ providers/base.py        THE CONTRACT (abstract)         │
│                          chat · chat_stream · name       │
│                          defines the message format and  │
│                          the streaming event protocol    │
└──────────────────┬───────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│ providers/ollama.py      TRANSLATOR                      │
│                          the only vendor-aware file      │
│                          our dicts → vendor payload      │
│                          yields text / tool_call / done  │
└─────┬────────────────────────────────────┬───────────────┘
      │ events                             │ records the call
      ▼                                    ▼
┌───────────────────────┐      ┌──────────────────────────┐
│ core/streaming.py     │      │ core/inspector.py        │
│ prints tokens live,   │      │ taps the WIRE, so        │
│ returns the assembled │      │ /inspect shows what was  │
│ response at the end   │      │ actually sent            │
└───────────────────────┘      └──────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `agent/cli.py` | The REPL. Owns the conversation list, handles slash commands, streams replies. |
| `agent/core/config.py` | Which model and which host. Eleven lines. |
| `agent/core/streaming.py` | Consumes the provider's event stream, prints text as it arrives, returns the final response. |
| `agent/core/inspector.py` | Records every model call for `/inspect`. |
| `agent/providers/base.py` | Abstract interface every provider implements. |
| `agent/providers/registry.py` | Factory that turns config into a provider instance. |
| `agent/providers/ollama.py` | Ollama implementation — the only file that knows a vendor exists. |

## The idea that matters: memory is a list

Look at `agent/cli.py` line 53:

```python
messages: list[dict] = []
```

That list is the entire memory of the agent. There is no database, no server-side session, no state hidden inside the model.

The model is **stateless**. Every call is a fresh request to a server that remembers nothing. Continuity is an illusion produced by re-sending the whole conversation every time:

```
turn 1 sends:  [user: "remember 42"]
turn 2 sends:  [user: "remember 42", assistant: "ok", user: "what number?"]
turn 3 sends:  [user: "remember 42", assistant: "ok", user: "what number?",
                assistant: "42", user: "and what's 2+2?"]
                └──────────── the whole thing, every single time ────────────┘
```

`/clear` is one line — `messages.clear()` — and it causes complete amnesia, because deleting that list *is* deleting the memory.

Two consequences worth carrying into later phases:

- The conversation grows without bound, and you re-send all of it on every turn. That is a cost curve, and it is why context compression eventually becomes necessary.
- Whoever owns that list controls the agent's memory. Here it is the CLI, and it stays that way even once a loop takes over the turn.

## One design detail worth noticing

The system prompt is **not** stored in `messages`. The provider prepends it fresh on every call (`providers/ollama.py`, `_inject_system`).

That is not a stylistic choice. `/clear` wipes `messages` — if the system prompt lived at `messages[0]`, clearing the conversation would also erase the agent's instructions. Identity and history have different lifetimes, so they live in different places.

## Run it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m agent.cli
```

You should see a banner, `Provider: Ollama (qwen2.5:7b-instruct)`, and a green `>` prompt. Type anything and watch the reply stream in token by token.

### Try this — it proves the whole section above

```
> remember the number 42
> what did I ask you to remember?          ← it answers 42
> /inspect                                  ← see the actual payload sent
> /clear
> what did I ask you to remember?          ← it has no idea
```

At the last step, nothing changed about the model or the server. You deleted a Python list in your own process, and that was enough to erase its memory.

The `/inspect` output is worth studying: the system message comes first, then your turns stacked in order. Nothing is hidden, and nothing is stored anywhere else.

## Commands

```
/help           Show available commands
/clear          Clear conversation history
/model          Show the current provider and model
/inspect        Show every model call's input and output
/clear-inspect  Clear inspector records (independent of /clear)
/quit           Exit
```

## What's missing

The model can talk and nothing else. It cannot read a file, run a command, or look anything up — because there is no loop and no tools. [Phase 2](../phase-2-agent-loop/) adds both, and it turns out to take about thirty lines.
