#!/usr/bin/env python
"""Container health check for the Databricks MCP Server.

Exit 0 = healthy, exit 1 = unhealthy.

Under the default stdio transport there is no socket to probe — the server is a
subprocess driven by its client — so the check is a no-op and reports healthy.
Under a networked transport it probes the local MCP endpoint. Any HTTP response
means the listener is up; MCP replies 4xx to an unadorned GET, which is still a
healthy listener. Only a connection-level failure is unhealthy.
"""

import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip() or "stdio"
    if transport == "stdio":
        return 0

    port = os.environ.get("MCP_PORT", "8000")
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        urllib.request.urlopen(url, timeout=4)
    except urllib.error.HTTPError:
        # The listener answered; the status code is irrelevant here.
        return 0
    except Exception as exc:  # connection refused, DNS, timeout, ...
        print(f"unhealthy: {url}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
