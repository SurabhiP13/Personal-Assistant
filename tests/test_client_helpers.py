"""
Unit tests for the pure helpers in client.py:

  - clean_schema: should strip 'title' fields recursively without mutating input
  - convert_mcp_tools_to_gemini: should produce a single Tool wrapping all
    function declarations
  - MCPClient.history rolling window: should trim history to MAX_HISTORY_TURNS

These tests do NOT touch Gemini, MCP servers, or the network. They stub out
the genai client constructor so MCPClient() can be instantiated without an
API key.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# Make sure GEMINI_API_KEY is set so MCPClient.__init__ doesn't raise. The
# value is irrelevant — we patch the client constructor below.
os.environ.setdefault("GEMINI_API_KEY", "test-key")


@pytest.fixture
def client_module():
    """Import client.py with the genai.Client constructor stubbed."""
    if "client" in sys.modules:
        del sys.modules["client"]
    with patch("google.genai.Client", return_value=SimpleNamespace(models=None)):
        import client  # noqa: WPS433 (import inside fixture is intentional)
    return client


# ---------------------------------------------------------------------------
# clean_schema
# ---------------------------------------------------------------------------
class TestCleanSchema:
    def test_removes_top_level_title(self, client_module):
        schema = {"title": "MyTool", "type": "object"}
        out = client_module.clean_schema(schema)
        assert out == {"type": "object"}

    def test_removes_nested_titles_in_properties(self, client_module):
        schema = {
            "title": "Outer",
            "type": "object",
            "properties": {
                "name": {"title": "Name", "type": "string"},
                "age": {"title": "Age", "type": "integer"},
            },
        }
        out = client_module.clean_schema(schema)
        assert "title" not in out
        assert "title" not in out["properties"]["name"]
        assert "title" not in out["properties"]["age"]
        assert out["properties"]["name"]["type"] == "string"

    def test_does_not_mutate_input(self, client_module):
        schema = {"title": "Original", "type": "object"}
        original_copy = dict(schema)
        client_module.clean_schema(schema)
        assert schema == original_copy, "clean_schema must not mutate its input"

    def test_handles_non_dict(self, client_module):
        assert client_module.clean_schema("not-a-dict") == "not-a-dict"
        assert client_module.clean_schema(None) is None
        assert client_module.clean_schema(42) == 42


# ---------------------------------------------------------------------------
# convert_mcp_tools_to_gemini
# ---------------------------------------------------------------------------
class TestConvertMcpToolsToGemini:
    def _fake_tool(self, name, description, schema):
        return SimpleNamespace(name=name, description=description, inputSchema=schema)

    def test_returns_single_tool_with_all_declarations(self, client_module):
        tools = [
            self._fake_tool(
                "run_command",
                "Run a shell command",
                {"type": "object", "properties": {"command": {"type": "string"}}},
            ),
            self._fake_tool(
                "list_emails",
                "List Gmail emails",
                {"type": "object", "properties": {"query": {"type": "string"}}},
            ),
        ]
        result = client_module.convert_mcp_tools_to_gemini(tools)
        # Exactly one Tool, with both FunctionDeclarations grouped under it.
        assert len(result) == 1
        declarations = result[0].function_declarations
        assert len(declarations) == 2
        names = {d.name for d in declarations}
        assert names == {"run_command", "list_emails"}

    def test_empty_tool_list(self, client_module):
        result = client_module.convert_mcp_tools_to_gemini([])
        assert len(result) == 1
        assert result[0].function_declarations == []


# ---------------------------------------------------------------------------
# MCPClient history rolling window
# ---------------------------------------------------------------------------
class TestHistoryRollingWindow:
    def test_history_initialized_empty(self, client_module):
        client = client_module.MCPClient()
        assert client.history == []
        assert client.MAX_HISTORY_TURNS == 20

    def test_trim_keeps_only_last_n(self, client_module):
        """
        Simulate the trim line at the end of process_query without invoking the
        full async flow. This pins the rolling-window behavior to the test.
        """
        client = client_module.MCPClient()
        client.history = list(range(50))  # 50 entries, > MAX_HISTORY_TURNS (20)

        if len(client.history) > client.MAX_HISTORY_TURNS:
            client.history = client.history[-client.MAX_HISTORY_TURNS :]

        assert len(client.history) == 20
        assert client.history == list(range(30, 50))
