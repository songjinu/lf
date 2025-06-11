import pytest
import httpx
import json
from typing import List, Dict, Any
from mcp_service.models import ReportRequest, EmailRequest, ToolProgress

# Assuming the server will be run separately for these tests, or using TestClient
# For simplicity here, we'll assume an external server.
# For true unit tests, one would use FastAPI's TestClient.
# from fastapi.testclient import TestClient
# from mcp_service.server import app # If using TestClient

# client = TestClient(app) # Example for TestClient

BASE_URL = "http://localhost:8000" # Ensure server is running here

async def stream_and_collect_sse(url: str, payload: Dict[str, Any]) -> List[ToolProgress]:
    updates = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status() # Will raise an exception for 4xx/5xx responses
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data_json = line[len("data:"):].strip()
                    try:
                        data = json.loads(data_json)
                        # Check if it's a ToolProgress model or a simple message like eof
                        if "task_id" in data and "step" in data and "status" in data:
                             updates.append(ToolProgress(**data))
                        elif "message" in data: # e.g. EOF message
                            print(f"SSE EOF/Message: {data}")
                    except json.JSONDecodeError:
                        pytest.fail(f"Failed to decode JSON from SSE: {data_json}")
                elif line.startswith("event: error"):
                     pytest.fail(f"Received SSE error event: {line}")
    return updates

@pytest.mark.asyncio
async def test_sse_report_tool_endpoint():
    request_data = ReportRequest(report_type="integration_test_report")
    url = f"{BASE_URL}/tools/report"

    try:
        progress_updates = await stream_and_collect_sse(url, request_data.model_dump())
    except httpx.ConnectError:
        pytest.fail(f"Could not connect to server at {BASE_URL}. Is it running?")

    assert len(progress_updates) > 0
    final_update = progress_updates[-1]
    assert final_update.status == "completed"
    assert "integration_test_report" in final_update.details
    assert final_update.task_id is not None

@pytest.mark.asyncio
async def test_sse_email_tool_endpoint():
    request_data = EmailRequest(to_email="servertest@example.com", subject="Server Test", body="Testing server endpoint.")
    url = f"{BASE_URL}/tools/email"

    try:
        progress_updates = await stream_and_collect_sse(url, request_data.model_dump())
    except httpx.ConnectError:
        pytest.fail(f"Could not connect to server at {BASE_URL}. Is it running?")

    assert len(progress_updates) > 0
    final_update = progress_updates[-1]
    assert final_update.status == "completed"
    assert final_update.task_id is not None

@pytest.mark.asyncio
async def test_root_endpoint():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(BASE_URL + "/")
            response.raise_for_status()
            assert response.json() == {"message": "MCP SSE Tool Server is running."}
        except httpx.ConnectError:
            pytest.fail(f"Could not connect to server at {BASE_URL}. Is it running?")
