# syntax=docker/dockerfile:1
#
# Databricks MCP Server — Unity Catalog analysis surface.
#
# Build:
#   docker build -t databricks-claude-mcp:local .
#
# The image ships no credentials. All Databricks configuration is supplied at
# run time through environment variables (see .env.example).

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1 — build the virtualenv
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Self-contained venv so the runtime stage can copy it without pip or compilers.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

COPY databricks-tools-core/ ./databricks-tools-core/
COPY databricks-mcp-server/ ./databricks-mcp-server/

# Both packages are installed in one pip invocation so that the
# databricks-mcp-server -> databricks-tools-core dependency resolves against the
# local source tree rather than PyPI (which does not publish databricks-tools-core).
RUN pip install --upgrade pip setuptools wheel \
 && pip install ./databricks-tools-core ./databricks-mcp-server

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MCP_TRANSPORT=stdio \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

# Unprivileged runtime user; the server never needs to write to the filesystem.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin mcp

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY databricks-mcp-server/run_server.py ./run_server.py
COPY databricks-mcp-server/healthcheck.py ./healthcheck.py

USER mcp

# stdio is the default MCP transport and keeps parity with a local install.
# For a long-running deployment set MCP_TRANSPORT=http and publish MCP_PORT.
EXPOSE 8000

# No-op under stdio (there is no socket to probe); probes /mcp otherwise.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]

CMD ["python", "run_server.py"]
