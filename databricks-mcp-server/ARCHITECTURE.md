# Databricks MCP Server — Architecture

> Illustrative overview of how the MCP client, server, and `databricks-tools-core` fit together. This diagram is a high-level sketch and may not enumerate every tool module.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              MCP Client (Claude Code / Cursor / …)          │
│                                                             │
│  MCP Tools (actions)                                        │
│  └── .mcp.json ──► databricks server                        │
└──────────────────────────────┬──────────────────────────────┘
                               │ MCP Protocol (stdio or http)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              databricks-mcp-server (FastMCP)                │
│                                                             │
│  tools/sql.py ──────────────┐                               │
│  tools/unity_catalog.py ────┼──► @mcp.tool decorators       │
│  tools/user.py ─────────────┘                               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Python imports
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   databricks-tools-core                     │
│                                                             │
│  sql/  unity_catalog/  auth.py  identity.py  client.py      │
└──────────────────────────────┬──────────────────────────────┘
                               │ Databricks SDK
                               ▼
                    ┌─────────────────────┐
                    │  Databricks         │
                    │  Workspace          │
                    └─────────────────────┘
```
