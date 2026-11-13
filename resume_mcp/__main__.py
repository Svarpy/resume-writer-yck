"""Run the MCP server: ``python -m resume_mcp`` (stdio, for Claude Desktop and other MCP clients)."""

from __future__ import annotations

import sys

from resume_mcp.server import build_server


def main() -> None:
    transport = "streamable-http" if "--http" in sys.argv else "stdio"
    build_server().run(transport)


if __name__ == "__main__":
    main()
