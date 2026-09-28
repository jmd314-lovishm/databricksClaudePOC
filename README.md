# databricksClaudePOC

A containerised [MCP](https://modelcontextprotocol.io) server that exposes a
Databricks workspace to an MCP client (Claude Code, Claude Desktop, or any other
MCP-capable agent), scoped to **analysing data that already lives in Unity
Catalog**.

Built on [FastMCP](https://github.com/jlowin/fastmcp) and the Databricks Python
SDK. Derived from the Databricks
[ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit); see
[NOTICE.md](NOTICE.md) and [LICENSE.md](LICENSE.md).

## Repository layout

```
databricksClaudePOC/
├── Dockerfile                    # Multi-stage production image
├── .dockerignore
├── .gitignore
├── .env.example                  # Variable names only — no values
├── LICENSE.md
├── NOTICE.md
├── README.md
├── databricks-mcp-server/        # MCP server: FastMCP tool registrations
│   ├── databricks_mcp_server/
│   │   ├── server.py             # FastMCP instance + tool registration
│   │   ├── middleware.py
│   │   ├── manifest.py
│   │   └── tools/                # sql.py, unity_catalog.py, user.py
│   ├── run_server.py             # Entry point
│   ├── healthcheck.py            # Container HEALTHCHECK probe
│   ├── pyproject.toml
│   └── tests/
└── databricks-tools-core/        # Reusable Databricks operations library
    ├── databricks_tools_core/    # sql/, unity_catalog/, auth.py, identity.py
    ├── pyproject.toml
    ├── requirements.txt
    └── tests/
```

`databricks-mcp-server` depends on `databricks-tools-core` as a local path
dependency. `databricks-tools-core` is not published to PyPI, so both packages
are always installed together from this tree.

## Tool surface

15 tools across three modules.

| Module | Tools |
|---|---|
| `sql` | `execute_sql`, `execute_sql_multi`, `manage_warehouse`, `get_table_stats_and_schema`, `get_volume_folder_details` |
| `unity_catalog` | `manage_uc_objects`, `manage_uc_grants`, `manage_uc_storage`, `manage_uc_connections`, `manage_uc_tags`, `manage_uc_security_policies`, `manage_uc_monitors`, `manage_uc_sharing`, `manage_metric_views` |
| `user` | `get_current_user` |

Deployment and serving surfaces (jobs, pipelines, apps, model serving, Genie,
vector search, Lakebase, AI/BI dashboards, clusters) are deliberately excluded —
this server is for reading and analysing catalog data.

## Configuration

All configuration is supplied through environment variables. **No credentials
are baked into the image.** Copy [.env.example](.env.example) to `.env` and fill
it in; `.env` is git-ignored and excluded from the Docker build context.

| Variable | Required | Purpose |
|---|---|---|
| `DATABRICKS_HOST` | yes | Workspace URL, e.g. `https://<workspace>.cloud.databricks.com` |
| `DATABRICKS_CLIENT_ID` | option A | Service principal application ID (OAuth M2M) |
| `DATABRICKS_CLIENT_SECRET` | option A | Service principal OAuth secret |
| `DATABRICKS_TOKEN` | option B | Personal access token |
| `DATABRICKS_CONFIG_PROFILE` | no | Profile from `~/.databrickscfg` (local use only) |
| `DATABRICKS_MCP_DEBUG` | no | Any non-empty value enables debug logging on stderr |
| `MCP_TRANSPORT` | no | `stdio` (default), `http`, `sse`, or `streamable-http` |
| `MCP_HOST` | no | Bind address for networked transports (default `0.0.0.0`) |
| `MCP_PORT` | no | Bind port for networked transports (default `8000`) |

Supply **either** option A (service principal, recommended for containers) **or**
option B (PAT). Authentication is resolved by the Databricks SDK's standard
credential chain.

No warehouse ID is required — `manage_warehouse` discovers an appropriate SQL
warehouse, and the SQL tools accept an explicit `warehouse_id` when you want to
pin one.

## Build

```bash
docker build -t databricks-claude-mcp:local .
```

The build is architecture-independent: all dependencies are pure-Python wheels
or provide wheels for both `linux/amd64` and `linux/arm64`. To target a specific
platform explicitly:

```bash
docker build --platform linux/amd64 -t databricks-claude-mcp:local .
```

## Run

### stdio (default)

stdio is the transport MCP clients use to launch a server as a subprocess. The
container must be given an attached stdin:

```bash
docker run --rm -i --env-file .env databricks-claude-mcp:local
```

Without `-i` the server reads EOF on stdin and exits immediately — that is
correct behaviour for stdio, not a failure.

To register with Claude Code:

```bash
claude mcp add databricks -- docker run --rm -i --env-file .env databricks-claude-mcp:local
```

### HTTP

For a long-running deployment:

```bash
docker run --rm -p 8000:8000 \
  --env-file .env \
  -e MCP_TRANSPORT=http \
  databricks-claude-mcp:local
```

The MCP endpoint is then served at `http://localhost:8000/mcp`.

The image declares a `HEALTHCHECK` that runs
[healthcheck.py](databricks-mcp-server/healthcheck.py): a no-op under stdio
(there is no socket to probe), and a probe of `/mcp` under a networked
transport. Any HTTP response counts as healthy — MCP answers an unadorned `GET`
with a 4xx, which still proves the listener is up. Only a connection-level
failure is unhealthy.

```bash
docker inspect --format '{{.State.Health.Status}}' <container>
```

## Local development

```bash
uv venv && uv pip install -e ./databricks-tools-core -e ./databricks-mcp-server
python databricks-mcp-server/run_server.py
```

Unit tests:

```bash
uv pip install pytest pytest-asyncio
python -m pytest databricks-mcp-server/tests --ignore=databricks-mcp-server/tests/integration
```

The integration tests under `tests/integration/` run against a real workspace
and need credentials plus a writable test catalog; see
`databricks-tools-core/.env.test.template`.

## Security

- No credentials, tokens, hostnames, or connection strings are committed or
  copied into the image.
- `.env` and `.env.*` (except `.env.example`) are excluded by both
  [.gitignore](.gitignore) and [.dockerignore](.dockerignore).
- The container runs as an unprivileged user (`mcp`, uid 10001).
- The runtime stage carries no compilers, no pip, and no build toolchain.
