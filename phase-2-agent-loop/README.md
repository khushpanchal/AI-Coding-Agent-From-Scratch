# AI Coding Agent

**Build a CLI AI agent from scratch — one phase at a time.**

Learn how production AI coding agents work by building one yourself, progressively, from a simple chat REPL to a multi-agent system where teammates find their own work. Each phase adds one new capability while keeping everything from the previous phases working.

## Phases

| Phase | Branch | What You Build | Tools |
|-------|--------|---------------|-------|
| **1** | `phase-1-foundation` | CLI + Ollama provider + streaming chat | 0 |
| **2** | `phase-2-agent-loop` | Core agent while-loop + bash tool | 1 |
| **3** | `phase-3-file-tools` | File read/write/edit + glob/grep + sandboxing | 6 |
| **4** | `phase-4-smart-context` | 3-layer context compression + CLAUDE.md project instructions | 7 |
| **5** | `phase-5-skills` | Dynamic skill loading (two-layer knowledge injection) | 8 |
| **6** | `phase-6-planning` | In-memory task list with dependencies and stuck-item reminder | 9 |
| **7** | `phase-7-subagents` | Subagent — spawn child agent with isolated context | 10 |
| **8** | `phase-8-background` | Background — non-blocking subagents via daemon threads | 12 |
| **9** | `phase-9-teams` | Named teammates (memory carries across tasks) a lead hires, assigns, and waits on | 13 |
| **10** | `phase-10-autonomous` | Teammates pull from a shared task queue (push → pull) | 13 |
| **11** | `phase-11-isolation` | Git worktrees — an isolated folder + branch per experiment | 14 |

## Quick Start

Clone the repository, then `cd` into the project directory.

```bash
# Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
python -m agent.cli
```

## Use from any project (optional)

By default, you have to `cd` into this project to run the agent. To run `ai-coding-agent` from *any* directory:

```bash
# Run these once from the project root (after the Quick Start setup above).

# 1. Make the `agent` package importable from the venv's Python:
SITE=$(venv/bin/python -c 'import site; print(site.getsitepackages()[0])')
echo "$(pwd)" > "$SITE/agent.pth"

# 2. Create a wrapper command on your PATH:
mkdir -p ~/.local/bin
cat > ~/.local/bin/ai-coding-agent <<EOF
#!/usr/bin/env bash
export PYTHONDONTWRITEBYTECODE=1
exec $(pwd)/venv/bin/python -m agent.cli "\$@"
EOF
chmod +x ~/.local/bin/ai-coding-agent
```

Now from any directory:

```bash
cd ~/my-project
ai-coding-agent
```

`~/.local/bin` is on your `PATH` by default on most macOS/Linux setups. If `ai-coding-agent` isn't found, add `export PATH="$HOME/.local/bin:$PATH"` to your shell config and open a new terminal.

After editing the agent's source code, just rerun `ai-coding-agent` — Python re-reads the source on every invocation.

## Prerequisites

- **Python 3.10+**
- **Ollama** installed and running locally (`ollama serve`)
- A model pulled: `ollama pull qwen2.5:7b-instruct`

## Provider

This branch uses **Ollama** exclusively for local-only inference. No API keys required.

| Provider | Models | API Key |
|----------|--------|---------|
| **Ollama** | qwen2.5:7b-instruct | None (local) |

The model is hardcoded to `qwen2.5:7b-instruct`.

---

## Phase 1: Foundation

**Branch:** `phase-1-foundation`
**Concept:** Build the backbone — provider abstraction + streaming + CLI

This phase creates the foundation that every future phase builds on. The CLI uses Ollama for local inference and streams tokens in real-time for a responsive experience.

### Architecture

```
agent/
├── cli.py                  # Interactive REPL (python -m agent.cli)
├── core/
│   ├── config.py           # Ollama config (hardcoded)
│   └── streaming.py        # Real-time token printer
└── providers/
    ├── base.py             # Abstract BaseProvider interface
    ├── registry.py         # Provider factory (returns Ollama)
    └── ollama.py           # Ollama provider implementation
```

### What You Learn

- How to design a provider abstraction layer
- How streaming works with Ollama's official Ollama Python SDK
- Building a CLI REPL with conversation history

### Commands

```
/help           — Show available commands
/clear          — Clear conversation history
/model          — Show current provider and model
/inspect        — Show every LLM call's input and output
/clear-inspect  — Clear inspector records (independent of /clear)
/quit           — Exit
```

## The Core Insight

Every AI coding agent follows the same pattern:

```
while True:
    response = call_llm(messages)
    if response.has_tool_calls:
        results = execute_tools(response.tool_calls)
        messages.append(results)
    else:
        return response
```

The loop never changes. Each phase adds a new mechanism *around* it — tools, planning, compression, teams — without modifying the fundamental pattern. That is the core idea of the whole project.

---

## Phase 2: Agent Loop

**Branch:** `phase-2-agent-loop`
**Concept:** The while-loop that turns a chatbot into an agent

Phase 1 was a chatbot — it sends your message, gets a response, done. Phase 2 adds the **agent loop**: if the model wants to use a tool, we execute it and feed the result back. The model keeps looping until it's satisfied.

### What's New

```
agent/
├── core/
│   └── loop.py             # The agent loop (while True → call → execute → loop)
└── tools/
    ├── registry.py          # ToolRegistry — register & dispatch tools by name
    ├── bash.py              # Bash tool — run shell commands
    └── safety.py            # Dangerous command blocking + output truncation
```

### How the Loop Works

```python
while True:
    response = provider.chat_stream(messages, tools)
    messages.append(response)

    if no tool_calls in response:
        return  # Agent is done

    for each tool_call:
        result = registry.dispatch(tool_call.name, tool_call.arguments)
        messages.append(result)
    # Loop continues — model sees the tool results
```

### Safety Guards

- **Dangerous command blocking** — `rm -rf /`, `sudo rm`, `shutdown`, fork bombs, etc. are blocked before execution
- **60-second timeout** — Commands that hang are killed
- **Output truncation** — Output over 50K characters is truncated (keeps first and last half)
- **Iteration limit** — Agent stops after **50 LLM calls** to prevent infinite loops. Tool calls within a single LLM round are uncapped.

## Phase 3: File Tools

**Branch:** `phase-3-file-tools`
**Concept:** Give the agent eyes and hands for the filesystem

The agent can now read, write, edit, search, and list files — all sandboxed to the workspace directory. No path traversal escapes allowed.

### What's New

| Tool | What It Does |
|------|-------------|
| `read_file` | Read file contents with line numbers (supports offset/limit) |
| `write_file` | Create or overwrite files (auto-creates parent dirs) |
| `edit_file` | Exact string replacement (must match uniquely) |
| `list_files` | Glob pattern matching (`**/*.py`, `src/*.ts`) |
| `search_files` | Regex search across file contents (like grep) |

### Path Sandboxing

Every file operation goes through `safe_path()`:

```python
def safe_path(file_path: str) -> Path:
    resolved = (WORKSPACE / file_path).resolve()
    if not resolved.is_relative_to(WORKSPACE):
        raise ValueError("Path escapes workspace!")
    return resolved
```

This prevents the agent from reading `/etc/passwd` or writing to `../../.ssh/authorized_keys`.

## Phase 4: Smart Context

**Branch:** `phase-4-smart-context`
**Concept:** Never run out of context — compression + CLAUDE.md

Without context management, long sessions crash when the context window fills up. This phase adds three-layer compression and CLAUDE.md project instructions.

### Three-Layer Compression

| Layer | Trigger | What It Does |
|-------|---------|-------------|
| **Micro** | Every turn | Replaces old tool results (older than last 3) with `[Previous tool result]` placeholders |
| **Auto** | Tokens > 100K | Asks the LLM to summarize, replaces all messages with the summary |
| **Manual** | `compact` tool or `/compact` command | Same as auto, but triggered explicitly |

### New Commands

```
/compact   — Manually compress context
/tokens    — Show estimated token count
/debug     — Dump raw message history (role + first 80 chars)
```

### CLAUDE.md — Project Instructions

Drop a `CLAUDE.md` file in your project root to give the agent custom rules, conventions, and context. The agent reads it automatically at session start and injects it into the system prompt.

```
project/
├── CLAUDE.md          ← project-level instructions (loaded first)
├── ../CLAUDE.md       ← parent directory instructions (also loaded)
└── ~/.claude/CLAUDE.md ← user-level defaults (loaded last)
```

**Lookup order:** walks up from the workspace directory, then checks `~/.claude/CLAUDE.md`. All files found are concatenated (nearest first).

Example `CLAUDE.md`:
```markdown
# Project Rules
- Use Python 3.12+ features
- Always run tests before committing
- Follow Google docstring style
```

### What's New in This Phase

```
agent/
├── memory/
│   ├── claude_md.py        # CLAUDE.md discovery and loading
│   └── compression.py      # Three-layer context compression
```

## Phase 5: Skills

**Branch:** `phase-5-skills`
**Concept:** Load knowledge on demand, not upfront

Putting all knowledge in the system prompt wastes tokens. Skills use a two-layer injection pattern: names are always visible (~100 tokens each), full content loads only when needed (~2000 tokens).

### How It Works

```
skills/
├── code-review/SKILL.md     # Code review expertise
├── agent-builder/SKILL.md   # Agent design patterns
└── pdf/SKILL.md             # PDF manipulation
```

Each SKILL.md has YAML frontmatter:
```yaml
---
name: code-review
description: Review code for quality, bugs, and best practices.
---
(full skill body here)
```

### Two-Layer Injection

| Layer | When | Token Cost |
|-------|------|-----------|
| **Layer 1** (system prompt) | Always present | ~100 per skill (name + description only) |
| **Layer 2** (tool result) | On demand via `load_skill` | ~2000 per skill (full body) |

## Phase 6: Planning

**Branch:** `phase-6-planning`
**Concept:** An agent without a plan drifts — give it structure

One unified `TaskManager` that combines a checklist, a dependency graph, and a stuck-item reminder.

### TaskManager (In-Memory)

Held in memory by `TaskManager`. Survives context compression (lives outside the message list); resets on restart or `/clear`.

- **One tool, five actions** — `task` with `action="create" | "update" | "list" | "get" | "delete"`. One schema in the model's tool list, not five.
- **Statuses** — `[ ]` pending, `[>]` in_progress, `[x]` completed
- **Mutual exclusion** — Max 1 task `in_progress` at a time (forces sequential focus). Setting a new task in_progress demotes any other in_progress task to pending.
- **Dependency graph** — `blocked_by` / `blocks` with bidirectional linking. A task whose blockers aren't completed cannot be started.
- **Auto-unblock** — Completing a task implicitly unblocks dependents (filtered at read time, not eagerly written).
- **Per-task age reminder** — soft prompt after 8 rounds in_progress, stronger one at 16 rounds. Wording is completion-neutral: suggests splitting the task or continuing before offering completion, so the model isn't pressured to tick the box prematurely.

## Phase 7: Subagent

**Branch:** `phase-7-subagents`
**Concept:** Delegate *thinking* — spawn a child agent with isolated context

Spawn a child agent with `messages=[]`. It works independently and returns only a text summary. The parent's context stays clean.

```
Parent context: [... 50 messages ...]
  → spawn subagent("analyze src/auth/")
  → Child starts fresh: [user: "analyze src/auth/"]
  → Child works: reads files, runs grep, 12 tool calls
  → Child returns: "Found 3 auth modules: ..."
Parent context: [... 51 messages ...] ← only the summary added
```

Two types:
- **`explore`** — Read-only tools (bash, read_file, list_files, search_files)
- **`general`** — Full tools including write/edit

## Phase 8: Background

**Branch:** `phase-8-background`
**Concept:** Delegate *thinking, without blocking* — run a subagent on a daemon thread

Phase 7's `subagent` blocks the parent until the child returns. Phase 8 runs the *same* child agent loop on a daemon thread, so the parent keeps working and the summary is injected when it's ready.

```
Agent: background_run("summarize the auth module")  → "Background subagent #1 started"
Agent: (keeps working on the foreground task)
[Background task completed]  → child's summary injected before next LLM call
```

### How it composes with Phase 7

`subagent` and `background_run` spawn the **same** isolated child agent — the only difference is whether the parent waits.

| | Foreground (blocks) | Background (fire-and-forget) |
|---|---|---|
| **Shell command** | `bash` | — (`bash` is fast; nothing to background) |
| **Subagent (LLM)** | `subagent` (Phase 7) | `background_run` (Phase 8) |

- Use `subagent` when the **next step needs the result** — block, get the summary inline, use it.
- Use `background_run` when there's **independent foreground work to overlap** — the summary arrives on its own.

A backgrounded subagent — a child loop on a thread — is just a *name* and *memory across tasks* away from being a **Phase 9 teammate**.

## Phase 9: Teams

**Branch:** `phase-9-teams`
**Concept:** When one agent isn't enough — named teammates with their own memory

A *teammate* is a background subagent (Phase 8) that also has a **name**, a **role**, and a **memory that carries across assignments**. The lead coordinates hub-and-spoke: it `hire`s teammates, `assign`s each a task (which runs on its own daemon thread), and `wait`s to gather their reports. Teammates never talk to each other — they report only to the lead. Each teammate's loop runs with `quiet=True` (Phase 8's flag), so concurrent work doesn't garble the terminal; `wait` prints each `[name] ✓ …` report on the main thread as it lands.

### The 7 → 8 → 9 progression

Each phase adds exactly one property:

| Phase | What you can do | New property |
|-------|----------------|--------------|
| 7 subagent | delegate once and **wait** | isolation |
| 8 background | delegate once and **don't wait** | concurrency |
| 9 team | delegate **repeatedly** to the **same named** worker who **remembers** | identity + memory |

### The `team` tool

One tool, action-dispatched:

```
hire    — add a teammate (name + role)
assign  — give a teammate a task; runs in the background
wait    — block until all working teammates finish, gather their reports
status  — show the roster and who's working on what
```

### New Commands

```
/team    — Show the team roster and who's working
```

> **⚠️ Running teammates in parallel (Ollama concurrency)**
>
> Ollama processes one request at a time per model by default (`OLLAMA_NUM_PARALLEL=1`), so the lead and a teammate that hit the model at the same moment will *queue* — the Phase 9 test looks stalled between `[teammate tester: working]` and `[teammate tester: finished]`. Raise `OLLAMA_NUM_PARALLEL` to at least the number of agents running at once (2 here: lead + one teammate), set where your Ollama runs:
>
> - **macOS menubar app:** `launchctl setenv OLLAMA_NUM_PARALLEL 2`, then quit and relaunch Ollama so the new server inherits it.
> - **`ollama serve` in a terminal:** `OLLAMA_NUM_PARALLEL=2 ollama serve`
>
> More teammates → set it higher (e.g. `4`). RAM scales with `OLLAMA_NUM_PARALLEL × OLLAMA_CONTEXT_LENGTH`, so don't exceed what your machine can hold. See the [Ollama FAQ](https://docs.ollama.com/faq) for the current method.

## Phase 10: Autonomous

**Branch:** `phase-10-autonomous`
**Concept:** The same team, made autonomous by flipping push to pull

In Phase 9 the lead *pushes*: it hand-assigns each task to a named teammate and waits at an all-or-nothing barrier — so a free teammate can't grab the next task while another is busy. Phase 10 flips this to *pull*: the lead hands the team a **list** of tasks via the `team` tool's `run` action. The tasks go into a shared queue, and every teammate runs a pull-loop:

```
grab next free task → do it → grab next → … → queue empty → done
```

The team self-distributes and self-balances (a faster teammate naturally pulls more tasks), and the run stops on an **objective** condition: the queue is empty — not the model's subjective "I think I'm done."

### Push vs Pull

| | Phase 9 (push) | Phase 10 (pull) |
|---|---|---|
| Who decides who does what | the lead, up front | the free teammate, at runtime |
| A free worker grabs the next task | no (blocked at `wait`) | yes (pulls from the queue) |
| Stop condition | lead calls `wait` | queue empty |

No new tool — the `team` tool's `assign`/`wait` are replaced by `run`.

## Phase 11: Workspace Isolation

**Branch:** `phase-11-isolation`
**Concept:** Try something in a separate folder without touching the main workspace

This is **filesystem** isolation — distinct from the **context** isolation a subagent already has (its own message history). The agent can create a git *worktree*: a separate working folder on its own branch, backed by the same repo. Two worktrees are two independent directories — a file written in one can't touch the other, and `main` stays untouched.

```
worktrees/              # created by `git worktree add`
├── exp-a/              # branch: exp-a
└── exp-b/              # branch: exp-b
```

### The `worktree` tool

Two actions, wrapping the basic git commands:

```
create <name>  →  git worktree add worktrees/<name> -b <name>
list           →  git worktree list
```

It never runs `git init` — isolation assumes you're already in a git repo with a base commit (it returns a friendly error otherwise). Setting up the repo is a deliberate manual prerequisite, so the agent never touches git history on a directory you didn't mean it to.

### New Commands

```
/worktrees   — List git worktrees (isolated workspaces)
```

---

## Tool Count Progression

| Phase | Tools | New Tools Added |
|-------|-------|----------------|
| 1 | 0 | — (chat only) |
| 2 | 1 | bash |
| 3 | 6 | read_file, write_file, edit_file, list_files, search_files |
| 4 | 7 | compact |
| 5 | 8 | load_skill |
| 6 | 9 | task |
| 7 | 10 | subagent |
| 8 | 12 | background_run, check_background |
| 9 | 13 | team (one tool — hire / assign / wait / status) |
| 10 | 13 | — (the `team` tool's assign/wait become `run`; no new tool) |
| 11 | 14 | worktree (one tool — create / list) |

## All CLI Commands

```
/quit           — Exit
/clear          — Clear conversation history
/model          — Show current provider and model
/compact        — Manually compress context
/tokens         — Show estimated token count
/tasks          — Show task board
/team           — Show team roster and who's working
/worktrees      — List git worktrees (isolated workspaces)
/debug          — Dump raw message history (role + first 80 chars)
/inspect        — Show every LLM call's input and output
/clear-inspect  — Clear inspector records (independent of /clear)
/help           — Show this help
```

## Final Architecture

```
agent/
├── cli.py                    # REPL + all commands (12 commands, 14 tools)
├── core/
│   ├── config.py             # Ollama config (hardcoded)
│   ├── loop.py               # Agent loop + pre-LLM pipeline
│   └── streaming.py          # Real-time token printer
├── providers/                # Ollama (local)
│   ├── base.py, registry.py, ollama.py
├── tools/                    # Core tools
│   ├── registry.py, bash.py, files.py, safety.py
├── memory/                   # Context management
│   ├── claude_md.py, compression.py
├── planning/                 # Planning systems
│   └── tasks.py
├── knowledge/                # Skill system
│   └── skills.py
├── parallel/                 # Concurrency + multi-agent
│   ├── subagent.py, background.py, team.py
└── isolation/                # Workspace isolation
    └── worktree.py
skills/
├── code-review/SKILL.md
├── pdf/SKILL.md
├── mcp-builder/SKILL.md
└── agent-builder/SKILL.md
```

---

## Summary: What You Learn

| Phase | Key Concept | Takeaway |
|-------|------------|----------|
| 1 | Provider + streaming | Local Ollama provider with streaming from the start |
| 2 | Agent loop | while-loop + tool dispatch = agent |
| 3 | File tools | Sandbox everything, search is as important as read/write |
| 4 | Context management | CLAUDE.md project instructions + three-layer compression |
| 5 | Skills | Two-layer injection — summaries in system prompt, full content on demand |
| 6 | Planning | One in-memory task list — dependencies, mutual-exclusion `in_progress`, and a stuck-item reminder, behind a single action-dispatched tool |
| 7 | Subagent | Spawn child agent with isolated context — saves parent tokens, not wall time |
| 8 | Background | Daemon-thread shell commands — saves wall time, not tokens |
| 9 | Teams | Named teammates with their own memory — lead hires, assigns, waits (push) |
| 10 | Autonomy | Teammates pull from a shared queue and self-distribute (push → pull) |
| 11 | Isolation | A git worktree gives an experiment its own folder + branch; main stays untouched |

The agent loop from Phase 2 is the same loop running in Phase 11. Everything else is just tools, knowledge, and infrastructure *around* it.
