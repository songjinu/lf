import pytest
from unittest.mock import patch, AsyncMock # For mocking external calls like OpenAI and SSE server

from mcp_service.agent import create_mcp_agent, GenerateReportSSETool, SendEmailSSETool, _stream_sse_tool
from mcp_service.models import ReportRequest, EmailRequest, ToolProgress

# These tests are more complex as they involve mocking LLM responses and SSE streams.
# Focus on testing the agent's tool usage logic.

@pytest.fixture
def mcp_agent_executor():
    # This fixture will provide an agent executor, potentially with mocked LLM
    # For simplicity, we'll directly test tool invocation logic or mock _stream_sse_tool
    return create_mcp_agent() # In a real test, ChatOpenAI would be mocked

@pytest.mark.asyncio
@patch('mcp_service.agent._stream_sse_tool', new_callable=AsyncMock)
async def test_generate_report_sse_tool_direct_call(mock_stream_sse):
    # Mock the SSE stream function to return a predefined list of progress updates
    mock_task_id = "report_task_123"
    mock_file_path = "/mock/reports/report_weekly.pdf"
    mock_stream_sse.return_value = [
        ToolProgress(task_id=mock_task_id, step="Starting", status="running").model_dump(),
        ToolProgress(task_id=mock_task_id, step="Fetching data", status="running").model_dump(),
        ToolProgress(task_id=mock_task_id, step="Completed", status="completed", details=f"Report generated: {mock_file_path}").model_dump(),
    ]

    tool = GenerateReportSSETool()
    result = await tool.arun(report_type="weekly")

    assert len(result) == 3
    final_progress = result[-1]
    assert final_progress["status"] == "completed"
    assert final_progress["details"] == f"Report generated: {mock_file_path}"
    # Check that _stream_sse_tool was called correctly
    mock_stream_sse.assert_called_once()
    call_args = mock_stream_sse.call_args[0] # Get positional arguments
    assert call_args[0] == "http://localhost:8000/tools/report" # URL
    assert call_args[1] == ReportRequest(report_type="weekly").model_dump() # Payload

@pytest.mark.asyncio
@patch('mcp_service.agent._stream_sse_tool', new_callable=AsyncMock)
async def test_send_email_sse_tool_direct_call(mock_stream_sse):
    mock_task_id = "email_task_456"
    mock_stream_sse.return_value = [
        ToolProgress(task_id=mock_task_id, step="Initiating", status="running").model_dump(),
        ToolProgress(task_id=mock_task_id, step="Sent", status="completed").model_dump(),
    ]

    tool = SendEmailSSETool()
    email_input = {
        "to_email": "test@example.com",
        "subject": "Test Subject",
        "body": "Test body",
        "attachment_path": "/mock/reports/report_weekly.pdf"
    }
    result = await tool.arun(**email_input)

    assert len(result) == 2
    assert result[-1]["status"] == "completed"
    mock_stream_sse.assert_called_once()
    call_args = mock_stream_sse.call_args[0]
    assert call_args[0] == "http://localhost:8000/tools/email"
    assert call_args[1] == EmailRequest(**email_input).model_dump()

# To test the full agent logic (e.g., processing "주간보고를 작성해서, 메일로 보내줘"):
# This would require mocking the ChatOpenAI LLM responses to simulate the agent's thought process
# and tool selections. This is significantly more complex and often involves:
# 1. Defining expected LLM responses (tool calls).
# 2. Mocking the LLM's `ainvoke` or `generate` method to return these predefined responses.
# 3. Verifying that the agent makes the correct sequence of tool calls based on the mocked LLM.
# For now, we've focused on testing the tools themselves and their direct invocation.
# A full agent test might look like (pseudo-code):
#
# @patch('langchain_openai.ChatOpenAI.ainvoke', new_callable=AsyncMock)
# @patch('mcp_service.agent.GenerateReportSSETool._arun', new_callable=AsyncMock) # Mock the tool's arun
# @patch('mcp_service.agent.SendEmailSSETool._arun', new_callable=AsyncMock)    # Mock the tool's arun
# async def test_agent_korean_query_flow(mock_send_email, mock_generate_report, mock_llm_ainvoke, mcp_agent_executor):
#     # 1. Setup mock LLM to first call generate_report
#     # 2. Setup mock_generate_report to return a path
#     # 3. Setup mock LLM to then call send_email with that path
#     # 4. Setup mock_send_email to return success
#     # ... then invoke agent and assert ...
#     pass

# Add a conftest.py if needed for shared fixtures, e.g. event loop policies for asyncio with pytest
