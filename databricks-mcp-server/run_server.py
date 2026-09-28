#!/usr/bin/env python
"""Run the Databricks MCP Server."""

import logging
import os
import sys

if os.environ.get("DATABRICKS_MCP_DEBUG"):
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

from databricks_mcp_server.server import mcp

# stdio is the default so a local launch behaves exactly as before. Container
# deployments set MCP_TRANSPORT=http (or sse / streamable-http) and bind a port.
# The registered tool surface is identical on every transport.
TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio").strip() or "stdio"

if __name__ == "__main__":
    if TRANSPORT == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport=TRANSPORT,
            host=os.environ.get("MCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("MCP_PORT", "8000")),
        )
