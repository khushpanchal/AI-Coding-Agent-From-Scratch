# Phase 2 — The Agent Loop

**The while-loop that turns a chatbot into an agent, plus one tool to prove it.**

Phase 1 was a chatbot: send a message, get a reply, done. This phase adds the loop — if the model asks to use a tool, your code runs it, feeds the result back, and asks again. That single change is the difference between a model that talks and an agent that acts.

> New here? Read the [project README](../README.md) first, then [phase 1](../phase-1-foundation/).

## What changed from phase 1

```
   phase 1                          phase 2
   ───────                          ───────
   cli.py → chat()                  cli.py → agent_loop()      delegates the turn
     one call, one reply              loops until no tool calls

                                   + core/loop.py       NEW — the loop itself
                                   + tools/registry.py  NEW — register & dispatch
                                   + tools/bash.py      NEW — one tool
                                   + tools/safety.py    NEW — guards
```

Everything else is **byte-identical** to phase 1: all three provider files, `streaming.py`, `inspector.py`, `config.py`. Adding a whole new capability touched exactly one existing file, and that is the point — the seams were placed correctly in phase 1.

`streaming.py` is the neat example. Since phase 1 it has carried a branch for tool-call events that did nothing at all:

```python
elif event["type"] == "tool_call":
    pass
```

It is load-bearing now, and nobody had to edit it.

## The loop

The whole thing lives in `agent/core/loop.py`, and it is about thirty lines.

```
        the user's message is already in `messages`
                     │
                     ▼
    ╔═══════════ for i in range(50) ════════════════════╗
    ║                                                    ║
    ║  ┌──────────────────────────────────────────┐     ║
    ║  │ 1. ASK THE MODEL                          │     ║
    ║  │    send messages + the tool schemas       │     ║
    ║  └──────────────┬───────────────────────────┘     ║
    ║                 ▼                                  ║
    ║  ┌──────────────────────────────────────────┐     ║
    ║  │ 2. RECORD WHAT IT SAID                    │     ║
    ║  │    append the assistant message           │     ║
    ║  └──────────────┬───────────────────────────┘     ║
    ║                 ▼                                  ║
    ║          ╔═══════════════════╗                     ║
    ║          ║ did it ask for    ║                     ║
    ║          ║ any tools?        ║                     ║
    ║          ╚═══╦═══════════╦═══╝                     ║
    ║        NO    ║           ║   YES                   ║
    ║   ┌──────────▼──┐        ▼                         ║
    ║   │ 3. RETURN   │  ┌───────────────────────────┐  ║
    ║   │    done     │  │ 4. RUN THEM, in order     │  ║
    ║   └─────────────┘  │    registry.dispatch(...) │  ║
    ║                    └────────────┬──────────────┘  ║
    ║                                 ▼                  ║
    ║                    ┌───────────────────────────┐  ║
    ║                    │ 5. APPEND THE RESULTS     │  ║
    ║                    │    as {"role": "tool"}    │  ║
    ║                    └────────────┬──────────────┘  ║
    ║                                 │                  ║
    ╚═════════════════════════════════╪══════════════════╝
                    loop back ────────┘
                                 │
                 ran out of iterations? → stop and say so
```

Four things to understand precisely:

**The exit condition is "the model stopped asking for tools"** — not "the task succeeded." Nothing checks for success. The model signals it is finished by simply replying with text instead of a tool request.

**The iteration cap counts model calls, not tool calls.** Ten tools in one response is one iteration. The cap exists so a confused model cannot loop forever on your time.

**Tools in a single response run sequentially**, in a plain `for` loop. Running them in parallel is a deliberate choice for a later phase, not an oversight here.

**Step 5 is the reason the loop exists.** You cannot hand a raw `ls` dump to a user and call it an answer. The results go back to the model so it can turn bytes into a grounded sentence. The loop is not just execution — it is interpretation.

Note also that `agent_loop` modifies `messages` in place. The CLI still owns that list, exactly as in phase 1. Only the work was delegated, not the ownership.

## Who actually runs the command

This is the part worth being pedantic about, because most confusion about agents lives here.

```
   MODEL                         YOUR CODE
   ─────                         ─────────
   emits a request:              receives it
   {"command": "date"}   ─────►  validates it against the schema
                                 checks it against the safety rules
                                 subprocess.run(...)   ← the real world is touched
                                 truncates the output
                         ◄─────  returns a plain string
   reads the result,
   writes a sentence
```

The model never executes anything. It produces a JSON request and hands it to you. Every security property this agent has lives on the right-hand side.

## Tools: a schema plus a function

`tools/registry.py` holds two dictionaries: the **schema** the model reads, and the **handler** your code runs. `register(schema, handler)` adds a tool; `dispatch(name, args)` validates and invokes it.

The interesting detail is what happens when validation fails. A missing or unexpected parameter returns an **error string**, not an exception:

```
Error: Tool 'bash' missing required parameter(s): command.
```

That string becomes a tool result, the loop continues, and the model reads its own mistake and corrects it on the next iteration. **Schema violations are a conversation, not a crash.** Genuine bugs inside a handler still raise, because those are yours to fix and should be loud.

## One tool, enormous reach

`tools/bash.py` defines a single tool with one string parameter. Ask the agent what time it is and it will emit `{"command": "date"}` — a command nobody wrote code for. The model already knows shell; you are only giving it a way to run things.

The field doing the work is **`description`**. The model never sees your function — the description is the entire basis on which it decides when to reach for the tool. The name matters far less than most people assume; the description matters far more.

## Safety guards

Four independent limits, each in a different place:

| Guard | Where | What it stops |
|-------|-------|---------------|
| Command blocklist | `tools/safety.py` | Known-destructive commands, before execution |
| 60-second timeout | `tools/bash.py` | Commands that hang |
| 50K output truncation | `tools/safety.py` | A command that returns 10,000 lines and blows up your context |
| 50-iteration cap | `core/loop.py` | A model stuck in a loop |

Worth being honest about the first one: **a blocklist is a speed bump, not a sandbox.** It enumerates bad strings, and there is always one more phrasing it does not cover — a glob, a variable, a subshell, an encoding. Real containment restricts what the process can *reach*, not what the command *looks like*. A later phase moves in that direction with path sandboxing.

## Run it

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m agent.cli
```

### Try this

```
> what is the time now?
```

Watch for the yellow `[tool: bash] command=date` line, then a sentence built from the output.

```
> /inspect
```

**This is the payoff.** One turn, but *two* model calls — with the tool call and its result sitting between them. That is the loop, made visible. Everything in the later phases is a variation on what you are looking at.

More things to try:

```
> create a folder called demo and list what is in this directory
> run sleep 200                    ← hits the 60-second timeout
```

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

The agent can run shell commands, which technically means it can do anything — `cat` a file, `sed` an edit. But going through a shell for file work is clumsy and unsafe, and nothing stops it from wandering outside your project directory. [Phase 3](../phase-3-file-tools/) gives it proper file tools with path sandboxing.
