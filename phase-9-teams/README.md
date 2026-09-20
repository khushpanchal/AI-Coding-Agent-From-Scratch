# Phase 9 — Teams

**A teammate is a background subagent plus a `messages` list that outlives the task.**

That sentence is the entire phase. Everything else is bookkeeping.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## The problem: every delegation starts from zero

Phase 8's background children are **anonymous and amnesiac**. Each one is created inside `run_subagent`, does its job, and evaporates. Ask for a follow-up — *"now add tests to what you just wrote"* — and you're explaining the whole context again to a stranger.

Three phases, one property added each time:

```
  p7  subagent     delegate once, BLOCK, get a summary          → isolation
  p8  background   delegate once, DON'T block, mailbox          → concurrency
  p9  team         delegate MANY times to the SAME NAMED worker → identity + memory
```

## The whole trick, in one comparison

```
  SUBAGENT (p7/p8)                      TEAMMATE (p9)
  ────────────────                      ─────────────
  run_subagent(...):                    class Teammate:
      messages = [user(prompt)]             self.name     = "Sam"
      ▲ created here                        self.role     = "backend engineer"
      agent_loop(messages, ...)             self.messages = []
      return summary                        ▲ lives on the OBJECT, in the roster
      ▲ messages dies with the call         self.tools    = ToolRegistry()
                                            self.status   = "idle"
```

A subagent's `messages` is a local variable. A teammate's `messages` is an attribute on an object held in a dictionary. **That's the difference.** Same `agent_loop`, same isolation, same privilege model — the list just doesn't go out of scope.

Assigning a task **appends** to that list; it never replaces it. So the second task arrives with the first one's entire conversation already in context.

| Property | Where it lives | Lifetime |
|---|---|---|
| identity | `self.name`, `self.role` | the process |
| **memory** | `self.messages` — appended to, never cleared | the process |
| role prompt | `self.system_prompt()` — an f-string, rebuilt per call | per call |
| capability | `self.tools` — its own registry | the process |
| liveness | `self.status`, mutated under the team's lock | per assignment |

Note the third row: the role prompt is **still a separate per-call argument**, never stored in `messages`. The invariant from phase 1 survives even here.

## The architecture

```
 ┌──── MAIN THREAD ───────────────────────────────────────────────────────┐
 │ agent_loop — UNCHANGED from phase 8, not one byte                      │
 │   dispatch("team", {action:"hire",   name:"Sam", role:"backend"})      │
 │   dispatch("team", {action:"assign", name:"Sam", task:"…"}) → NOW      │
 │   dispatch("team", {action:"assign", name:"Ria", task:"…"}) → NOW      │
 │   dispatch("team", {action:"wait"})                         → BLOCKS   │
 └────────────────────────────────┬───────────────────────────────────────┘
                                  ▼
 ┌──── Team (parallel/team.py) ───────────────────────────────────────────┐
 │  _members  dict[str, Teammate]      ◄ THE ROSTER, keyed by name        │
 │  _reports  deque[(name, summary)]   ◄ the mailbox, drained by wait     │
 │  _lock     threading.Lock()         ◄ guards status flips + reports    │
 │                                                                        │
 │  assign → member.messages.append(user(task))   ◄ APPEND, never replace │
 │           spawn daemon thread, return immediately                      │
 │  wait   → poll every 200ms on the MAIN thread; print each report as    │
 │           it lands; break when nobody is working and the box is empty  │
 └──────────────────┬─────────────────────────────────┬───────────────────┘
                    ▼                                 ▼
      ┌── THREAD "Sam" ──────────┐      ┌── THREAD "Ria" ──────────┐
      │ agent_loop(              │      │ agent_loop(              │
      │   messages=m.messages,   │      │   messages=m.messages,   │  ◄ SAME
      │   tools=m.tools,         │      │   tools=m.tools,         │    function
      │   system=m.system_prompt,│      │   system=…,              │
      │   quiet=True)            │      │   quiet=True)            │
      └──────────────────────────┘      └──────────────────────────┘

      ╳ Sam and Ria never talk to each other — hub-and-spoke only
      ╳ teammates are NOT given the `team` tool → they cannot sub-delegate
```

## Why the loop didn't change this time

Phase 8 *had* to modify the loop, because a background result arrived **unprompted** — something had to check the mailbox on every iteration.

Here, results are gathered by an explicit `wait` tool call that **the model itself makes**. The gathering happens inside a tool handler, on the main thread. `agent_loop` never learns any of this exists.

The lesson generalises: **unsolicited events need a hook in the loop; solicited ones only need a tool.** If you can express a capability as "the model asks and your code answers," you don't touch the engine.

## Only the main thread prints

Worker threads run `quiet=True` and never touch stdout. `wait` pops reports under the lock and prints them **itself**, from the main thread — so `[Sam] ✓ …` can't interleave mid-character with `[Ria] ✓ …`.

Concurrency in the workers, serialisation at the output. A small thing that makes the difference between a readable demo and garbage.

## The defect that motivates phase 10

Watch the timeline carefully when you run this:

```
  t0   assign T1 → Sam        assign T2 → Ria
  t1   wait ──────── barrier ────────
       Sam finishes first, then sits ▓▓▓▓▓ IDLE
  t2   ...until Ria finishes too, wait returns, and the lead needs
       a whole new model round-trip before it can assign anything else
```

**The lead is the bottleneck.** Workers can only receive work at the coarse barrier where the lead is paying attention, so a fast worker sits idle waiting for a slow one. That's the problem [phase 10](../phase-10-autonomous/) solves.

## Run it

**Set this first, or the demo will look hung:**

```bash
launchctl setenv OLLAMA_NUM_PARALLEL 2   # macOS; then restart the Ollama app
# or: OLLAMA_NUM_PARALLEL=2 ollama serve
```

Ollama serialises requests per model by default. With parallelism at 1, Sam and Ria **queue** — you'll sit between `[Sam] working` and `[Sam] ✓` wondering what broke.

**One-time setup** (the virtualenv is not checked in):

```bash
REPO=$(pwd)          # run this from the repository root
cd $REPO/phase-9-teams
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Then, because the agent sandboxes file operations to the directory you launch it from,
run it from a scratch folder rather than inside this repo:

```bash
mkdir -p /tmp/agent-demo-9 && cd /tmp/agent-demo-9

PYTHONPATH=$REPO/phase-9-teams \
  $REPO/phase-9-teams/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `hire Sam as a backend engineer and Ria as a test writer` | two `[tool: team] action=hire` calls |
| `/team` | the roster, both idle |
| `assign Sam to write greet.py with a greet function, and Ria to write a README` | both return **immediately** |
| `/team` | both `working` |
| `tell the team to wait` | reports land as they finish, one line each |
| **`assign Sam to add a docstring to the greet function he just wrote`** | **the memory demo** |

That last row is the phase. Sam is not told which function, which file, or what he did before — **it's all still in his `messages`.** Phase 8's background child would have had no idea what you were talking about.

## New commands

```
/team      Show the roster — names, roles, status, current task
```

## What's missing

The lead assigns, then waits at a barrier. A worker who finishes early has nothing to do until every other worker finishes and the lead gets a turn to think. [Phase 10](../phase-10-autonomous/) inverts it: the lead publishes a queue, and whoever is free pulls the next item.
