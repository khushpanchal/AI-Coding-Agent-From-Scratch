# Lab — Streaming Tool Execution

**Start running a tool the instant its request finishes streaming, instead of waiting for the model to stop typing.**

> This is **not** phase 12. It's a standalone benchmark of one production optimization, built on a minimal agent so the measurement isn't buried under nine phases of machinery. Read it after [phase 8](../phase-8-background/), where threads first appear — or last, as a finale. The phase ladder is in the [project README](../README.md).

## The observation

A model generates one token at a time. When it asks for three tools, that request streams as an array — and the array takes time to finish:

```
  t=0.0s   {"tool_calls": [
  t=1.7s     {"name": "read_file",  "args": {...}},     ← COMPLETE. Parseable. Runnable.
  t=2.3s     {"name": "run_tests",  "args": {...}},     ← COMPLETE
  t=3.3s     {"name": "web_search", "args": {...}}      ← COMPLETE
  t=3.4s   ]}                                            ← only NOW does the loop wake up
```

Every agent in this repo waits for `t=3.4s` and *then* starts working. But `read_file` was fully specified at `t=1.7s` and sat idle for 1.7 seconds for no reason.

**The question that drives the whole lab:** if a complete signal arrives early, can you start acting on it early?

## The result

```
  SEQUENTIAL (every phase 1-11)         STREAMING (this lab)
  ─────────────────────────────         ────────────────────
  stream  ██████████████████ 3.4s       stream  ██████████████████ 3.4s
                             then:        read_file   ▓▓▓▓▓      fired @1.7s
  read_file                  ▓▓▓▓▓       run_tests      ▓▓▓▓▓▓▓▓▓▓▓▓ @2.3s
  run_tests                       ▓▓▓▓   web_search       ▓▓▓▓▓▓▓▓ @3.3s
  web_search                          ▓▓
  └ 6.35s                               └ 5.29s   (measured)
```

Tool work is hidden *underneath* token generation rather than queued behind it.

## How the signal arrives early

You could detect a complete tool call yourself by counting brackets — when opens and closes balance, one call is done. That's the algorithm, and you don't have to write it: **Ollama already emits tool calls one at a time as it parses them.**

Which means the seam has been sitting in this codebase since phase 1:

```python
# providers/ollama.py — chat_stream
if chunk.message.tool_calls:
    for tc in ...:
        yield {"type": "tool_call", "tool_call": parsed}   # ◄ the instant it parses
```

And in `core/streaming.py`, in **every phase of this project**:

```python
elif event["type"] == "tool_call":
    # In Phase 1 we just have chat, no tools yet.
    pass          # ◄ this branch has been dead the whole time
```

The phase agents read tool calls off the final `done` event and ignore the per-call events entirely. **The event this lab is built on has been firing, unused, in all eleven phases.** That's a nice illustration of a general truth: the signal you need for an optimization is often already there, and nobody looked.

## The executor

```
 ┌──── core/executor.py :: StreamingToolExecutor.run ─────────────────┐
 │  t0 = perf_counter();  pool = ThreadPoolExecutor(max_workers=8)    │
 │                                                                     │
 │  for event in stream:            ◄ ONE pass, generator consumed once│
 │    "text"      → print it; main thread keeps reading                │
 │    "tool_call" → pool.submit(worker, run)     ◄── THE WHOLE POINT   │
 │                  ▲ non-blocking: the main thread returns to         │
 │                    reading the stream immediately                   │
 │    "done"      → capture the assembled response                     │
 │                                                                     │
 │  t_stream_done = perf_counter() - t0                                │
 │  for fut in futures: fut.result()   ◄ many are ALREADY finished     │
 │  t_all_done    = perf_counter() - t0                                │
 └─────────────────────────────────────────────────────────────────────┘
```

Roughly twenty lines of real change. Everything else — the registry, the dispatch contract, the provider — is what you've already read.

## The measurement is honest about itself

```
  streaming_total      = measured
  non_streaming_total  = stream_time + max(tool latency)   ← COMPUTED, same response
  saved                = the difference
```

The baseline is **computed rather than re-run**, and that's deliberate. Model generation time swings by seconds between runs; that noise would dwarf a one-second saving. Holding the response fixed isolates the executor from the model's variance.

And it degrades honestly: if every tool call arrives at the very end of the stream, the two numbers are **equal**, and the output says so.

`tools/simulated.py` exists for the same reason — five fake tools that just sleep:

```
  read_file 1.2s · lint_code 1.5s · web_search 2.0s · db_query 2.4s · run_tests 3.0s
```

Unequal on purpose: `sum = 10.1s` but `max = 3.0s`. That gap is what the thread pool recovers. They model **slow I/O-bound work**, which is exactly where overlapping with token generation pays.

## When this does and doesn't work

**It only applies when the model emits several tool calls in one response.** One tool call, no overlap, no gain. The whole optimization lives on parallelism *within a single assistant message*.

**And it's a bet.** You start executing before the model has finished its thought. If it's mid-hallucination, you've done work that gets thrown away — or worse, work with side effects. The honest framing: most of the time you buy a better experience, sometimes you waste effort. That trade is fine for reads and lookups, and needs thought for writes and deletes.

## The transferable pattern

This is the part worth keeping long after you've forgotten the code:

> **Write down every step of your system, in order, and ask at each one: can I get a signal early? If I get it early, can I start the work early?**

It isn't about agents. Any streaming or staged pipeline has the same shape — a progressive response, a multi-stage job, a paginated fetch. The habit of listing every step and interrogating each for early signals is the reusable skill.

## Why this isn't a numbered phase

It's built on roughly **phase 2**, not phase 11. No memory, no skills, no planning, no subagents, no teams, no real file tools. Its `BaseProvider` even drops the blocking `chat()` method, since this project only ever streams — a different contract from the one the phases share.

Dropping it in as `phase-12-…` would tell you the agent had *lost* nine phases of capability. It's a side quest that isolates one idea, which is why it can measure it cleanly.

## Run it

```bash
cd lab-streaming-tool-execution
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m agent.cli
```

Ask for something that needs several tools at once:

```
> read the config file, run the tests, and search the web for the error
```

Watch the timing block at the end: when each call was submitted, when each finished, and the two totals side by side.

## Where to go next

Port `StreamingToolExecutor` into [phase 11](../phase-11-isolation/)'s `core/loop.py`. It's about twenty lines, everything else already fits, and it's the one optimization the phase ladder demonstrates but never adopts — the loop still dispatches tools strictly one at a time, in every phase.
