# Architecture

> How every component fits together — from a single chat REPL to a 14-tool multi-agent system with workspace isolation.

## Overall Architecture

The system is organized in six horizontal layers, each building on the ones beneath it — though the multi-agent and isolation layers reuse the core agent loop as their primitive (a teammate is just another `agent_loop`). The loop at the center orchestrates everything — it calls the provider and dispatches tools — and its core while-loop *pattern* is unchanged from Phase 2 through Phase 11; later phases only add hooks around it (`quiet`, `background_manager`). The team and isolation layers add no new loop hooks at all — teammates run their own `agent_loop` on threads, and isolation is just a tool that shells out to `git worktree`.

```mermaid
graph TD
    subgraph Interface["Interface Layer"]
        CLI["cli.py<br/>REPL + Commands"]
    end

    subgraph Core["Core Engine"]
        Loop["loop.py<br/>Agent Loop"]
        Stream["streaming.py<br/>Token Printer"]
        Config["config.py<br/>Ollama Config"]
    end

    subgraph Capabilities["Capability Layer"]
        subgraph ToolsGroup["Tools"]
            Bash["bash.py"]
            Files["files.py"]
            Safety["safety.py"]
            TReg["registry.py"]
        end
        subgraph MemoryGroup["Memory"]
            AgentsMD["agents_md.py"]
            Compress["compression.py"]
        end
        subgraph PlanGroup["Planning"]
            Tasks["tasks.py"]
        end
        subgraph KnowGroup["Knowledge"]
            Skills["skills.py"]
        end
        subgraph ParGroup["Parallel"]
            Sub["subagent.py"]
            BG["background.py"]
        end
    end

    subgraph MultiAgent["Multi-Agent Layer"]
        Team["team.py<br/>Team + Teammates<br/>(shared task queue)"]
    end

    subgraph IsoLayer["Isolation Layer"]
        WT["isolation/worktree.py<br/>Git Worktrees"]
    end

    subgraph Provider["Provider Layer"]
        Base["base.py<br/>Abstract"]
        Ollama["ollama.py<br/>Ollama"]
        PReg["registry.py<br/>Factory"]
    end

    CLI --> Loop
    Loop --> Stream
    Loop --> TReg
    Loop --> Compress
    TReg --> Bash
    TReg --> Files
    Bash --> Safety
    Files --> Safety
    Loop --> Tasks
    Loop --> BG
    BG --> Sub
    CLI --> AgentsMD
    CLI --> Skills
    CLI --> Team
    CLI --> WT
    Team --> Loop
    Loop --> PReg
    PReg --> Ollama
    Ollama --> Base

    classDef phase12 fill:#e0e0e0,stroke:#999,color:#333
    classDef phase34 fill:#90caf9,stroke:#1565c0,color:#333
    classDef phase56 fill:#a5d6a7,stroke:#2e7d32,color:#333
    classDef phase78 fill:#fff9c4,stroke:#f9a825,color:#333
    classDef phase910 fill:#ffccbc,stroke:#d84315,color:#333
    classDef phase11 fill:#ef9a9a,stroke:#c62828,color:#333

    class CLI,Config,Stream,Base,Ollama,PReg phase12
    class Loop,Bash,Safety,TReg phase12
    class Files,AgentsMD,Compress phase34
    class Tasks,Skills phase56
    class Sub,BG phase78
    class Team phase910
    class WT phase11
```

**Legend:** Gray = Phase 1-2 | Blue = Phase 3-4 | Green = Phase 5-6 | Yellow = Phase 7-8 | Orange = Phase 9-10 | Red = Phase 11

---

## Agent Loop: Control Flow

The core `agent_loop()` function drives the entire system. This sequence shows one complete turn — from user input to final response. The while-loop continues as long as the LLM returns tool calls.

```mermaid
sequenceDiagram
    actor User
    participant CLI as cli.py
    participant AL as agent_loop()
    participant Comp as compression.py
    participant LLM as Provider
    participant Tools as ToolRegistry

    User->>CLI: types input
    CLI->>CLI: append user message
    CLI->>AL: agent_loop(messages, tools)

    rect rgb(240, 240, 240)
        Note over AL,Tools: While LLM returns tool_calls (max 50 iterations)
        AL->>Comp: micro_compact(messages)
        Note right of Comp: Layer 1: trim old tool results

        opt Token count > 100K
            AL->>Comp: auto_compact(messages)
            Note right of Comp: Layer 2: LLM summarizes
        end

        opt Background tasks completed
            AL->>AL: drain notifications
        end

        opt Task nag due
            AL->>AL: inject reminder
        end

        AL->>LLM: chat_stream(messages, tools)
        LLM-->>AL: stream tokens

        alt Tool calls in response
            AL->>Tools: dispatch(name, args)
            Tools-->>AL: result string
            Note over AL: append results, continue
        else No tool calls
            AL-->>CLI: return
        end
    end

    CLI-->>User: response displayed
```

**Key insight:** This loop is written once in Phase 2 and never modified. Phases 4-11 add hooks *around* it (compression, nag, background notifications) but the core pattern — call LLM, dispatch tools, loop — is immutable. Teammates (Phase 9-10) and isolation (Phase 11) don't touch it at all — each teammate simply runs its own copy of this same loop.

---

## Phase Progression

```mermaid
timeline
    title From Chat to Autonomous Agents — 0 to 14 tools

    Phase 1 - Foundation (0 tools)
        : CLI REPL with streaming
        : Ollama provider

    Phase 2 - Agent Loop (1 tool)
        : while-loop + tool dispatch
        : Adds bash

    Phase 3 - File Tools (6 tools)
        : Path sandboxing
        : Adds read_file, write_file, edit_file, list_files, search_files

    Phase 4 - Smart Context (7 tools)
        : AGENTS.md project instructions
        : 3-layer compression
        : Adds compact

    Phase 5 - Skills (8 tools)
        : Two-layer skill injection
        : On-demand knowledge loading
        : Adds load_skill

    Phase 6 - Planning (9 tools)
        : TaskManager with dependencies
        : Mutual-exclusion in_progress and stuck-item nag
        : Adds task

    Phase 7 - Subagent (10 tools)
        : Spawn child agent with isolated context
        : Synchronous — saves tokens, not time
        : Adds subagent

    Phase 8 - Background (12 tools)
        : Subagents in daemon threads (non-blocking)
        : quiet=True keeps the child off the terminal
        : Adds background_run, check_background

    Phase 9 - Teams (13 tools)
        : Named teammates that remember across tasks
        : Hub-and-spoke — lead hires, assigns, and waits (push)
        : Adds team (hire / assign / wait / status)

    Phase 10 - Autonomous (13 tools)
        : Teammates pull from a shared task queue (push becomes pull)
        : Self-distributing; stops on an objective condition (queue empty)
        : Evolves the team tool (assign/wait become run) — no new tool

    Phase 11 - Workspace Isolation (14 tools)
        : Git worktrees — a separate folder + branch per experiment
        : Filesystem isolation, distinct from a subagent's context isolation
        : Adds worktree (create / list)
```

---

## Phase Details

### Phase 1: Foundation (0 tools)

The starting point: a streaming chat REPL connected to a local Ollama model. No tools — the agent can only talk.

```mermaid
graph LR
    User((User)) --> CLI["cli.py<br/>REPL + /commands"]
    CLI --> PReg["registry.py<br/>Provider Factory"]
    PReg --> Ollama["ollama.py<br/>Ollama Provider"]
    Ollama --> Base["base.py<br/>Abstract Interface"]
    Ollama --> Server["Ollama Server<br/>qwen2.5:7b"]
    Server --> Stream["streaming.py<br/>Token Printer"]
    Stream --> User
    CLI --> Config["config.py<br/>Model + URL"]

    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class CLI,PReg,Ollama,Base,Server,Stream,Config new
```

### Phase 2: Agent Loop (1 tool)

The heart of the system: a while-loop that calls the LLM, executes tool calls, and loops until the model is done.

```mermaid
graph LR
    CLI["cli.py"] --> Loop["loop.py<br/>Agent Loop ♻️"]
    Loop --> Provider["Ollama Provider"]
    Loop --> TReg["registry.py<br/>Tool Registry"]
    TReg --> Bash["bash.py<br/>Shell Execution"]
    Bash --> Safety["safety.py<br/>Command Blocking"]
    Loop -->|"no tool calls = done"| CLI

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class CLI,Provider existing
    class Loop,TReg,Bash,Safety new
```

### Phase 3: File Tools (6 tools)

Five file operations with path sandboxing. The agent can now read, write, and edit files safely.

```mermaid
graph LR
    TReg["Tool Registry"] --> Bash["bash"]
    TReg --> RF["read_file"]
    TReg --> WF["write_file"]
    TReg --> EF["edit_file"]
    TReg --> LF["list_files"]
    TReg --> SF["search_files"]
    RF & WF & EF & LF & SF --> Safety["safety.py<br/>+ Path Sandboxing"]

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    classDef modified fill:#fff59d,stroke:#f9a825,color:#333
    class TReg,Bash existing
    class RF,WF,EF,LF,SF new
    class Safety modified
```

### Phase 4: Smart Context (7 tools)

Project instructions via AGENTS.md and three-layer compression to keep context manageable.

```mermaid
graph LR
    CMD["AGENTS.md"] --> SysPrompt["System Prompt"]

    subgraph Compression["3-Layer Compression"]
        L1["Layer 1: Micro<br/>Trim old tool results<br/>Every turn"]
        L2["Layer 2: Auto<br/>LLM summarizes<br/>At 100K tokens"]
        L3["Layer 3: Manual<br/>/compact command<br/>On demand"]
    end

    Loop["agent_loop()"] --> L1
    L1 --> L2
    L3 --> Loop

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Loop existing
    class CMD,SysPrompt,L1,L2,L3 new
```

### Phase 5: Skills (8 tools)

Two-layer knowledge injection: lightweight summaries in the system prompt, full skill bodies loaded on demand.

```mermaid
graph LR
    subgraph SkillFiles["skills/ Directory"]
        CR["code-review/<br/>SKILL.md"]
        AB["agent-builder/<br/>SKILL.md"]
        MB["mcp-builder/<br/>SKILL.md"]
        PDF["pdf/<br/>SKILL.md"]
    end

    subgraph Injection["Two-Layer Injection"]
        L1["Layer 1: System Prompt<br/>Name + description<br/>~100 tokens each"]
        L2["Layer 2: On Demand<br/>Full SKILL.md body<br/>~2000 tokens"]
    end

    SkillFiles --> Loader["skills.py<br/>SkillLoader"]
    Loader --> L1
    Loader -->|"load_skill tool"| L2

    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class CR,AB,MB,PDF,Loader,L1,L2 new
```

### Phase 6: Planning (9 tools)

A single TaskManager for structured work: dependency graph, mutual-exclusion `in_progress`, and a stuck-item reminder. One `task` tool with action dispatch covers create / update / list / get / delete.

```mermaid
graph LR
    subgraph TaskSystem["TaskManager"]
        Task["task tool<br/>create / update / list / get / delete"]
        Mutex["Mutual exclusion<br/>(one in_progress)"]
        Nag["Stuck-item reminder<br/>(soft @ 8 rounds, hard @ 16)"]
    end

    Task --> Deps["Dependency graph<br/>blocked_by / blocks"]
    Task --> Mutex
    Nag -->|"inject reminder"| Loop["agent_loop()"]

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Loop existing
    class Task,Deps,Mutex,Nag new
```

### Phase 7: Subagent (10 tools)

Delegate *thinking*: spawn a child agent with a fresh message list and a restricted tool set. The child runs synchronously on the main thread; the parent gets back only the child's text summary. Trades wall-clock time for parent-context tokens.

```mermaid
graph LR
    Lead["Lead Agent Loop"]

    subgraph SubagentFlow["Subagent"]
        SA["subagent.py"]
        FreshCtx["Fresh Messages<br/>+ Tool Registry"]
        ChildLoop["Child agent_loop()"]
    end

    Lead -->|"run_subagent()"| SA
    SA --> FreshCtx --> ChildLoop
    ChildLoop -->|"text summary"| Lead

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Lead existing
    class SA,FreshCtx,ChildLoop new
```

### Phase 8: Background (12 tools)

Delegate *thinking without blocking*: run a subagent (the Phase-7 child loop) on a daemon thread. The agent loop drains a thread-safe mailbox at the top of each iteration, so the child's summary lands in the conversation when the model is ready for it. The child runs with `quiet=True` so its streamed tokens stay off the terminal — a single loop flag, not per-thread stdout routing.

```mermaid
graph LR
    Lead["Lead Agent Loop"]

    subgraph BackgroundFlow["Background"]
        BG["background.py"]
        Daemon["Daemon Thread<br/>run_subagent(quiet=True)"]
        Queue["Notification Mailbox"]
    end

    Lead -->|"background_run()"| BG
    BG --> Daemon
    Daemon -->|"summary on complete"| Queue
    Queue -->|"drain before LLM call"| Lead

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Lead existing
    class BG,Daemon,Queue new
```

### Phase 9: Teams (13 tools)

Named teammates that remember across tasks, coordinated by the lead hub-and-spoke. The lead `hire`s a teammate (a name + a role), `assign`s it a task that runs in the background on its own thread, and `wait`s to gather every teammate's report. Unlike a one-shot subagent, a teammate keeps its own message history *across assignments* — so it remembers earlier work and you can keep handing it follow-ups. Teammates never talk to each other; they report only to the lead. Each teammate's loop runs with `quiet=True`, so parallel work doesn't garble the lead's terminal — `wait` prints each `[name] ✓ …` report on the main thread as it lands. One `team` tool covers hire / assign / wait / status.

```mermaid
graph LR
    Lead["Lead Agent"]

    subgraph TeamLayer["team.py"]
        TmMgr["Team<br/>roster + reports mailbox"]
    end

    subgraph Teammates["Teammate Threads (each its own agent_loop)"]
        T1["Teammate A<br/>remembers across tasks"]
        T2["Teammate B<br/>remembers across tasks"]
    end

    Lead -->|"hire / assign / wait / status"| TmMgr
    TmMgr -->|"assign runs on a daemon thread"| T1 & T2
    T1 & T2 -->|"report on finish"| TmMgr
    TmMgr -->|"gathered reports"| Lead

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Lead existing
    class TmMgr,T1,T2 new
```

### Phase 10: Autonomous (13 tools)

The same team, made autonomous by flipping *push* to *pull*. In Phase 9 the lead hand-assigns each task to a named teammate and waits at an all-or-nothing barrier — so a free teammate can't grab the next task while another is busy. Phase 10 instead hands the team a *list* of tasks via the `team` tool's `run` action. The tasks go into a shared queue, and every teammate runs a pull-loop: grab the next free task, do it, grab the next — until the queue is empty. The team self-distributes and self-balances (a faster teammate naturally does more), and the run stops on an *objective* condition: the queue is empty. No new tool — `assign`/`wait` are replaced by `run`.

```mermaid
graph LR
    Lead["Lead Agent"] -->|"team(action=#quot;run#quot;, tasks=[...])"| Queue["Shared Task Queue<br/>(deque)"]

    subgraph Pull["Teammates pull in parallel"]
        T1["Teammate A<br/>work-loop"]
        T2["Teammate B<br/>work-loop"]
    end

    Queue -->|"popleft next task"| T1 & T2
    T1 & T2 -->|"reports"| Lead
    Queue -.->|"empty = done (objective stop)"| Lead

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Lead existing
    class Queue,T1,T2 new
```

### Phase 11: Workspace Isolation (14 tools)

Filesystem isolation — distinct from the *context* isolation a subagent already has (its own message history). The agent can create a git *worktree*: a separate working folder on its own branch, backed by the same repo, to try an experiment or an alternative implementation without touching the main workspace. Two worktrees are two independent directories — a file written in one can't touch the other. One `worktree` tool wraps the basic git commands: `create` (`git worktree add worktrees/<name> -b <name>`) and `list` (`git worktree list`). It never runs `git init` — isolation assumes an existing repo with a base commit, and returns a friendly error otherwise.

```mermaid
graph LR
    Lead["Lead Agent"] -->|"worktree create / list"| WM["isolation/worktree.py<br/>WorktreeManager"]

    subgraph Repo["Same repo, separate working trees"]
        Main["main workspace<br/>branch: main (untouched)"]
        WT1["worktrees/exp-a<br/>branch: exp-a"]
        WT2["worktrees/exp-b<br/>branch: exp-b"]
    end

    WM -->|"git worktree add"| WT1 & WT2

    classDef existing fill:#e0e0e0,stroke:#999,color:#333
    classDef new fill:#4caf50,color:#fff,stroke:#2e7d32
    class Lead,Main existing
    class WM,WT1,WT2 new
```

---

## Tool Reference

All 14 tools organized by phase of introduction.

| # | Tool | Phase | Module | Description |
|---|------|-------|--------|-------------|
| 1 | `bash` | 2 | `tools/bash.py` | Execute shell commands with safety blocking |
| 2 | `read_file` | 3 | `tools/files.py` | Read file contents with optional line range |
| 3 | `write_file` | 3 | `tools/files.py` | Create or overwrite files |
| 4 | `edit_file` | 3 | `tools/files.py` | Find-and-replace within files |
| 5 | `list_files` | 3 | `tools/files.py` | Glob pattern file listing |
| 6 | `search_files` | 3 | `tools/files.py` | Regex search across files |
| 7 | `compact` | 4 | `memory/compression.py` | Manually compress conversation context |
| 8 | `load_skill` | 5 | `knowledge/skills.py` | Load full skill body on demand |
| 9 | `task` | 6 | `planning/tasks.py` | Create / update / list / get / delete tasks (action-dispatched) with mutual-exclusion `in_progress`, dependency graph, and stuck-item nag |
| 10 | `subagent` | 7 | `parallel/subagent.py` | Spawn child agent with isolated context |
| 11 | `background_run` | 8 | `parallel/background.py` | Run a subagent in a background daemon thread |
| 12 | `check_background` | 8 | `parallel/background.py` | Check status of background tasks |
| 13 | `team` | 9 | `parallel/team.py` | Build and run a team of named, memory-keeping teammates. Phase 9 (push): `hire` / `assign` / `wait` / `status`. Phase 10 (pull): `assign`/`wait` are replaced by `run`, which loads a shared task queue the teammates pull from until empty |
| 14 | `worktree` | 11 | `isolation/worktree.py` | Create and list git worktrees — isolated working folders, each on its own branch (`create` / `list`) |
