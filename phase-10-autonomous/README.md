# Phase 10 — Autonomous Team

**Stop assigning. Publish a queue and let free workers pull from it.**

This phase adds **no new tool** and **no new file**. It rewrites one module in place, and the agent gets meaningfully better. That's worth sitting with: the capability jump here is a change of *protocol*, not a change of surface area.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## Push versus pull

```
        PHASE 9 — PUSH                        PHASE 10 — PULL
  ┌──────────────────────────────┐   ┌──────────────────────────────────┐
  │ the LEAD decides who's next, │   │ the FREE TEAMMATE decides what's │
  │ only at coarse barriers      │   │ next, immediately                │
  │                              │   │                                  │
  │ t0  assign T1→Sam            │   │ t0  run([T1,T2,T3,T4])           │
  │     assign T2→Ria            │   │     Sam pulls T1 · Ria pulls T2  │
  │ t1  wait ─── barrier ───     │   │ t1  Ria done → Ria pulls T3      │
  │     Sam idle ▓▓▓▓ (wasted)   │   │ t2  Sam done → Sam pulls T4      │
  │ t2  assign T3→… but first a  │   │ t3  queue empty → return         │
  │     whole new model round!   │   │     NOBODY was ever idle          │
  └──────────────────────────────┘   └──────────────────────────────────┘
```

In phase 9 the lead is a scheduler, and a scheduler that has to think with a language model is a slow scheduler. Every reassignment costs a full round-trip. Worse, the lead only gets to schedule at the barrier — so the *fastest* worker is throttled by the *slowest* one.

Pull removes the lead from the inner loop entirely. Work distribution becomes a property of the queue rather than a decision someone has to make.

## What changed

```
  phase 9                          phase 10
  ───────                          ────────
  actions: hire assign wait status actions: hire run status
                                            ▲ assign+wait collapse into run
  task: string                     tasks: array of string
  _reports: deque   (finished)     _queue:  deque   (PENDING)  ◄ the one new idea
                                   _events: deque   (progress feed)
  Team._run(member)                Team._work_loop(member)
    run ONE task, then idle          while True: pop, run, repeat
```

The loop of each worker:

```python
while True:
    with self._lock:
        if not self._queue:
            break                 # objective stop: nothing left to pull
        task = self._queue.popleft()
    ...run agent_loop on that task...
    self._events.append(("done", name, task, summary))
```

**One thread per teammate, not one per task.** Two workers and forty tasks means two threads, each pulling forty times between them. Compare with phase 8, where every `background_run` spawned a thread — that model doesn't scale, and this one does, by binding threads to workers instead of to work.

## The architecture

```
 ┌──── MAIN THREAD ───────────────────────────────────────────────────┐
 │ agent_loop — STILL UNCHANGED (two phases running untouched)        │
 │   dispatch("team", {action:"hire", …}) ×2                          │
 │   dispatch("team", {action:"run", tasks:[T1,T2,T3,T4]}) → BLOCKS   │
 └────────────────────────────────┬───────────────────────────────────┘
                                  ▼
 ┌──── Team._run_team ────────────────────────────────────────────────┐
 │  1. normalize tasks (accepts a list OR a newline-separated string) │
 │  2. _queue.extend(tasks)         ◄ THE SHARED QUEUE                │
 │  3. one daemon thread per TEAMMATE                                 │
 │  4. main thread polls _events every 100ms and prints:              │
 │        [Sam] pulled: …     [Sam] ✓ …                               │
 │     done when: queue empty AND all idle AND no pending events      │
 │  5. return ONE tool result containing every report                 │
 └────────────────────────────────┬───────────────────────────────────┘
              ┌───────────────────┴───────────────────┐
              ▼                                       ▼
   ┌── THREAD "Sam" ─────────┐          ┌── THREAD "Ria" ─────────┐
   │ while True:             │          │ while True:             │
   │   pop from shared queue │◄────────►│   pop from shared queue │
   │   (under the lock)      │  same    │   (under the lock)      │
   │   agent_loop(...)       │  deque   │   agent_loop(...)       │
   │   file a "done" event   │          │   file a "done" event   │
   └─────────────────────────┘          └─────────────────────────┘
```

Two deques doing different jobs: `_queue` is work going **out**, `_events` is progress coming **back**. Keeping them separate is what lets the main thread render a live feed while workers keep pulling.

## The teammate barely changed

`Teammate` still holds `name`, `role`, its own `messages` (still appended to, still never cleared), its own tools. Memory across tasks still works exactly as in phase 9.

One sentence of the system prompt changed: *"A lead assigns you tasks"* → *"You are given one task at a time."* The worker no longer has a boss; it has a queue.

> **A note if you're diffing phase 9 against phase 10:** `team.py` is rewritten wholesale, so `Teammate` and `Team` both appear as large diffs. Nearly all of that is churn. The real change is `_reports` → `_queue` plus `_run` → `_work_loop`. Don't hunt for meaning in the rest.

## Why the tool count stays at 13

Phases 9 and 10 both expose 13 tools. If you've been reading the phase ladder as "each phase adds a tool," this one breaks the pattern — and that's the point.

**A phase adds a capability, not necessarily a tool.** The most valuable changes in a mature system are often protocol changes behind a stable interface: the model calls `team` in both phases, and the thing that got better is what happens on the other side of that call.

## Run it

**Set this first, or the demo will look hung:**

```bash
launchctl setenv OLLAMA_NUM_PARALLEL 2   # macOS; then restart the Ollama app
# or: OLLAMA_NUM_PARALLEL=2 ollama serve
```

```bash
mkdir -p /tmp/p10test && cd /tmp/p10test

PYTHONPATH=/path/to/phase-10-autonomous \
  /path/to/phase-10-autonomous/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `hire Sam as a python developer and Ria as a python developer` | two hires |
| `have the team run these 4 tasks: write add.py with an add function; write sub.py with a subtract function; write mul.py with a multiply function; write div.py with a divide function that handles division by zero` | the live feed |
| *watch the output* | `[Sam] pulled:` / `[Ria] pulled:` / `[Sam] ✓` / **`[Sam] pulled:`** again |
| `ls` in another terminal | four real files |

**The moment that matters** is a worker pulling a *second* task without anyone assigning it. Nobody scheduled that. Sam finished, looked at the queue, and took the next thing — which in phase 9 would have required the lead to wake up, think, and issue a new instruction.

Give it 4 tasks and 2 workers so you can actually see the second pull. With 2 tasks and 2 workers, nobody ever pulls twice.

## Commands

```
/team      Show the roster — names, roles, status, current task
```

## What's missing

Your teammates now work efficiently and in parallel — **in the same directory**. They share one filesystem, and nothing stops two workers from editing the same file at the same time. Parallel work has been safe so far only because the tasks happened to touch different files.

Context isolation was never filesystem isolation. [Phase 11](../phase-11-isolation/) gives each experiment its own folder.
