"""
app/mcp/server.py
-----------------
MCP (Model Context Protocol) server exposing e& Egypt KB retrieval & calculations as tools.

Tools exposed:
  1. search_knowledge_base  - Hybrid semantic + BM25 search with 2-stage reranking
  2. get_package_details    - Structured info about a named package
  3. calculate_price        - Deterministic tax-inclusive price calculator
  4. get_activation_code    - Verified USSD code lookup
  5. recommend_package      - Rule-grounded package recommendation engine

The MCP server runs as a separate process or is invoked via MCP Client.
Enable with: MCP_ENABLED=true in .env

Run standalone:
    python -m app.mcp.server
"""
import json
import logging
import sys

logger = logging.getLogger("mcp.server")


def create_mcp_server():
    """Create and configure the MCP Server with all 5 registered tools."""
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError:
        logger.error("mcp package not installed. Run: pip install mcp")
        return None

    from app.mcp.tools.search_kb import search_knowledge_base_tool
    from app.mcp.tools.get_package_details import get_package_details_tool
    from app.mcp.tools.calculate_price import calculate_price_tool, calculate_total_price_tool
    from app.mcp.tools.get_activation_code import get_activation_code_tool
    from app.mcp.tools.recommend_package import recommend_package_tool

    server = Server("etisalat-kb")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="search_knowledge_base",
                description=(
                    "Search the e& Egypt telecom knowledge base using hybrid semantic + BM25 retrieval "
                    "with cross-encoder reranking. Returns structured excerpts with source metadata and scores."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query in Arabic or English"},
                        "service": {"type": "string", "description": "Optional: Hekaya, Emerald, Prepaid, DataLine, Super Connect"},
                        "category": {"type": "string", "description": "Optional category filter"},
                        "top_k": {"type": "integer", "description": "Number of results (default: 5)"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_package_details",
                description=(
                    "Get verified structured details (price, total EGP, quota, validity, family lines, USSD) "
                    "for a named e& Egypt package from the official registry."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "package_name": {"type": "string", "description": "e.g. Hekaya Mixat 92, Hekaya Internet 270, Emerald 430"},
                    },
                    "required": ["package_name"],
                },
            ),
            Tool(
                name="calculate_price",
                description=(
                    "Calculate exact pre-tax price, tax amount, and total recharge amount for e& Egypt packages. "
                    "Supports both forward calculation (pretax -> total) and reverse calculation (total budget -> pretax)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "base_price": {"type": "number", "description": "Base price or total budget in EGP"},
                        "pretax_price": {"type": "number", "description": "Alias for base_price"},
                        "tax_type": {
                            "type": "string",
                            "enum": ["prepaid", "postpaid", "hekaya", "emerald", "dataline"],
                            "description": "Tax type: prepaid (42.86%) or postpaid (~22%)",
                        },
                        "is_tax_inclusive": {"type": "boolean", "description": "Set True if base_price is already tax-inclusive total"},
                        "discount_pct": {"type": "number", "description": "Optional percentage discount (0-100)"},
                    },
                },
            ),
            Tool(
                name="calculate_total_price",
                description="Compatibility alias for calculate_price.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pretax_price": {"type": "number", "description": "Pre-tax price in EGP"},
                        "tax_type": {"type": "string", "description": "Tax type: prepaid or postpaid"},
                    },
                    "required": ["pretax_price"],
                },
            ),
            Tool(
                name="get_activation_code",
                description="Get the verified official USSD activation code for an e& Egypt service or package tier.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service name: Hekaya, Hekaya Mixat, Hekaya Internet, Mini Hekaya, Aqwa Card, Super Connect, DataLine, Emerald"},
                        "package": {"type": "string", "description": "Optional specific package tier (e.g. 180, 92)"},
                    },
                    "required": ["service"],
                },
            ),
            Tool(
                name="recommend_package",
                description=(
                    "Recommend the optimal e& Egypt telecom package deterministically based on budget, "
                    "tax inclusivity, track/service preference, and usage type."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "budget_egp": {"type": "number", "description": "Maximum budget in EGP"},
                        "includes_tax": {"type": "boolean", "description": "Whether budget includes 42.86% tax (default: True)"},
                        "service": {"type": "string", "description": "Preferred track: Hekaya Mixat, Hekaya Internet, Emerald, DataLine"},
                        "usage_type": {"type": "string", "description": "Usage profile: data_heavy, calls_heavy, balanced, family, mifi"},
                        "line_type": {"type": "string", "description": "mobile_phone, mifi_router, home_adsl"},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name == "search_knowledge_base":
            result = search_knowledge_base_tool(**arguments)
        elif name == "get_package_details":
            result = get_package_details_tool(**arguments)
        elif name in ("calculate_price", "calculate_total_price"):
            result = calculate_price_tool(**arguments)
        elif name == "get_activation_code":
            result = get_activation_code_tool(**arguments)
        elif name == "recommend_package":
            result = recommend_package_tool(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}", "found": False}

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    return server


def start_mcp_server():
    """Start the MCP server using stdio transport."""
    server = create_mcp_server()
    if server is None:
        return

    logger.info("Starting MCP server (stdio transport)...")
    import asyncio
    from mcp.server.stdio import stdio_server
    asyncio.run(stdio_server(server))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_mcp_server()
