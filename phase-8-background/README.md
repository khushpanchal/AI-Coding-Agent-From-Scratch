# Phase 8 — Background Tasks

**Delegate without waiting. A daemon thread, a `quiet` flag, and a mailbox the loop drains.**

Phase 7's subagent worked, but it **blocked**. Delegate three investigations and they run one after another while you watch a frozen prompt. The child was already isolated and self-contained — the only thing missing was permission to not wait for it.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## The problem is one word: *wait*

```
  PHASE 7                               PHASE 8
  ───────                               ───────
  dispatch("subagent")                  dispatch("background_run")
    child runs ████████████               spawn thread, RETURN NOW
    parent blocked ▓▓▓▓▓▓▓▓               parent keeps working ──────►
  return summary                        summary arrives later,
                                        through a mailbox
```

Everything hard about this was already solved in phase 7 — isolation, privilege, the summary filter. What's left is genuinely small, and the lecture says so: *it can be done easily just by using a thread.*

But two things follow from that thread, and they're the real content of this phase.

## Consequence 1 — the child must be silent

Two agents printing to the same terminal produce interleaved garbage. The fix is smaller than you'd expect — **no stdout redirection, no per-thread capture**, just a flag:

```python
def agent_loop(..., quiet: bool = False):
    emit = (lambda *a, **k: None) if quiet else print
```

Every `print` in the loop became `emit`. `print_stream` gets the same treatment, with one important detail: when quiet, **the stream is still fully consumed** — only the `sys.stdout.write` is skipped. The child still needs the assembled response; it just doesn't narrate.

That's the entire silencing mechanism. Three lines pass `quiet` down through `run_subagent` to `agent_loop`.

## Consequence 2 — the result needs a mailbox

If the parent isn't waiting, the child can't return a value anywhere useful. It needs somewhere to leave the answer, and the parent needs somewhere to look.

```
   ┌─── MAIN THREAD ──────────────────────────────────────────────────┐
   │  agent_loop                                                       │
   │   ┌─ PRE-CALL PIPELINE (before EVERY model call) ──────────┐     │
   │   │ 1. micro_compact(messages)                     [p4]    │     │
   │   │ 2. should_auto_compact → auto_compact          [p4]    │     │
   │   │ 3. bg.drain_notifications()   ◄── NEW HERE     [p8]    │     │
   │   │ 4. task_manager.tick()                         [p6]    │     │
   │   └────────────────────────────────────────────────────────┘     │
   │   provider.chat_stream(...)                                       │
   │   dispatch("background_run") ──┐                                  │
   └────────────────────────────────┼──────────────────────────────────┘
                                    ▼
   ┌─── BackgroundManager (parallel/background.py) ───────────────────┐
   │  _tasks          id → {prompt, status, result}                   │
   │  _notifications  deque()   ◄── THE MAILBOX                       │
   │  _lock           guards id allocation                            │
   │                                                                   │
   │  run()  → spawn daemon thread, RETURN IMMEDIATELY with            │
   │           "Background subagent #N started"                        │
   │           ▲ that string is the tool result — it lands in          │
   │             `messages` right away, so the model knows it fired    │
   └────────────────────────────────┬──────────────────────────────────┘
                                    ▼  (new daemon thread)
   ┌─── BACKGROUND THREAD ────────────────────────────────────────────┐
   │  run_subagent(provider, prompt, agent_type, quiet=True)          │
   │    └─► the SAME agent_loop — fresh messages, narrower registry,  │
   │        own system prompt, quiet=True, max_iterations=30          │
   │  on finish:                                                       │
   │    _tasks[id].status = "completed"                                │
   │    _notifications.append("<background-result …>")                 │
   └───────────────────────────────────────────────────────────────────┘
```

### How the result gets back into the conversation

This is the part worth tracing carefully, because it's where the design decision lives:

```
  child thread                    main thread
  ────────────                    ───────────
  summary ready
      └─ _notifications.append ──┐
                                 │  deque hand-off — append and popleft
                                 │  are atomic under CPython's GIL
                                 ▼
              next loop iteration, at the TOP, before the model is called:

                  for note in bg.drain_notifications():
                      messages.append({"role": "user",      "content": note})
                      messages.append({"role": "assistant", "content": "Noted…"})
                                 │
                                 ▼
              the model's next call sees the summary as if you had typed it
```

Three details, each deliberate:

**It's injected as a `user` message.** There's no "background result" role in any chat API. Existing roles are all you have, so the result arrives dressed as user input — wrapped in a `<background-result task_id='N'>` envelope so the model can tell it apart from your actual typing.

**A synthetic `assistant` acknowledgement follows it.** That keeps `user → assistant` alternation intact, which some providers require. Same reasoning as phase 4's two-message compaction result.

**The drain happens before `chat_stream`, not when the task finishes.** So a result lands at the start of the *next* model call — in practice, the next time you type something. The parent isn't interrupted mid-thought; it checks its mailbox on the way past. And note *where* it plugs in: the pre-call pipeline that phase 4 opened and phase 6 extended. Third mechanism, same slot.

## The threading model

One `threading.Thread(daemon=True)` per call. **No pool, no cap.** Daemon means the process can exit with children still running.

That's appropriate for a teaching codebase and worth naming as a limitation: a confused model that calls `background_run` in a loop spawns unbounded threads. The lecture names the production answer — a thread pool with an executor framework on top — and the [streaming lab](../lab-streaming-tool-execution/) is where a `ThreadPoolExecutor` actually appears.

## Two tools, not one

| Tool | Purpose |
|---|---|
| `background_run` | start a task, return immediately |
| `check_background` | ask for the status of all tasks |

`check_background` exists because the mailbox is **push** and sometimes the model wants **pull** — "is that done yet?" — without waiting for a drain. Two directions of information flow again, the same pattern phase 6 introduced with `tick()`.

## Run it

```bash
mkdir -p /tmp/p8test && cd /tmp/p8test
printf 'def add(a,b):\n    return a+b\n' > calc.py

PYTHONPATH=/path/to/phase-8-background \
  /path/to/phase-8-background/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `start a background task with agent_type explore to summarise calc.py` | returns **instantly** — `Background subagent #1 started` |
| `what is 2+2?` | the agent answers normally; **the child is working silently** |
| `check background tasks` | `[running]` or `[done]` |
| press Enter / ask anything once it's done | `[Background task completed]` appears, then the model references the result |
| `/debug` | the summary is a **`user`** message wrapped in `<background-result>`, followed by a synthetic assistant ack |

That `/debug` row is the phase. The result didn't arrive through a return value — it arrived as a message, because messages are the only memory this system has.

## Note before you run phases 9–10

Ollama serialises requests per model by default, so concurrent agents **queue** rather than run in parallel — which looks like a hang. Set `OLLAMA_NUM_PARALLEL=2` (or higher) before the next phase. RAM scales with parallelism × context length.

## What's missing

You can now fire off work and carry on. But each background task is **anonymous and amnesiac** — a fresh child every time, with no memory of the last one. Ask for a follow-up and you re-explain everything. [Phase 9](../phase-9-teams/) gives the worker a name and a memory that outlives the task.
