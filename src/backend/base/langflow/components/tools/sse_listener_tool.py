import asyncio
import httpx
import json
from typing import cast, Type, Optional, Any, Dict, AsyncGenerator

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import MessageTextInput, IntInput, SecretStrInput

# Configuration for the external MCP server (consistent with other tools)
DEFAULT_MCP_SERVER_URL = "http://localhost:8765"

# Define the input schema for the tool's Langchain execution
class SSEListenerInput(BaseModel):
    client_callback_id: str = Field(description="The client-generated ID used to subscribe to the SSE event stream.")
    expected_task_id: Optional[str] = Field(default=None, description="Optional server-generated task_id to specifically wait for within the SSE stream if the stream might contain multiple task updates.")
    timeout_seconds: int = Field(default=60, description="Maximum time to wait for a relevant SSE event in seconds.")

# Define the actual Langchain Tool
class SSEListenerExternalMCPTool(BaseTool):
    name: str = "sse_listener_external_mcp"
    description: str = (
        "Connects to an SSE endpoint from an external MCP server to listen for task completion events "
        "based on a client_callback_id and optionally an expected_task_id."
    )
    args_schema: Type[BaseModel] = SSEListenerInput
    mcp_server_url: str
    # _current_timeout is set per-run in _arun, no need for class default here unless _run also uses it.

    def __init__(self, mcp_server_url: str = DEFAULT_MCP_SERVER_URL, **data: Any):
        super().__init__(**data)
        self.mcp_server_url = mcp_server_url if mcp_server_url and mcp_server_url.strip() else DEFAULT_MCP_SERVER_URL

    async def _iterate_sse_events(self, sse_url: str, current_timeout: float) -> AsyncGenerator[Dict[str, Any], None]:
        """Helper to connect and parse SSE events."""
        # Add a small buffer to the HTTP client timeout beyond the SSE timeout itself
        # to allow the stream to naturally close or for the server to send a final message.
        http_client_timeout = current_timeout + 10.0
        try:
            async with httpx.AsyncClient(timeout=http_client_timeout) as client:
                async with client.stream("GET", sse_url, headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"}) as response:
                    if response.status_code != 200:
                        print(f"SSEListenerTool: Error connecting to SSE stream '{sse_url}'. Status: {response.status_code}")
                        await response.aread() # Consume body to close properly
                        response.raise_for_status() # Will raise HTTPStatusError

                    current_event_name = None
                    current_data_lines = []
                    current_event_id = None

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line: # Empty line signifies end of an event
                            if current_data_lines:
                                full_data = "\n".join(current_data_lines)
                                try:
                                    data_json = json.loads(full_data)
                                    yield {
                                        "event": current_event_name or "message",
                                        "data": data_json,
                                        "id": current_event_id
                                    }
                                except json.JSONDecodeError:
                                    print(f"SSEListenerTool: Error decoding JSON data: '{full_data}' from stream '{sse_url}'")
                                # Reset for next event
                                current_event_name = None
                                current_data_lines = []
                                current_event_id = None
                            continue

                        if line.startswith("event:"):
                            current_event_name = line[len("event:"):].strip()
                        elif line.startswith("data:"):
                            current_data_lines.append(line[len("data:"):].strip())
                        elif line.startswith("id:"):
                            current_event_id = line[len("id:"):].strip()
                        # Comments (lines starting with ':') are ignored
        except httpx.HTTPStatusError as e: # Catch it here to add context
            print(f"SSEListenerTool: HTTPStatusError while streaming from '{sse_url}': {e}")
            raise # Re-raise to be caught by _arun
        except Exception as e:
            print(f"SSEListenerTool: Exception during SSE iteration from '{sse_url}': {type(e).__name__} - {e}")
            raise


    async def _arun(self, client_callback_id: str, expected_task_id: Optional[str] = None, timeout_seconds: int = 60, **kwargs: Any) -> Any:
        sse_url = f"{self.mcp_server_url}/events/{client_callback_id}"
        print(f"SSEListenerTool: Connecting to SSE stream at {sse_url} for client_callback_id {client_callback_id}, timeout {timeout_seconds}s")

        try:
            async def event_processor():
                async for event_dict in self._iterate_sse_events(sse_url, float(timeout_seconds)):
                    print(f"SSEListenerTool: Received raw SSE event: {event_dict}")

                    event_name = event_dict.get("event")
                    event_data = event_dict.get("data", {})

                    if event_name == "task_update": # Ensure we are processing the correct event type
                        server_task_id_from_event = event_data.get("task_id")
                        status = event_data.get("status")
                        result_payload = event_data.get("result") # This can be any JSON structure

                        # If expected_task_id is specified, filter by it.
                        if expected_task_id and server_task_id_from_event != expected_task_id:
                            print(f"SSEListenerTool: Skipping event for task_id '{server_task_id_from_event}' (expected '{expected_task_id}') on stream '{client_callback_id}'.")
                            continue

                        # If no expected_task_id, any completed/failed task on this client_callback_id stream is considered.
                        # This assumes client_callback_id is unique enough per originating request.
                        print(f"SSEListenerTool: Processing event for task_id '{server_task_id_from_event}' (expected: '{expected_task_id or 'any'}') with status '{status}'.")

                        if status == "COMPLETED":
                            print(f"SSEListenerTool: Task '{server_task_id_from_event}' COMPLETED. Result: {result_payload}")
                            return result_payload
                        elif status == "FAILED":
                            print(f"SSEListenerTool: Task '{server_task_id_from_event}' FAILED. Details: {result_payload}")
                            return {"error": "Task failed on MCP server.", "details": result_payload}
                        elif status == "IN_PROGRESS":
                            print(f"SSEListenerTool: Progress update for task '{server_task_id_from_event}': {result_payload}")
                            # Continue listening for a terminal event
                        else:
                            print(f"SSEListenerTool: Received event with unhandled status '{status}' for task '{server_task_id_from_event}'.")
                    elif event_name == "error": # Handle specific error events from SSE stream
                         print(f"SSEListenerTool: Received error event from stream '{client_callback_id}': {event_data}")
                         return {"error": "Error event received from SSE stream.", "details": event_data}
                    # Other event types can be handled or ignored here.

                # If the generator finishes without returning, it means the stream ended before a relevant event.
                print(f"SSEListenerTool: SSE stream for '{client_callback_id}' ended without a final COMPLETED/FAILED event for task '{expected_task_id or 'any'}'.")
                return {"error": "SSE stream ended before a conclusive task update was received."}

            final_result = await asyncio.wait_for(event_processor(), timeout=float(timeout_seconds))
            return final_result # Can be None if event_processor returns None explicitly, but current logic returns dict.

        except asyncio.TimeoutError:
            print(f"SSEListenerTool: Timeout after {timeout_seconds}s waiting for SSE event for client_callback_id '{client_callback_id}'.")
            return {"error": f"Timeout waiting for SSE event for client_callback_id {client_callback_id}"}
        except httpx.HTTPStatusError as e: # From _iterate_sse_events if response.raise_for_status() is hit early
            print(f"SSEListenerTool: HTTP error connecting to SSE stream '{sse_url}': {e.response.status_code} - {e.response.text}")
            return {"error": f"HTTP {e.response.status_code} connecting to SSE stream."}
        except httpx.RequestError as e: # From _iterate_sse_events for connection issues
            print(f"SSEListenerTool: Request error connecting to SSE stream '{sse_url}': {e}")
            return {"error": f"Could not connect to SSE stream ({type(e).__name__})."}
        except Exception as e:
            print(f"SSEListenerTool: Unexpected error during SSE processing for '{client_callback_id}': {e} ({type(e).__name__})")
            return {"error": f"An unexpected error occurred during SSE processing: {type(e).__name__} - {str(e)}."}

# Define the Langflow component
class SSEListenerToolComponent(LCToolComponent):
    display_name = "SSE Listener Tool (External MCP)"
    description = "Listens to an SSE stream from an external MCP server for task results."
    # name = "SSEListenerTool" # Let Langflow use class name by default
    icon = "Wifi"
    tool_class: Type[BaseTool] = SSEListenerExternalMCPTool

    inputs = LCToolComponent.get_fields_from_class(tool_class) + [
        SecretStrInput(
            name="mcp_server_base_url",
            display_name="MCP Server Base URL",
            info="Base URL of the external MCP server (e.g., http://localhost:8765). If not set, uses default.",
            required=False,
            advanced=True,
            value=DEFAULT_MCP_SERVER_URL
        )
    ]

    def build_tool(self, **kwargs: Any) -> BaseTool:
        mcp_url = kwargs.pop("mcp_server_base_url", DEFAULT_MCP_SERVER_URL)
        if not mcp_url or not mcp_url.strip():
             mcp_url = DEFAULT_MCP_SERVER_URL
        return self.tool_class(mcp_server_url=mcp_url)


async def main():
    # This main is for conceptual testing. A real test needs a mock SSE server.
    print("SSEListenerToolComponent Conceptual Test:")

    # Simulate component instantiation and tool building
    component = SSEListenerToolComponent()

    # Test with default URL
    tool_default_url = component.build_tool(mcp_server_base_url="")
    print(f"Tool built with MCP URL: {tool_default_url.mcp_server_url}")
    assert tool_default_url.mcp_server_url == DEFAULT_MCP_SERVER_URL

    # Test with custom URL
    custom_url = "http://my-custom-mcp.com:8000"
    tool_custom_url = component.build_tool(mcp_server_base_url=custom_url)
    print(f"Tool built with MCP URL: {tool_custom_url.mcp_server_url}")
    assert tool_custom_url.mcp_server_url == custom_url

    print("\nSSEListenerTool instance can be created with different MCP URLs.")
    print("Standalone _arun test would require a mock MCP SSE server.")
    # Example of how it might be called (requires mock server):
    # client_id_for_test = "test-client-id-123"
    # print(f"\nSimulating _arun for client_callback_id: {client_id_for_test}")
    # result = await tool_custom_url._arun(client_callback_id=client_id_for_test, timeout_seconds=5)
    # print(f"Result from _arun: {result}")

if __name__ == "__main__":
    # To run main effectively, LCToolComponent and its methods like get_fields_from_class
    # would need to be available in the execution context, or mocked.
    # asyncio.run(main())
    print("To run main for SSEListenerToolComponent, LCToolComponent context is needed or mocks for its methods.")
    pass
```
