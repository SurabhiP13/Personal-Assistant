"""
End-to-end test for server__v2.py over MCP stdio.

Spawns the server as a subprocess (using the same python interpreter), opens
an MCP ClientSession, and verifies:

  1. The expected tools are registered.
  2. run_command actually runs a shell command and returns structured output.

This test does NOT touch Gmail (no auth required).
"""
import json
import os
import sys

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_PATH = os.path.join(ROOT, "servers", "server__v2.py")


# Tools that must be registered. (Subset — we don't pin the full list so adding
# new tools later won't break this test.)
EXPECTED_TOOLS = {
    "run_command",
    "list_emails",
    "get_email",
    "get_unread_emails",
    "send_email",
    "delete_email",
    "delete_emails_in_label",
    "gmail.list_labels",
    "gmail.create_label",
    "gmail.update_label",
    "gmail.delete_label",
    "gmail.label_emails",
    "gmail.search_and_label",
    "gmail.list_drafts",
    "gmail.get_draft",
    "gmail.create_draft",
    "gmail.update_draft",
}


@pytest.fixture
async def mcp_session():
    """Spawn server__v2.py over stdio and yield an initialized MCP session."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[SERVER_PATH, "--server_type", "stdio"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.mark.asyncio
async def test_expected_tools_registered(mcp_session):
    """All expected tools should be registered by the MCP server."""
    response = await mcp_session.list_tools()
    registered = {t.name for t in response.tools}
    missing = EXPECTED_TOOLS - registered
    assert not missing, f"Missing tools: {missing}"


@pytest.mark.asyncio
async def test_run_command_echo(mcp_session):
    """run_command should execute a shell command and return JSON with stdout."""
    result = await mcp_session.call_tool(
        "run_command", {"command": "echo hello-from-e2e"}
    )
    # result.content is a list of TextContent — extract the first text payload.
    assert result.content, "run_command returned no content"
    text = result.content[0].text
    payload = json.loads(text)
    assert payload["exit_code"] == 0
    assert "hello-from-e2e" in payload["stdout"]
    assert payload["stderr"] == ""


@pytest.mark.asyncio
async def test_run_command_timeout(mcp_session):
    """A command that exceeds the timeout should return a timeout error payload."""
    result = await mcp_session.call_tool(
        "run_command", {"command": "sleep 5", "timeout": 1}
    )
    text = result.content[0].text
    payload = json.loads(text)
    assert payload["exit_code"] is None
    assert "timed out" in payload["error"].lower()
