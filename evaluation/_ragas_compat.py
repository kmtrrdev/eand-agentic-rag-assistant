"""
Compatibility shim for Ragas 0.4.x when used with modern langchain-community.
Injects a mock Module for `langchain_community.chat_models.vertexai` so ragas loads
without throwing ModuleNotFoundError.
"""
import sys
import types

if "langchain_community.chat_models.vertexai" not in sys.modules:
    mod = types.ModuleType("langchain_community.chat_models.vertexai")
    mod.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules["langchain_community.chat_models.vertexai"] = mod
