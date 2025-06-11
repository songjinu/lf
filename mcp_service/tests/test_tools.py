import pytest
import asyncio
from mcp_service.tools import run_report_tool, run_email_tool
from mcp_service.models import ReportRequest, EmailRequest, ToolProgress

@pytest.mark.asyncio
async def test_run_report_tool():
    request = ReportRequest(report_type="test_report")
    progress_updates = []
    async for update in run_report_tool(request):
        progress_updates.append(ToolProgress(**update)) # Validate against model

    assert len(progress_updates) > 0
    final_update = progress_updates[-1]
    assert final_update.status == "completed"
    assert final_update.details is not None
    assert "test_report" in final_update.details
    assert final_update.task_id is not None

@pytest.mark.asyncio
async def test_run_email_tool():
    request = EmailRequest(to_email="test@example.com", subject="Test Email", body="This is a test.")
    progress_updates = []
    async for update in run_email_tool(request):
        progress_updates.append(ToolProgress(**update))

    assert len(progress_updates) > 0
    final_update = progress_updates[-1]
    assert final_update.status == "completed"
    assert final_update.task_id is not None

@pytest.mark.asyncio
async def test_run_email_tool_with_attachment():
    request = EmailRequest(
        to_email="test@example.com",
        subject="Test Email with Attachment",
        body="This is a test.",
        attachment_path="/tmp/fake_attachment.pdf"
    )
    progress_updates = []
    has_attachment_step = False
    async for update in run_email_tool(request):
        validated_update = ToolProgress(**update)
        progress_updates.append(validated_update)
        if validated_update.step and "Attaching file" in validated_update.step:
            has_attachment_step = True

    assert len(progress_updates) > 0
    final_update = progress_updates[-1]
    assert final_update.status == "completed"
    assert has_attachment_step, "Email tool should have shown an attachment step."
