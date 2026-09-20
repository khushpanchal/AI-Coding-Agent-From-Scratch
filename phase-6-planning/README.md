# Phase 6 — Planning

**A task board that lives outside the conversation, so compression can't erase it.**

Ask the agent for a five-step refactor. By step three it has lost the plan. Not because it's forgetful in some vague way — because of something you built two phases ago, working exactly as designed.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## The problem is a mechanism, not a mood

```
  messages = [ ... 60 turns of work ... ]
       ▲
       │  micro_compact blanks old tool results        (phase 4, every turn)
       │  auto_compact REPLACES THE ENTIRE LIST
       │             with a single summary             (phase 4, at threshold)
       │
       └─ if the plan lives in here, the plan is not durable
```

Phase 4 made long sessions affordable by aggressively rewriting `messages`. But the plan *was* in `messages` — stated once, in a turn that got summarised into "the user asked for a refactor." The detail is gone.

**The fix is structural: state that must survive cannot live in the message list.** Once you see that, this phase writes itself.

## The design

```
                              ┌──────────────────────────────┐
                              │ TaskManager (planning/       │
                              │              tasks.py)       │
                              │ _tasks: {id: {subject,       │
                              │   status, blocked_by,        │
                              │   blocks, started_at}}       │
                              │ _round: int                  │
                              │                              │
                              │ LIVES OUTSIDE messages  ⇒    │
                              │ compression cannot touch it  │
                              └───┬──────────────────┬───────┘
                                  │                  │
              WRITE/READ PATH     │                  │   PUSH PATH
             (the model asks)     │                  │  (the loop pushes)
                                  ▼                  ▼
    ┌──────────────────────┐  ┌───────────────┐  ┌────────────────────┐
    │ ToolRegistry         │  │ tasks.handle()│  │ tasks.tick()       │
    │ register(TASK_SCHEMA,│─►│ ONE tool,     │  │ called EVERY       │
    │          tasks.handle│  │ FIVE actions: │  │ iteration; returns │
    │ ← a bound method =   │  │ create update │  │ a <reminder> at    │
    │   a closure over     │  │ list get      │  │ age 8 and 16       │
    │   the manager        │  │ delete        │  │                    │
    └──────────────────────┘  └───────────────┘  └─────────┬──────────┘
                                                            │
  ┌─────────────────────────────────────────────────────────┼────────┐
  │ agent_loop — the ONLY 6 lines that changed              │        │
  │   for i in range(max_iterations):                       │        │
  │       micro_compact(messages)             ← phase 4     │        │
  │       if should_auto_compact(...): ...    ← phase 4     │        │
  │       if task_manager:                    ← PHASE 6 ◄───┘        │
  │           nag = task_manager.tick()                              │
  │           if nag: messages.append({"role":"user", ...})          │
  │       ... call model, dispatch tools, append ...  UNCHANGED      │
  └──────────────────────────────────────────────────────────────────┘
```

Six lines, dropped into the **pre-call pipeline slot** that phase 4 opened. The loop's call/dispatch/append machinery is untouched. Note how the slot is turning into a general-purpose place for per-turn mechanisms — that's now a pattern, not a coincidence.

## Two directions of information flow

This is the conceptually new thing in this phase, and it's worth naming:

```
  PULL — the model asks                PUSH — the system tells
  ────────────────────                 ───────────────────────
  model emits task(action="create")    loop calls tick() every iteration
  → a tool call, model-initiated       → injects a message the model
  → the model chose to do this           never asked for
```

Every tool so far has been pull: the model decides, your code responds. `tick()` is the first **push** — your code injecting a message into the conversation on its own initiative, because a task has been in progress too long.

That's an agent design pattern in its own right. The system isn't just a service the model calls; it can also interrupt.

## Invariants enforced in code, not in the prompt

This is the same lesson as phase 3's sandbox, applied to state. You *could* write "only work on one task at a time" in the system prompt and hope. Instead:

| Invariant | How it's enforced |
|---|---|
| Only one task `in_progress` | setting a task in progress **demotes** any other in-progress task to pending |
| Blocked tasks unblock themselves | `_active_blockers()` filters to non-completed blockers **at read time** — nothing is eagerly rewritten |
| The nag clock can't be reset | `started_at` is set only on the *transition into* `in_progress`, not on re-assertion |

That last one is subtle and good. If `started_at` were refreshed every time the model marked a task in progress, the model could silence the reminder forever by re-asserting the same status. The transition check makes the clock honest.

`blocked_by` / `blocks` are written as bidirectional links at create time, so the graph can be walked from either end.

## The reminder ladder

```
  age = current_round - started_at

  age == 8    soft:  "still working on this? if it grew, consider splitting"
  age == 16   hard:  "(a) split it  (b) explain and continue
                      (c) mark complete ONLY if actually done"
```

Read the wording order carefully. "Mark complete" is offered **last**, and hedged. If completion were listed first, the cheapest way for a model to stop being nagged would be to declare victory. Ordering the options so the easy exit isn't the dishonest one is prompt design doing real work.

## One tool, five actions

`task` is a single tool with an `action` parameter (`create` / `update` / `list` / `get` / `delete`) rather than five separate tools.

Compare this with phase 3, where the argument went the other way — five separate file tools instead of one `file_op`. Both are right, and the difference is instructive:

- **File tools** have genuinely different required arguments (`read` needs a path; `edit` needs path + old + new). Splitting lets the schema enforce that.
- **Task actions** share one shape — mostly an id and a couple of optional fields. Splitting would produce five nearly-identical schemas and five registry entries for no validation benefit.

The question to ask isn't "one or many," it's **"do these operations have different argument shapes?"**

## The board is in memory only

`TaskManager` holds state in a Python object. Restart the agent and the board is empty. It survives *compression*, which is what it was built for — not process death.

Persisting it would mean choosing a storage location, a format, and a reconciliation story for a stale board that no longer matches the repo. That's a real feature, not a line of code, and it isn't in this phase.

## Run it

```bash
mkdir -p /tmp/agent-demo-6 && cd /tmp/agent-demo-6
PYTHONPATH=/path/to/phase-6-planning \
  /path/to/phase-6-planning/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `plan a refactor of calculator.py in 4 steps and track it` | several `[tool: task]` calls with `action=create` |
| `/tasks` | the board — statuses, and any blocked-by links |
| `start the first task` | `action=update`, status `in_progress` |
| `start the third task too` | the second one is **silently demoted** to pending |
| keep chatting for ~8 rounds | a `<reminder>` appears that **you did not ask for** — that's `tick()` pushing |
| `/compact` then `/tasks` | **the board survives** — the conversation was summarised, the plan wasn't |

That last row is the phase in one line. Everything else was rewritten; the task board was untouched, because it was never in the list that gets rewritten.

## New commands

```
/tasks     Show the task board
```

## What's missing

The agent can plan and remember the plan, but it does all the work itself, in one conversation. A long investigation — "find every place we call this API" — fills the context with dozens of file reads, and then compression eats them anyway. [Phase 7](../phase-7-subagents/) spawns a child agent with its own context, does the work over there, and brings back only the answer.
