import asyncio # Keep for _arun
import httpx # For making HTTP requests
import uuid # For generating client_callback_id
from typing import cast, Type, Optional, Any, Dict

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import MessageTextInput, MultilineInput, SecretStrInput

# Configuration for the external MCP server
DEFAULT_MCP_SERVER_URL = "http://localhost:8765"

# Define the input schema for the tool's Langchain execution
class EmailSenderMCPInput(BaseModel):
    content: str = Field(description="The content of the email to be sent.")
    recipient: str = Field(description="The email address of the recipient.")

# Define the actual Langchain Tool
class EmailSenderExternalMCPTool(BaseTool):
    name: str = "email_sender_external_mcp" # Renamed
    description: str = (
        "Submits an email sending task to an external MCP server and returns identifiers. "
        "Status is delivered via a separate SSE mechanism."
    )
    args_schema: Type[BaseModel] = EmailSenderMCPInput
    mcp_server_url: str # To be configured via component

    def __init__(self, mcp_server_url: str = DEFAULT_MCP_SERVER_URL, **data: Any):
        super().__init__(**data)
        # Ensure mcp_server_url is not an empty string, use default if it is.
        self.mcp_server_url = mcp_server_url if mcp_server_url and mcp_server_url.strip() else DEFAULT_MCP_SERVER_URL


    async def _arun(self, content: str, recipient: str, **kwargs: Any) -> str:
        client_callback_id = uuid.uuid4().hex

        payload = {
            "client_callback_id": client_callback_id,
            "tool_name": "email_sender",
            "params": {"content": content, "recipient": recipient}
        }

        submit_url = f"{self.mcp_server_url}/submit_task"
        print(f"EmailSenderExternalMCPTool: Submitting task to {submit_url} with payload: {payload}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(submit_url, json=payload, timeout=10.0)

            response.raise_for_status()

            mcp_response_data = response.json()
            server_task_id = mcp_response_data.get("task_id")

            if not server_task_id:
                error_msg = f"EmailSenderExternalMCPTool: Error - MCP server response missing 'task_id'. Response: {mcp_response_data}"
                print(error_msg)
                return error_msg # Return the error message directly

            return (
                f"Task {server_task_id} submitted to MCP for sending email. "
                f"Use client_callback_id {client_callback_id} with SSEListenerTool for status."
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"EmailSenderExternalMCPTool: HTTP error submitting task to MCP: {e.response.status_code} - {e.response.text}"
            print(error_msg)
            return f"Error submitting task to MCP: HTTP {e.response.status_code}."
        except httpx.RequestError as e:
            error_msg = f"EmailSenderExternalMCPTool: Request error submitting task to MCP: {e}"
            print(error_msg)
            return f"Error submitting task to MCP: Could not connect or request failed ({type(e).__name__})."
        except Exception as e:
            error_msg = f"EmailSenderExternalMCPTool: Unexpected error: {e} ({type(e).__name__})"
            print(error_msg)
            return f"An unexpected error occurred: {type(e).__name__}."

# Define the Langflow component
class EmailSenderToolComponent(LCToolComponent):
    display_name = "Email Sender Tool (External MCP)"
    description = "Submits an email sending task to an external MCP server. Status via SSE."
    # name = "EmailSenderTool" # Let Langflow use class name or define custom registration if needed
    icon = "Mail"
    tool_class: Type[BaseTool] = EmailSenderExternalMCPTool

    inputs = LCToolComponent.get_fields_from_class(tool_class) + [
        SecretStrInput(
            name="mcp_server_base_url", # Consistent naming
            display_name="MCP Server Base URL", # Removed "(Optional)" as it defaults
            info="Base URL of the external MCP server (e.g., http://localhost:8765). If not set, uses default.",
            required=False, # It has a default in the tool
            advanced=True,
            value=DEFAULT_MCP_SERVER_URL
        )
    ]

    def build_tool(self, **kwargs: Any) -> BaseTool:
        # Pop mcp_server_base_url for the tool's constructor, others are for _arun
        mcp_url = kwargs.pop("mcp_server_base_url", DEFAULT_MCP_SERVER_URL)
        if not mcp_url or not mcp_url.strip(): # Ensure not empty or just whitespace
            mcp_url = DEFAULT_MCP_SERVER_URL

        # The remaining kwargs are for the _arun method, LCToolComponent handles this.
        # We only pass constructor-specific args here.
        # If EmailSenderExternalMCPTool had other constructor args besides mcp_server_url and standard Pydantic ones,
        # they would be handled here.
        return self.tool_class(mcp_server_url=mcp_url)


# Standalone test block
async def main():
    # This main function is for conceptual testing of component instantiation logic.
    # It assumes LCToolComponent.get_fields_from_class is available or mocked if run directly.
    print("--- EmailSenderToolComponent Standalone Test ---")

    # Simulate Langflow instantiating the component (simplified)
    # In a real scenario, Langflow does this and provides the UI fields.
    # For testing `build_tool`, we can call it directly.

    # Test with default URL
    # When Langflow calls build_tool, it passes values from UI fields.
    # If "mcp_server_base_url" is not provided or empty, the default should be used.
    component_default = EmailSenderToolComponent() # In Langflow, this would be its representation

    # Simulating build_tool call as Langflow would, with UI values
    # Case 1: UI field is empty or not touched (so default applies)
    tool_instance_default = component_default.build_tool(mcp_server_base_url="")
    print(f"Tool with default MCP URL (from empty input): {tool_instance_default.mcp_server_url}")
    assert tool_instance_default.mcp_server_url == DEFAULT_MCP_SERVER_URL

    # Case 2: UI field has a value
    custom_url = "http://custom-mcp-server:1234"
    tool_instance_custom = component_default.build_tool(mcp_server_base_url=custom_url)
    print(f"Tool with custom MCP URL: {tool_instance_custom.mcp_server_url}")
    assert tool_instance_custom.mcp_server_url == custom_url

    print("\nEmailSenderExternalMCPTool instance creation logic tested.")
    print("Standalone _arun test would require a running mock MCP server and actual parameters (content, recipient).")

if __name__ == "__main__":
    # To run this main effectively, LCToolComponent and its methods like get_fields_from_class
    # would need to be available in the execution context, or mocked.
    # This is primarily for illustrating the component's build logic.
    # asyncio.run(main()) # Actual _arun calls are not made here.
    print("To run main for EmailSenderToolComponent, LCToolComponent context is needed or mocks for its methods.")
    pass
```
