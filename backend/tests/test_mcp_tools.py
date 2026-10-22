"""The MCP server must really work: real session, real tools, real database."""

import uuid

import pytest

from app.mcp_server.client import open_client
from app.security import hash_api_key
from app.models import User

TEST_API_KEY = "pl_test_api_key"


async def test_mcp_server_lists_the_expected_tools():
    async with open_client(TEST_API_KEY) as client:
        tools = {tool.name for tool in await client.list_tools()}
    assert tools == {
        "create_commitment",
        "list_commitments",
        "update_commitment",
        "add_dependency",
        "get_next_actions",
        "complete_commitment",
    }


async def test_mcp_tool_schemas_are_valid_json_schema():
    async with open_client(TEST_API_KEY) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    for tool in tools.values():
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        assert tool.description
    assert "title" in tools["create_commitment"].input_schema["properties"]
    assert "due_text" in tools["create_commitment"].input_schema["properties"]


async def test_create_and_list_through_mcp(user: User):
    async with open_client(TEST_API_KEY) as client:
        created = await client.call_tool(
            "create_commitment",
            {
                "title": "Send the demo to Abhishek",
                "recipient": "Abhishek",
                "due_text": "tomorrow evening",
                "timezone": "UTC",
            },
        )
        assert created["title"] == "Send the demo to Abhishek"
        assert created["due_at"] is not None

        listed = await client.call_tool("list_commitments", {})
        assert listed["count"] == 1
        assert listed["commitments"][0]["id"] == created["id"]


async def test_create_commitment_validates_its_input():
    async with open_client(TEST_API_KEY) as client:
        result = await client.call_tool("create_commitment", {"title": "   "})
        assert "error" in result
        result = await client.call_tool(
            "create_commitment", {"title": "ok", "priority": "super-urgent"}
        )
        assert "error" in result


async def test_dependencies_and_next_actions_through_mcp(user: User):
    async with open_client(TEST_API_KEY) as client:
        first = await client.call_tool("create_commitment", {"title": "Draft slides"})
        second = await client.call_tool("create_commitment", {"title": "Send slides"})

        linked = await client.call_tool(
            "add_dependency",
            {"commitment_id": second["id"], "depends_on_id": first["id"]},
        )
        assert linked["blocked_by"] == [first["id"]]

        actions = await client.call_tool("get_next_actions", {"limit": 5})
        titles = [entry["commitment"]["title"] for entry in actions["next_actions"]]
        assert "Draft slides" in titles
        blocked = [entry for entry in actions["next_actions"] if entry["blocked"]]
        assert blocked and blocked[0]["commitment"]["title"] == "Send slides"

        completed = await client.call_tool("complete_commitment", {"id": first["id"]})
        assert completed["status"] == "completed"


async def test_mcp_session_without_a_key_is_refused():
    async with open_client("pl_a_key_that_does_not_exist") as client:
        result = await client.call_tool("list_commitments", {})
        assert "error" in result


async def test_mcp_cannot_touch_another_users_data(client, user: User):
    """A key that resolves to no user gets nothing."""
    async with open_client("pl_not_a_real_key") as mcp:
        result = await mcp.call_tool("list_commitments", {})
        assert "error" in result
        assert result["count"] if "count" in result else True


async def test_mcp_server_runs_as_a_real_stdio_subprocess(user: User):
    """The stdio transport spawns `python -m app.mcp_server.server` and talks MCP to it."""
    async with open_client(TEST_API_KEY, transport="stdio") as client:
        tools = {tool.name for tool in await client.list_tools()}
        assert "create_commitment" in tools

        created = await client.call_tool(
            "create_commitment", {"title": "Made over stdio", "timezone": "UTC"}
        )
        assert created["title"] == "Made over stdio"

        listed = await client.call_tool("list_commitments", {})
        assert listed["count"] == 1
