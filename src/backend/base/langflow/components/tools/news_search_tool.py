import asyncio # Keep for _arun, though direct sleep is removed
import httpx # For making HTTP requests
import uuid # For generating client_callback_id
from typing import cast, Type, Optional, Any, Dict, List

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import MessageTextInput, MultilineInput, SecretStrInput # Added SecretStrInput
from langflow.schema import Data # Keep for consistency, though not directly used now
# Removed TaskService, SocketService, and pending_tasks_store imports as they are no longer used by this tool's logic

# Configuration for the external MCP server
# This global can be overridden if the component's build_tool injects a different URL into the tool instance.
DEFAULT_MCP_SERVER_URL = "http://localhost:8765"

# Define the input schema for the tool's Langchain execution
class NewsSearchMCPInput(BaseModel):
    query: str = Field(description="The search query for news articles.")
    # callback_url is no longer used by this tool directly; SSE is the callback mechanism

# Define the actual Langchain Tool
class NewsSearchExternalMCPTool(BaseTool):
    name: str = "news_search_external_mcp" # Renamed to distinguish
    description: str = (
        "Submits a news search task to an external MCP server and returns identifiers. "
        "Results are delivered via a separate SSE mechanism."
    )
    args_schema: Type[BaseModel] = NewsSearchMCPInput
    mcp_server_url: str # To be set on instantiation

    def __init__(self, mcp_server_url: str = DEFAULT_MCP_SERVER_URL, **data: Any):
        super().__init__(**data)
        self.mcp_server_url = mcp_server_url if mcp_server_url else DEFAULT_MCP_SERVER_URL


    async def _arun(self, query: str, **kwargs: Any) -> str:
        client_callback_id = uuid.uuid4().hex

        payload = {
            "client_callback_id": client_callback_id,
            "tool_name": "news_search", # This is the name the MCP server knows this tool by
            "params": {"query": query}
        }

        submit_url = f"{self.mcp_server_url}/submit_task"
        print(f"NewsSearchExternalMCPTool: Submitting task to {submit_url} with payload: {payload}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(submit_url, json=payload, timeout=10.0)

            response.raise_for_status() # Raise an exception for HTTP error codes (4xx or 5xx)

            mcp_response_data = response.json()
            server_task_id = mcp_response_data.get("task_id")

            if not server_task_id:
                error_msg = f"NewsSearchExternalMCPTool: Error - MCP server response missing 'task_id'. Response: {mcp_response_data}"
                print(error_msg)
                return error_msg # Return the error message directly

            # Message includes both server_task_id and client_callback_id
            # SSEListenerTool will primarily use client_callback_id to connect to the SSE stream.
            # server_task_id can be used by the listener or agent to confirm it's the right task's data if needed.
            return (
                f"Task {server_task_id} submitted to MCP for news search. "
                f"Use client_callback_id {client_callback_id} with SSEListenerTool for results."
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"NewsSearchExternalMCPTool: HTTP error submitting task to MCP: {e.response.status_code} - {e.response.text}"
            print(error_msg)
            return f"Error submitting task to MCP: HTTP {e.response.status_code}."
        except httpx.RequestError as e:
            error_msg = f"NewsSearchExternalMCPTool: Request error submitting task to MCP: {e}"
            print(error_msg)
            return f"Error submitting task to MCP: Could not connect or request failed ({type(e).__name__})."
        except Exception as e:
            error_msg = f"NewsSearchExternalMCPTool: Unexpected error: {e} ({type(e).__name__})"
            print(error_msg)
            return f"An unexpected error occurred: {type(e).__name__}."

# Define the Langflow component
class NewsSearchToolComponent(LCToolComponent):
    display_name = "News Search Tool (External MCP)"
    description = "Submits a news search task to an external MCP server. Results via SSE."
    # The 'name' attribute in LCToolComponent usually defaults to the class name.
    # If you need to force it to "NewsSearchTool" for backward compatibility or specific registration,
    # you might need to set it explicitly or ensure the registration mechanism handles the new class name.
    # For now, let's assume Langflow handles components by their class name or a custom registration.
    # name = "NewsSearchTool"
    icon = "FileSearch"
    tool_class = NewsSearchExternalMCPTool # For LCToolComponent to know which tool to build

    inputs = LCToolComponent.get_fields_from_class(tool_class) + [ # Get args_schema fields automatically
        SecretStrInput(
            name="mcp_server_base_url", # This will be passed to the tool's constructor
            display_name="MCP Server Base URL",
            info="Base URL of the external MCP server (e.g., http://localhost:8765). If not set, uses default.",
            required=False, # It has a default in the tool
            advanced=True,
            value=DEFAULT_MCP_SERVER_URL # Default value shown in UI
        )
    ]

    def build_tool(self, **kwargs) -> BaseTool: # kwargs will contain 'mcp_server_base_url'
        # The MCP server URL from the component's input field
        mcp_url_from_input = kwargs.pop("mcp_server_base_url", DEFAULT_MCP_SERVER_URL)
        if not mcp_url_from_input: # Handles empty string from UI
            mcp_url_from_input = DEFAULT_MCP_SERVER_URL

        # All other kwargs should be parameters for the tool's args_schema,
        # but NewsSearchExternalMCPTool doesn't take them in constructor, _arun gets them.
        # LCToolComponent usually handles passing these to _arun.
        # We need to ensure only non-args_schema params are popped if any.

        return NewsSearchExternalMCPTool(mcp_server_url=mcp_url_from_input, **kwargs)


# Standalone test block (optional, good for quick verification if runnable outside Langflow)
async def main():
    # This test would require a mock MCP server endpoint.

    # Scenario 1: Using default MCP URL
    print("--- Scenario 1: Default MCP URL ---")
    component1 = NewsSearchToolComponent() #This would be how Langflow instantiates it
    # In Langflow, build_tool is called with resolved input values
    # Let's simulate that:
    tool_instance1_args = {field.name: field.value for field in component1.inputs if hasattr(field, 'value')}
    tool_instance1_args['mcp_server_base_url'] = DEFAULT_MCP_SERVER_URL # Explicitly set for clarity

    # Simulate how LCToolComponent might build the tool
    # The actual call from Langflow would be more complex, involving resolving all inputs
    # For this tool, mcp_server_base_url is a constructor arg for the *component*, then passed to tool

    # Let's assume the component is instantiated and then build_tool is called with the value from the UI field
    # For testing `build_tool` more directly:
    tool_instance1 = component1.build_tool(mcp_server_base_url=DEFAULT_MCP_SERVER_URL, query="AI in 2024") # query is an _arun arg
    print(f"Tool 1 instance created with MCP URL: {tool_instance1.mcp_server_url}")
    # result1 = await tool_instance1._arun(query="AI in 2024") # Requires mock server
    # print(f"Result 1: {result1}")


    # Scenario 2: Using custom MCP URL from component input
    print("\n--- Scenario 2: Custom MCP URL ---")
    custom_url = "http://my-custom-mcp:9000"
    component2 = NewsSearchToolComponent()
    tool_instance2 = component2.build_tool(mcp_server_base_url=custom_url, query="Future of AI")
    print(f"Tool 2 instance created with MCP URL: {tool_instance2.mcp_server_url}")
    # result2 = await tool_instance2._arun(query="Future of AI") # Requires mock server
    # print(f"Result 2: {result2}")

    print("\nNewsSearchExternalMCPTool instance creation tested. Standalone _arun test would require a mock MCP server.")

if __name__ == "__main__":
    # To run main, you'd need to define or import LCToolComponent.get_fields_from_class
    # For now, this structure is for conceptual testing.
    # asyncio.run(main()) # Commented out as it needs a mock server and LCToolComponent setup
    print("To run main for NewsSearchToolComponent, LCToolComponent context is needed or mocks for its methods.")
    pass
```
