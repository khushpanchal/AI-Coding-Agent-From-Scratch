# Phase 5 — Skills

**Split knowledge into a cheap index and an expensive body, and put a tool between them.**

Phase 4 gave the agent `AGENTS.md`, and it worked. So well, in fact, that you keep adding to it — a code review checklist, PDF handling notes, MCP conventions. And then you type `hi` and pay for all of it.

> New here? Start with the [project README](../README.md) and work forward from [phase 1](../phase-1-foundation/).

## The problem, in one picture

The system prompt is rebuilt and sent on **every single call**:

```
  SYSTEM PROMPT (sent on EVERY call, even for "hi")
  ┌────────────────────────────────────────────────┐
  │ base rules                                     │
  │ + AGENTS.md                                    │
  │ + code review guideline   (~2000 tok) ← unused │
  │ + PDF guideline           (~2000 tok) ← unused │  you pay for
  │ + MCP guideline           (~2000 tok) ← unused │  all of this
  └────────────────────────────────────────────────┘
```

The fix that solved repetition in phase 4 has become the thing that costs you. This is worth noticing as a pattern: **the solution to one context problem becomes the next context problem.** Phase 4 solved it for tool results; phase 5 solves it for instructions.

## The idea: two layers

Every piece of knowledge has two parts with wildly different sizes:

- **what it is** — a name and one line. Tiny. ~100 tokens.
- **how to do it** — the actual procedure. Large. ~2000 tokens.

You need the first one *always*, to know the capability exists. You need the second one *only* when you're actually doing that task. So store them together, load them separately.

```
                        DISK (skills/ — a convention, not code)
                        ┌──────────────────────────────────────┐
                        │ skills/code-review/SKILL.md          │
                        │  ---                                 │
                        │  name: code-review        ← FRONT    │
                        │  description: Review ...  ← MATTER   │
                        │  ---                                 │
                        │  # Code Review Skill ...  ← BODY     │
                        │ skills/pdf/SKILL.md                  │
                        │ skills/mcp-builder/SKILL.md          │
                        └──────────────┬───────────────────────┘
                                       │ scanned ONCE at startup
                                       ▼
                        ┌──────────────────────────────────────┐
                        │ SkillLoader (knowledge/skills.py)    │
                        │ {name: {description, body, path}}    │
                        │ two methods = two layers:            │
                        │   get_system_prompt_section() → index│
                        │   load(name)                  → body │
                        └───────┬──────────────────┬───────────┘
              LAYER 1           │                  │   LAYER 2
        always present,         │                  │  on demand,
        ~100 tok/skill          ▼                  ▼  ~2000 tok
        ┌──────────────────────────┐   ┌──────────────────────────┐
        │ SYSTEM PROMPT            │   │ ToolRegistry             │
        │ base + skill index       │   │  register(               │
        │      + AGENTS.md         │   │    LOAD_SKILL_SCHEMA,    │
        │ (separate arg, never     │   │    skills.load)          │
        │  stored in messages)     │   │  ← a BOUND METHOD        │
        └────────────┬─────────────┘   └────────────┬─────────────┘
                     └──────────┬───────────────────┘
                                ▼
                     ┌──────────────────────┐
                     │ agent_loop UNCHANGED │
                     │ byte-identical to    │
                     │ phase 4              │
                     └──────────────────────┘
```

## How a turn actually plays out

```
 turn 1   model sees: the INDEX only
          "code-review: Review code for quality, bugs, best practices"
                    │
                    ▼  decides it needs the detail
          emits tool_call: load_skill("code-review")
                    │
                    ▼
          dispatch → skills.load() → returns the full body
                    │
                    ▼
          appended as {"role": "tool", "content": <2000-token body>}
                                                   ▲
                              the body enters MESSAGES here —
                              NOT the system prompt

 turn 2   model sees: index + body-as-tool-result → does the review
```

**Where the body lands is the whole design.** It goes into `messages` as a tool result, not into the system prompt. That has a consequence worth tracing: tool results are exactly what phase 4's `micro_compact` blanks out once three newer ones exist. So a loaded skill body is **automatically garbage-collected** by a mechanism written one phase earlier, for a completely different reason.

That's two phases composing without either knowing about the other — the kind of thing that only happens when the seams are in the right place.

## The cost you're actually paying

Nothing is free; this trades one resource for another:

| | Before | After |
|---|---|---|
| Idle cost per skill | ~2000 tokens, every call | ~100 tokens, every call |
| Cost when you need it | 0 extra | **one extra model round-trip** |
| After use | still there forever | dropped once 3 newer tool results exist |

You buy a 20× reduction in idle cost and pay for it with latency at the moment of use. For knowledge that's rarely needed, that's a good trade. For knowledge needed on every single turn, it isn't — which is why `AGENTS.md` still exists and wasn't replaced.

## Skills are a convention, not a framework

```
skills/
└── <skill-name>/
    └── SKILL.md      ← YAML front matter (name, description) + markdown body
```

That's the entire specification. The loader is a 124-line file with a hand-rolled front-matter parser — deliberately no PyYAML dependency for something this simple.

Two directories are scanned, in order:

```
BUNDLED:  <repo>/skills    ← ships with the agent, found regardless of cwd
PROJECT:  <cwd>/skills     ← per-project skills
                              scanned second, so it OVERRIDES by name
```

Project-beats-bundled falls out of scan order — later writes win. No precedence logic needed.

## The description does all the work

The name is nearly cosmetic. The **description** is the only thing the model reads when deciding whether to load a skill, since the body is invisible until it does.

Notice too that `LOAD_SKILL_SCHEMA`'s own description contains a negative instruction:

> "Do NOT call this to answer questions like 'what skills are available' — the skill names and summaries are already in your context."

Without that line the model wastes a round-trip loading a skill just to tell you it exists. **Tool descriptions are where you prevent behaviour, not just enable it.**

## A known gap: there is no `unload_skill`

Once a body is loaded it rides along in `messages` until `micro_compact` happens to catch it. There is no way to say "done with that, drop it."

This ships as-is, and it's worth understanding rather than patching over: the cleanup path exists but it's *incidental* — it depends on three newer tool results showing up. Ask for a code review and then chat for twenty turns without using any tools, and you carry those 2000 tokens the whole way.

## Run it

```bash
mkdir -p /tmp/agent-demo5 && cd /tmp/agent-demo5
PYTHONPATH=/path/to/phase-5-skills \
  /path/to/phase-5-skills/venv/bin/python -m agent.cli
```

| Type this | What to watch for |
|---|---|
| `what skills do you have?` | it answers from the **index** — no `load_skill` call |
| `/inspect` | the system prompt holds names + descriptions only, no bodies |
| `review the code in calculator.py` | `[tool: load_skill]` → then the review |
| `/inspect` again | the body is now a **tool result** in `messages`, not in the system prompt |

That second `/inspect` is the whole phase. Two layers, two different places, one tool between them.

A note on the small local model: `qwen2.5:7b-instruct` sometimes loads the skill and then produces an empty final turn. That's model capability, not a code defect — the mechanism is visible in `/inspect` either way.

## What's missing

The agent can now pull in knowledge on demand, but it still has no memory of **what it is doing**. Ask for a five-step refactor and by step three the plan has been compacted away — because the plan lives in `messages`, and `messages` is exactly what compression rewrites. [Phase 6](../phase-6-planning/) moves that state somewhere compression can't reach.
