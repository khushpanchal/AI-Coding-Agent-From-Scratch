---
name: mcp-builder
description: Build MCP (Model Context Protocol) servers that expose tools, resources, and prompts to AI agents.
---

# MCP Builder Skill

Build servers that follow the Model Context Protocol — a standard for connecting AI agents to external tools and data.

## MCP Primitives

| Primitive | Purpose | Example |
|-----------|---------|---------|
| **Tools** | Functions the agent can call | `run_query`, `send_email` |
| **Resources** | Read-only data the agent can access | `db://users`, `file://config.yaml` |
| **Prompts** | Reusable prompt templates | `summarize`, `review-code` |

## Python Server (using `mcp` SDK)

```python
# server.py
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

app = Server("my-server")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="greet",
            description="Greet someone by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to greet"}
                },
                "required": ["name"],
            },
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "greet":
        return [TextContent(type="text", text=f"Hello, {arguments['name']}!")]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## TypeScript Server (using `@modelcontextprotocol/sdk`)

```typescript
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server({ name: "my-server", version: "1.0.0" }, {
  capabilities: { tools: {} },
});

server.setRequestHandler("tools/list", async () => ({
  tools: [{
    name: "greet",
    description: "Greet someone by name",
    inputSchema: {
      type: "object",
      properties: { name: { type: "string" } },
      required: ["name"],
    },
  }],
}));

server.setRequestHandler("tools/call", async (request) => {
  if (request.params.name === "greet") {
    return { content: [{ type: "text", text: `Hello, ${request.params.arguments.name}!` }] };
  }
  throw new Error(`Unknown tool: ${request.params.name}`);
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

## Adding Resources

```python
@app.list_resources()
async def list_resources():
    return [Resource(uri="config://app", name="App Config", mimeType="application/json")]

@app.read_resource()
async def read_resource(uri: str):
    if uri == "config://app":
        return json.dumps({"debug": True, "version": "1.0"})
```

## Common Patterns

### External API Integration
```python
import httpx

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "fetch_weather":
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.weather.com/{arguments['city']}")
            return [TextContent(type="text", text=resp.text)]
```

### Database Access
```python
import sqlite3

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "query_db":
        conn = sqlite3.connect("data.db")
        rows = conn.execute(arguments["sql"]).fetchall()
        return [TextContent(type="text", text=json.dumps(rows))]
```

## Testing

```bash
# Test with MCP Inspector
npx @anthropics/mcp-inspector python server.py

# Register with Claude Code
# Add to ~/.claude/mcp.json:
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

## Tips

- Keep tools focused — one tool per action
- Return structured data (JSON) for tools that query data
- Use resources for read-only data the agent might need
- Test with the MCP Inspector before registering
- Handle errors gracefully — return error messages, don't crash
