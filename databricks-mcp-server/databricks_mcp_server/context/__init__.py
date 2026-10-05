"""Bundled business context documents for the Databricks MCP Server.

- analysis_instructions.md: sent to the client as MCP server instructions
- customer_tool_data_context.md: served via the get_business_context tool/resource
"""

from functools import lru_cache
from pathlib import Path

_CONTEXT_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    return (_CONTEXT_DIR / name).read_text(encoding="utf-8")


def load_analysis_instructions() -> str:
    return _read("analysis_instructions.md")


def load_data_context() -> str:
    return _read("customer_tool_data_context.md")
