import asyncio
import uuid
from typing import AsyncGenerator, Dict, Any
from mcp_service.models import ReportRequest, EmailRequest, ToolProgress # Assuming models.py is in the same directory level

async def run_report_tool(request: ReportRequest) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Asynchronously generates a mock report, yielding progress updates.
    """
    task_id = str(uuid.uuid4())
    yield ToolProgress(task_id=task_id, step="Starting report generation", status="running", details=f"Report type: {request.report_type}").model_dump()
    await asyncio.sleep(1) # Simulate initial processing

    yield ToolProgress(task_id=task_id, step="Fetching data", status="running").model_dump()
    await asyncio.sleep(2) # Simulate data fetching

    yield ToolProgress(task_id=task_id, step="Formatting report", status="running").model_dump()
    await asyncio.sleep(2) # Simulate formatting

    mock_file_path = f"/tmp/reports/report_{task_id}_{request.report_type.replace(' ', '_')}.pdf"
    yield ToolProgress(task_id=task_id, step="Finalizing report", status="completed", details=f"Report generated: {mock_file_path}").model_dump()
    # In a real scenario, you would return more comprehensive data, here we focus on the SSE stream
    # For the final message, it might be part of the last SSE event or a separate return if not purely SSE based.

async def run_email_tool(request: EmailRequest) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Asynchronously sends a mock email, yielding progress updates.
    """
    task_id = str(uuid.uuid4())
    yield ToolProgress(task_id=task_id, step="Initiating email send", status="running", details=f"To: {request.to_email}, Subject: {request.subject}").model_dump()
    await asyncio.sleep(1)

    yield ToolProgress(task_id=task_id, step="Connecting to email server", status="running").model_dump()
    await asyncio.sleep(1) # Simulate connection

    if request.attachment_path:
        yield ToolProgress(task_id=task_id, step=f"Attaching file: {request.attachment_path}", status="running").model_dump()
        await asyncio.sleep(1) # Simulate attaching file

    yield ToolProgress(task_id=task_id, step="Sending email", status="running").model_dump()
    await asyncio.sleep(2) # Simulate sending

    yield ToolProgress(task_id=task_id, step="Email sent successfully", status="completed").model_dump()

# Example of how to use the tools (optional, for direct testing)
async def main():
    print("Testing Report Tool:")
    report_req = ReportRequest(report_type="weekly_summary")
    async for progress in run_report_tool(report_req):
        print(progress)

    print("\nTesting Email Tool:")
    email_req = EmailRequest(to_email="test@example.com", subject="Weekly Report", body="Please find attached the weekly report.", attachment_path="/tmp/reports/report_mock_id_weekly_summary.pdf")
    async for progress in run_email_tool(email_req):
        print(progress)

if __name__ == "__main__":
    asyncio.run(main())
