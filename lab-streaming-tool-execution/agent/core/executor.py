"""Tool execution - the heart of this project.

The agent runs each tool the moment its call appears in the model's stream
(StreamingToolExecutor): every `tool_call` event triggers an immediate
`pool.submit(...)`, so a tool starts running on a worker thread while the
model is still generating the rest of its reply. Tools run in parallel.

To show what that *buys* you, each turn also reports the counterfactual:
what the classic NON-STREAMING approach would have cost on the SAME response
(wait for the whole stream, THEN run the tools). Both numbers come from one
real run, so the model's large, random generation time cancels out and you
see the streaming saving directly:

    streaming     = max(stream_time, when the last tool finishes)   # measured
    non-streaming = stream_time + max(latency)                      # same response,
                                                                    # tools start at the end
    saved         = non-streaming - streaming

The saving is the overlap of tool work with token generation: any tool whose
call arrives early runs (partly or fully) before the stream ends. If every
call arrives only at the very end, the two are equal - the honest truth about
the technique.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

GREEN = "\033[32m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

MAX_WORKERS = 8


@dataclass
class ToolRun:
    """One tool execution and its timeline (seconds, relative to run start)."""

    call_id: str
    name: str
    args: dict
    result: str = ""
    submitted_at: float = 0.0   # when its call appeared in the stream
    started_at: float = 0.0     # when a worker actually began running it
    finished_at: float = 0.0    # when it returned

    @property
    def duration(self) -> float:
        """Wall time the tool itself spent running (its own latency)."""
        return self.finished_at - self.started_at


@dataclass
class ExecutionResult:
    """Everything one agent-loop iteration produced, plus its timing.

    Carries the real (measured) streaming timeline and the computed
    non-streaming counterfactual for the SAME model response.
    """

    response: dict
    runs: list[ToolRun] = field(default_factory=list)
    t_stream_done: float = 0.0          # when the model stream finished
    t_all_done: float = 0.0             # when the last tool finished (measured)

    # ── what the agent loop needs to continue ──
    @property
    def tool_results(self) -> list[dict]:
        return [
            {"tool_call_id": r.call_id, "tool_name": r.name, "content": r.result}
            for r in self.runs
        ]

    # ── timing ──
    @property
    def stream_time(self) -> float:
        return self.t_stream_done

    @property
    def n_tools(self) -> int:
        return len(self.runs)

    @property
    def max_duration(self) -> float:
        return max((r.duration for r in self.runs), default=0.0)

    @property
    def streaming_total(self) -> float:
        """Measured wall time: what just ran (tools started mid-stream)."""
        return self.t_all_done

    @property
    def non_streaming_total(self) -> float:
        """Counterfactual on the SAME response: wait for the whole stream,
        then run the tools in parallel -> stream_time + max(latency)."""
        return self.stream_time + self.max_duration

    @property
    def saved(self) -> float:
        return self.non_streaming_total - self.streaming_total

    def format_summary(self) -> str:
        """A timing block comparing streaming vs non-streaming on this run."""
        if self.n_tools == 0:
            return f"{DIM}(no tools this turn - pure chat, {self.stream_time:.2f}s){RESET}"

        s = self.streaming_total
        ns = self.non_streaming_total
        saved = self.saved
        pct = (saved / ns * 100) if ns > 0 else 0.0

        left1 = "streaming     (start tools as calls arrive)"
        left2 = "non-streaming (wait for the full response) "

        lines = []
        lines.append(f"{BOLD}┌─ tool execution {'─' * 31}{RESET}")
        lines.append(f"  model stream time : {self.stream_time:.2f}s")
        lines.append(f"  tool calls        : {self.n_tools}")
        lines.append(f"  {DIM}── same response, two strategies ──{RESET}")
        lines.append(f"  {left1} : {BOLD}{GREEN}{s:5.2f}s{RESET}  {DIM}◄ this run{RESET}")
        lines.append(f"  {left2} : {ns:5.2f}s")
        lines.append(f"  {BOLD}{GREEN}saved {saved:.2f}s  ({pct:.0f}% faster){RESET}")
        lines.append(f"{BOLD}└{'─' * 46}{RESET}")
        return "\n".join(lines)


def _worker(registry, run: ToolRun, t0: float):
    """Build a callable that runs one tool, stamping its own start/finish
    times (relative to t0). Submitted to a thread pool so tools run in
    parallel and durations are measured directly.
    """
    def call():
        run.started_at = time.perf_counter() - t0
        run.result = registry.dispatch(run.name, run.args)
        run.finished_at = time.perf_counter() - t0
        return run.result

    return call


class StreamingToolExecutor:
    """Start each tool the instant its call appears in the stream.

    The generator is consumed exactly once; each `tool_call` event triggers
    an immediate `pool.submit(...)`, so the tool starts on a worker thread
    while the model keeps producing tokens. The main thread never blocks on a
    tool - it goes right back to reading the stream. By the time the `done`
    event arrives, tools that fired early may already be finished.
    """

    def __init__(self, max_workers: int = MAX_WORKERS):
        self.max_workers = max_workers

    def run(self, stream, registry, on_text) -> ExecutionResult:
        t0 = time.perf_counter()
        response = None
        runs: list[ToolRun] = []
        futures = []

        pool = ThreadPoolExecutor(max_workers=self.max_workers)
        try:
            for event in stream:
                if event["type"] == "text":
                    on_text(event["content"])
                elif event["type"] == "tool_call":
                    tc = event["tool_call"]
                    run = ToolRun(call_id=tc["id"], name=tc["name"], args=tc["arguments"])
                    run.submitted_at = time.perf_counter() - t0
                    # THE WHOLE POINT: start the tool NOW, mid-stream,
                    # while the model keeps generating the rest of its reply.
                    futures.append(pool.submit(_worker(registry, run, t0)))
                    runs.append(run)
                elif event["type"] == "done":
                    response = event["response"]

            on_text("\n")
            t_stream_done = time.perf_counter() - t0

            # Many of these are already done - they ran during the stream.
            for fut in futures:
                fut.result()
            t_all_done = time.perf_counter() - t0
        finally:
            pool.shutdown(wait=True)

        return ExecutionResult(
            response=response,
            runs=runs,
            t_stream_done=t_stream_done,
            t_all_done=t_all_done,
        )
