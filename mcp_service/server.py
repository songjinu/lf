import json
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from sse_starlette.sse import EventSourceResponse
from typing import Dict, Any

from mcp_service.models import ReportRequest, EmailRequest, ToolProgress
from mcp_service.tools import run_report_tool, run_email_tool

app = FastAPI(
    title="MCP SSE Tool Server",
    description="Provides asynchronous tools via Server-Sent Events (SSE).",
    version="0.1.0",
)

@app.post("/tools/report", summary="Generate a report asynchronously via SSE")
async def sse_report_tool(request: ReportRequest = Body(...)) -> EventSourceResponse:
    """
    Endpoint to trigger the report generation tool and stream progress via SSE.
    """
    async def event_generator():
        try:
            async for progress_update in run_report_tool(request):
                yield {
                    "event": "update",
                    "data": json.dumps(progress_update) # Serialize ToolProgress model
                }
            # Signal completion of the stream
            yield {
                "event": "eof", # Or "close", "finish", etc.
                "data": json.dumps({"message": "Report generation stream finished."})
            }
        except Exception as e:
            # In case of an error during generation, send an error event
            # This ensures the client is aware of issues.
            error_message = ToolProgress(task_id="error", step="error", status="failed", details=str(e)).model_dump()
            yield {
                "event": "error",
                "data": json.dumps(error_message)
            }
            # Optionally, re-raise or log more extensively here
            # raise HTTPException(status_code=500, detail=str(e)) # This would terminate the SSE differently

    return EventSourceResponse(event_generator())

@app.post("/tools/email", summary="Send an email asynchronously via SSE")
async def sse_email_tool(request: EmailRequest = Body(...)) -> EventSourceResponse:
    """
    Endpoint to trigger the email sending tool and stream progress via SSE.
    """
    async def event_generator():
        try:
            async for progress_update in run_email_tool(request):
                yield {
                    "event": "update",
                    "data": json.dumps(progress_update) # Serialize ToolProgress model
                }
            yield {
                "event": "eof",
                "data": json.dumps({"message": "Email sending stream finished."})
            }
        except Exception as e:
            error_message = ToolProgress(task_id="error", step="error", status="failed", details=str(e)).model_dump()
            yield {
                "event": "error",
                "data": json.dumps(error_message)
            }

    return EventSourceResponse(event_generator())

@app.get("/", summary="Root endpoint for server status")
async def read_root():
    return {"message": "MCP SSE Tool Server is running."}

# To run this server (for development):
# uvicorn mcp_service.server:app --reload --port 8000
if __name__ == "__main__":
    # This is for illustrative purposes.
    # In a production environment, you'd use a process manager like Gunicorn with Uvicorn workers.
    print("Starting Uvicorn server for MCP Service on http://localhost:8000")
    print("Endpoints available:")
    print("  POST /tools/report")
    print("  POST /tools/email")
    print("  GET  /")
    uvicorn.run(app, host="0.0.0.0", port=8000)
