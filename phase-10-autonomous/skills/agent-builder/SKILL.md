---
name: agent-builder
description: Design and build AI agents with tool-calling, planning, and multi-agent patterns.
---

# Agent Builder Skill

When designing or building AI agents, follow these principles:

## Core Architecture

Every agent follows the same loop:
```
while True:
    response = call_llm(messages, tools)
    if has_tool_calls(response):
        results = execute(response.tool_calls)
        messages.append(results)
    else:
        return response
```

## Design Principles

1. **Start minimal** — Begin with one tool (bash), add more only when needed
2. **Tools are a dispatch map** — `{name: handler}`. Adding a tool shouldn't change the loop.
3. **Safety first** — Sandbox file paths, block dangerous commands, set timeouts
4. **Context management** — Compress old tool results, save transcripts
5. **Plan before acting** — Use a task list for multi-step work

## Common Patterns

- **Provider abstraction** — Support multiple LLM providers through a unified interface
- **Streaming** — Always stream responses for better UX
- **Subagents** — Spawn child agents with fresh context for isolated tasks
- **Persistent state** — Store tasks/state on disk to survive context compression
- **Background execution** — Run long commands in daemon threads, notify on completion

## Anti-Patterns

- Don't change the agent loop for every new feature
- Don't put all knowledge in the system prompt (use skills/on-demand loading)
- Don't let agents run without iteration limits
- Don't skip path sandboxing for file tools
