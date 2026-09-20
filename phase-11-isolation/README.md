# Phase 11 — Workspace Isolation

**Context isolation was never filesystem isolation. Give each experiment its own folder.**

Four phases of concurrency work gave every worker its own `messages`, its own tools, its own system prompt. None of that stopped two workers from writing to the same file.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## The gap you've been living with

```
  CONTEXT isolation  (phases 7-10)      FILESYSTEM isolation  (phase 11)
  ──────────────────────────────        ────────────────────────────────
  each worker gets its own `messages`   each worker gets its own DIRECTORY
  → can't pollute each other's          → can't overwrite each other's
    reasoning                              files
  ✓ solved in phase 7                   ✗ phase 9/10 teammates ALL shared
                                          one folder
```

Phase 10's demo was safe by luck: four tasks that happened to write four different filenames. Point two workers at the same module and they'll clobber each other with no warning and no error.

There is a second motivation, and it may be the more compelling one: **comparing two implementations.** You want approach A and approach B side by side, both on disk, both runnable, at the same time. Git branches can't do that — one working tree, one branch checked out. Git *worktrees* can.

## What a worktree actually is

```
  demo/                    ← main worktree, branch `main`        ┐
    .git/                  ← ONE object database                 │ shared
    calculator.py                                                │ history
    worktrees/                                                   │
      approach-a/          ← full checkout, branch `approach-a`  │ 3 branches
        calculator.py        its own independent file            │ 2 extra
      approach-b/          ← full checkout, branch `approach-b`  ┘ folders
        calculator.py
```

Three branches, three working directories, **one repository**. Edit `worktrees/approach-a/calculator.py` and nothing in `main` moves. Commit in either and both land in the same object database, so you can diff and merge across them normally.

That's the whole feature. It's been in git since 2015 and most developers never touch it.

## The implementation is deliberately thin

`isolation/worktree.py` is 106 lines and wraps exactly two git commands:

```
  create  →  git worktree add worktrees/<name> -b <name>
  list    →  git worktree list
```

Plus one guard:

```
  git rev-parse --is-inside-work-tree
      └─ not a repo? return a friendly error telling YOU to run `git init`
```

**The agent never runs `git init` itself** — and that restraint is a design decision worth noticing. Initialising a repository in a directory the user didn't intend as one is the kind of "helpful" action that's a nuisance to undo. Isolation assumes an existing repo with a base commit; if that assumption fails, the tool says so instead of fixing it for you.

Same principle as phase 3's `safe_path`, pointed in the opposite direction: there, the code refused to let the model reach outside the workspace. Here, the code refuses to create state the user didn't ask for. **Both are the agent declining to exceed its brief.**

## The architecture

```
 ┌──── MAIN THREAD ───────────────────────────────────────────────────┐
 │ agent_loop — UNCHANGED for the THIRD phase running                 │
 │   dispatch("worktree", {action:"create", name:"approach-a"})       │
 │   dispatch("worktree", {action:"create", name:"approach-b"})       │
 │   dispatch("worktree", {action:"list"})                            │
 └────────────────────────────────┬───────────────────────────────────┘
                                  ▼
 ┌──── WorktreeManager (isolation/worktree.py) ───────────────────────┐
 │  _base = Path(base_dir or ".").resolve()   ◄ cwd at construction   │
 │                                                                     │
 │  _create(name)                                                      │
 │    ├ guard: name required                                           │
 │    ├ guard: _is_git_repo()                                          │
 │    │    └ if not → "run `git init` and make a base commit"         │
 │    └ _git("worktree", "add", f"worktrees/{name}", "-b", name)      │
 │  _list()  → git worktree list                                       │
 │  _git(*args) → subprocess.run(["git", *args], cwd=_base)           │
 └─────────────────────────────────────────────────────────────────────┘
```

## An honest gap: the seam is dangling

**`WorktreeManager` is never wired to `Team`.** No teammate runs inside a worktree. The model is handed a tool that creates isolated folders and told in the system prompt to do experimental work there — but nothing enforces it, and a teammate's working directory is still the one you launched from.

So this phase delivers the *mechanism* for filesystem isolation without connecting it to the concurrency that needed it. That's how the source ships, and it's left as the obvious exercise. Connecting it is not trivial, either — there's a real subtlety waiting:

> `WorktreeManager` resolves `.` at **construction** time, while `WORKSPACE` in `tools/files.py` is frozen from `os.getcwd()` at **import** time. Today they agree, because both happen at startup in the same directory. Run a teammate inside a worktree and they diverge — the file tools would still be sandboxed to the *original* workspace, and the teammate couldn't write to its own folder.

Two different answers to "where am I," which is fine until something moves.

## Run it

**This phase needs a git repository with at least one commit.** That's the setup step:

```bash
mkdir -p /tmp/agent-demo-11 && cd /tmp/agent-demo-11
git init -q
printf 'def add(a,b):\n    return a+b\n' > calculator.py
git add -A && git commit -q -m "base"

PYTHONPATH=/path/to/phase-11-isolation \
  /path/to/phase-11-isolation/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `create a worktree called approach-a` | `[tool: worktree] action=create` |
| `create a worktree called approach-b` | a second one |
| `list the worktrees` | three entries — `main` plus both branches |
| `ls worktrees/` *(another terminal)* | two real directories, each a full checkout |
| `git branch` *(another terminal)* | three branches |
| edit `worktrees/approach-a/calculator.py` | `main`'s copy is **untouched** |

**To see the guard:** run the agent from a directory that isn't a git repo and ask for a worktree. You get a friendly instruction, not a stack trace and not a surprise `git init`.

> Production agents typically name this folder `.worktrees` so editors hide it. It's `worktrees` here so you can see it.

## Commands

```
/worktrees    List active worktrees
```

## You've reached the end of the ladder

Eleven phases, 14 tools, from a chat REPL to a multi-agent system with isolated workspaces. The [project README](../README.md) has the full map.

What stayed constant is more interesting than what changed:

- **`messages` is still the only memory.** Every single thing added — tools, skills, tasks, teammates, worktrees — either lives in that list or deliberately lives outside it for a stated reason.
- **The system prompt and tool schemas are still separate arguments**, rebuilt every call, never stored.
- **`agent_loop` is one function.** The parent, every subagent, every background child, and every teammate all run it. They differ only in the arguments passed.
- **The loop changed twice in eleven phases.** The pre-call pipeline grew (phases 4, 6, 8) and `quiet` was added (phase 8). Phases 9, 10 and 11 changed it **zero** times.

## What a production agent would still need

Worth knowing what you *don't* have, because the gaps are as instructive as the build:

**Semantic editing.** `edit_file` is literal string replacement. Real coding agents drive a language server — renaming a symbol across a codebase shouldn't mean reading every file. This is the largest single gap.

**Self-verification.** The agent never runs what it writes. No tests, no syntax check, no lint. Phase 10 generated four Python files and validated none of them.

**Undo.** Git appears here for worktrees, but never as a safety net — no auto-commit before a risky edit, no revert on failure.

**Human approval.** The bash blocklist is the only gate. No "may I run this?", no diff-before-apply, no dry run.

**Durability.** Task board, team roster, every teammate's memory, the mailbox — all RAM. Restart and eleven phases of state evaporate.

**Budget control.** No token accounting, no spend cap, and nothing stopping a confused model from spawning unbounded background threads.

**Parallel tool execution.** Even here, the loop dispatches tools strictly one at a time. The [streaming lab](../lab-streaming-tool-execution/) shows what's possible — and porting it into this phase's `core/loop.py` is genuinely about twenty lines. **That's the best final exercise in the project.**
