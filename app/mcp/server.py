"""
Standalone MCP server exposing this app's RAG search and deterministic telecom
tools over the standard Model Context Protocol, so any MCP-compatible client
(Claude Desktop, another agent framework, etc.) can use them directly — not
just this project's own FastAPI app.

The live /chat pipeline (app/agent/) calls these same underlying functions
in-process for speed (no subprocess/stdio round trip on every customer
request); this server exposes the identical implementations externally.

Run standalone:
    python -m app.mcp.server
"""
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from app.retrieval.hybrid_retriever import search
from app.tools import (
    calculate_price_tool,
    get_activation_code_tool,
    get_family_packages_tool,
    get_package_details_tool,
    recommend_packages_tool,
)

mcp = MCPServer(
    name="etisalat-agentic-kb",
    instructions=(
        "Tools for e& Egypt (Etisalat) telecom packages: hybrid RAG search over the "
        "package catalog, plus deterministic exact lookups for prices, USSD codes, "
        "tax calculation, and budget-based recommendations."
    ),
)


@mcp.tool()
def search_knowledge_base(query: str) -> List[Dict[str, Any]]:
    """Hybrid (dense + BM25 + cross-encoder rerank) search over the e& Egypt
    package catalog. Returns the top matching chunks with their source metadata.
    Use this for open-ended or descriptive questions that aren't about one exact,
    named package tier — for an exact tier, use get_package_details instead."""
    return [{"content": doc["content"], "metadata": doc["metadata"]} for doc in search(query)]


@mcp.tool()
def get_package_details(package_name: str) -> Dict[str, Any]:
    """Exact lookup for one named e& Egypt package tier, e.g. "Aqwa Card 19",
    "Hekaya Mixat 92", "Emerald 430". Returns found=false with closest_matches
    if the tier doesn't exist — never guess a tier that isn't returned here."""
    return get_package_details_tool(package_name)


@mcp.tool()
def get_family_packages(family_name: str) -> Dict[str, Any]:
    """Every tier in a product family (e.g. "hekaya_mixat", "emerald"), sorted by price."""
    return get_family_packages_tool(family_name)


@mcp.tool()
def calculate_price(base_price: float, tax_type: str = "prepaid") -> Dict[str, Any]:
    """Deterministic tax calculator. tax_type is "prepaid" (42.857% recharge tax),
    "postpaid", or "emerald" (8% schedule tax + 14% VAT + flat 10 EGP fee)."""
    return calculate_price_tool(base_price=base_price, tax_type=tax_type)


@mcp.tool()
def get_activation_code(service: str, package: Optional[str] = None) -> Dict[str, Any]:
    """Verified USSD/activation code for a service or specific package tier."""
    return get_activation_code_tool(service=service, package=package)


@mcp.tool()
def recommend_packages(
    budget_egp: Optional[float] = None,
    family: Optional[str] = None,
    device_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Budget-constrained package recommendation, filtered by the after-tax
    total (not the bare listed price). device_type is "phone" or "router"/"mifi"."""
    return recommend_packages_tool(budget_egp=budget_egp, family=family, device_type=device_type)


if __name__ == "__main__":
    mcp.run()
