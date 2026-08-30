"""
app/mcp/client.py
-----------------
MCP Client interface for the LangGraph Agent.
Enables the agent to dynamically discover tools, execute them via MCP protocol/handlers,
and seamlessly inject structured results into the agent state and context.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.mcp.tools.search_kb import search_knowledge_base_tool
from app.mcp.tools.get_package_details import get_package_details_tool
from app.mcp.tools.calculate_price import calculate_price_tool, calculate_total_price_tool
from app.mcp.tools.get_activation_code import get_activation_code_tool
from app.mcp.tools.recommend_package import recommend_package_tool

logger = logging.getLogger("mcp.client")


class MCPClient:
    """
    Standard MCP Client for e& Egypt Telecom Agent.
    Provides tool discovery, validation, in-process & remote tool execution,
    and structured output mapping.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or settings.MCP_HOST
        self.port = port or settings.MCP_PORT
        self.enabled = settings.MCP_ENABLED

        # Tool registry dictionary mapping name -> handler callable
        self._tool_handlers = {
            "search_knowledge_base": search_knowledge_base_tool,
            "get_package_details": get_package_details_tool,
            "calculate_price": calculate_price_tool,
            "calculate_total_price": calculate_total_price_tool,
            "get_activation_code": get_activation_code_tool,
            "recommend_package": recommend_package_tool,
        }

    def is_enabled(self) -> bool:
        """Check if MCP tool integration is active."""
        return self.enabled

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all tools exposed by the MCP Server with their parameter schemas.
        """
        return [
            {
                "name": "search_knowledge_base",
                "description": "Search e& Egypt knowledge base using hybrid semantic + BM25 retrieval with 2-stage reranking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "service": {"type": "string", "description": "Hekaya, Emerald, Prepaid, DataLine, Super Connect"},
                        "top_k": {"type": "integer", "description": "Number of results (default 5)"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_package_details",
                "description": "Get verified structured specifications (price, total EGP, quota, validity, USSD, perks) for a named e& Egypt package.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_name": {"type": "string", "description": "Package name (e.g. Hekaya Mixat 92, Emerald 430)"},
                    },
                    "required": ["package_name"],
                },
            },
            {
                "name": "calculate_price",
                "description": "Calculate exact pre-tax price, tax amount (42.86%), and total recharge amount for e& Egypt packages.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "base_price": {"type": "number", "description": "Pre-tax price or total recharge budget in EGP"},
                        "tax_type": {"type": "string", "description": "prepaid, postpaid, hekaya, emerald, dataline"},
                        "is_tax_inclusive": {"type": "boolean", "description": "Set True if base_price is total customer budget"},
                        "discount_pct": {"type": "number", "description": "Discount percentage (0-100)"},
                    },
                },
            },
            {
                "name": "get_activation_code",
                "description": "Get verified official USSD activation code for an e& Egypt service or package tier.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service: Hekaya, Hekaya Mixat, Hekaya Internet, Mini Hekaya, Aqwa Card, Super Connect, DataLine, Emerald"},
                        "package": {"type": "string", "description": "Optional tier (e.g. 180, 92)"},
                    },
                    "required": ["service"],
                },
            },
            {
                "name": "recommend_package",
                "description": "Deterministic telecom package recommendation based on budget, tax inclusivity, track, and usage.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "budget_egp": {"type": "number", "description": "Maximum budget in EGP"},
                        "includes_tax": {"type": "boolean", "description": "Whether budget includes tax (default True)"},
                        "service": {"type": "string", "description": "Hekaya Mixat, Hekaya Internet, Emerald, DataLine"},
                        "usage_type": {"type": "string", "description": "data_heavy, calls_heavy, balanced, family, mifi"},
                        "line_type": {"type": "string", "description": "mobile_phone, mifi_router, home_adsl"},
                    },
                },
            },
        ]

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute an MCP tool by name with arguments.

        Args:
            name: Name of the tool.
            arguments: Dictionary of keyword arguments.

        Returns:
            Dict containing the tool execution result or error.
        """
        args = arguments or {}
        logger.info(f"MCPClient invoking tool '{name}' with args: {args}")

        handler = self._tool_handlers.get(name)
        if not handler:
            err_msg = f"Tool '{name}' not found in MCP registry."
            logger.warning(err_msg)
            return {"error": err_msg, "found": False}

        try:
            result = handler(**args)
            logger.debug(f"MCPClient tool '{name}' executed successfully.")
            return result
        except TypeError as te:
            err_msg = f"Invalid arguments for tool '{name}': {te}"
            logger.error(err_msg)
            return {"error": err_msg, "found": False}
        except Exception as exc:
            err_msg = f"Exception executing MCP tool '{name}': {exc}"
            logger.error(err_msg, exc_info=True)
            return {"error": err_msg, "found": False}

    async def acall_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Async invocation of an MCP tool."""
        return self.call_tool(name, arguments)


# Singleton MCP Client instance
mcp_client = MCPClient()
