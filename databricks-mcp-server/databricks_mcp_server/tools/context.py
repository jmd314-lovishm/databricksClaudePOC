"""Business context tools - Serve the Customer Tool data context to the client.

Tools:
- get_business_context: Full Customer Tool data context (tables, joins, rules)

Resources:
- context://customer-tool/data-context: Same document, as an MCP resource
- context://analysis/instructions: The analysis/output instructions sent as server instructions

Prompts:
- customer_tool_analysis: Instructions + data context as a ready-made prompt
"""

from ..context import load_analysis_instructions, load_data_context
from ..server import mcp


@mcp.tool(timeout=30)
def get_business_context() -> str:
    """Get the authoritative Customer Tool data context for dev_catalog.

    This Databricks connection holds the company's revenue, sales and customer data:
    revenue by channel / PE fund / investment bank, new vs existing channels and clients,
    LTM and year-on-year revenue movement (new, cross-sell, netsell, churn), invoices and
    billing in GBP, customers, clusters, projects, solutions/service lines, spend bands
    and cohorts.

    Call this BEFORE answering any business question or querying dev_catalog.
    Returns the required answer format, then markdown covering table paths, grain,
    join keys, column meanings, revenue/bucket business rules, known ambiguities
    and glossary."""
    # Clients that load connector tools on demand may never surface the server
    # instructions, so the answer-format rules travel with the tool result too.
    return (
        f"{load_analysis_instructions()}\n\n---\n\n{load_data_context()}\n\n---\n\n"
        f"{_FORMAT_REMINDER}"
    )


_FORMAT_REMINDER = (
    "ANSWER FORMAT (mandatory): inline dashboard first (KPI cards + exactly ONE chart, "
    "more charts only if the user explicitly asks), then "
    "EXACTLY 3 bullet points of at most 2 lines each. Nothing else: no tables, "
    "headings, caveat lists, alternative views or follow-up offers, unless the user "
    "explicitly asks for more detail."
)


@mcp.resource(
    "context://customer-tool/data-context",
    name="Customer Tool data context",
    description="Authoritative business context for dev_catalog Customer Tool tables.",
    mime_type="text/markdown",
)
def data_context_resource() -> str:
    return load_data_context()


@mcp.resource(
    "context://analysis/instructions",
    name="Analysis instructions",
    description="Output format and analysis rules for answering business questions.",
    mime_type="text/markdown",
)
def analysis_instructions_resource() -> str:
    return load_analysis_instructions()


@mcp.prompt(name="customer_tool_analysis")
def customer_tool_analysis(question: str) -> str:
    """Answer a business question using dev_catalog with the full instructions and data context."""
    return (
        f"{load_analysis_instructions()}\n\n---\n\n{load_data_context()}\n\n---\n\n"
        f"Business question: {question}"
    )
