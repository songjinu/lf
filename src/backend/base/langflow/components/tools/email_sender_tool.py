import asyncio
from typing import cast, Type, Optional, Any, Dict

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import MultilineInput, MessageTextInput, SecretStrInput

# Attempt to import MCP SDK components
try:
    from mcp import ClientSession, types as mcp_types
    from mcp.client.streamable_http import streamablehttp_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    class ClientSession:
        def __init__(self, *args, **kwargs):
            if not MCP_SDK_AVAILABLE:
                 raise ImportError("MCP SDK not installed. Please install 'mcp' to use this tool.")
        async def initialize(self, *args, **kwargs):
            pass
        async def call_tool(self, *args, **kwargs):
            return {"error": "MCP SDK call_tool called on dummy session."}
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args, **kwargs):
            pass

    def streamablehttp_client(*args, **kwargs):
        class DummyStreamableClient:
            async def __aenter__(self):
                async def dummy_read_stream():
                    if False: yield b""
                async def dummy_write_stream(data):
                    pass
                return (dummy_read_stream(), dummy_write_stream)
            async def __aexit__(self, *args, **kwargs):
                pass
        if not MCP_SDK_AVAILABLE:
            raise ImportError("MCP SDK not installed. Please install 'mcp' to use this tool.")
        return DummyStreamableClient()

# Configuration for the MCP server
DEFAULT_MCP_SERVER_URL = "http://localhost:8765/mcp"

# Define the input schema for the tool's Langchain execution
class EmailSenderSDKInput(BaseModel):
    content: str = Field(description="The content of the email to be sent.")
    recipient: str = Field(description="The email address of the recipient.")

# Define the actual Langchain Tool using MCP SDK
class EmailSenderExternalSDKTool(BaseTool):
    name: str = "email_sender_mcp_sdk" # Renamed for SDK
    description: str = (
        "Sends an email by submitting a task to an MCP server using the mcp-sdk. "
        "Returns the status directly."
    )
    args_schema: Type[BaseModel] = EmailSenderSDKInput
    mcp_server_url: str

    def __init__(self, mcp_server_url: str = DEFAULT_MCP_SERVER_URL, **data: Any):
        super().__init__(**data)
        self.mcp_server_url = mcp_server_url if mcp_server_url and mcp_server_url.strip() else DEFAULT_MCP_SERVER_URL

    async def _arun(self, content: str, recipient: str, **kwargs: Any) -> Any:
        if not MCP_SDK_AVAILABLE:
            return {"error": "MCP SDK not installed. Please install 'mcp' to use this tool."}

        print(f"EmailSenderExternalSDKTool: Connecting to MCP server at {self.mcp_server_url} for tool 'email_sender'")

        try:
            async with streamablehttp_client(self.mcp_server_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session: # type: ignore
                    await session.initialize()
                    print(f"EmailSenderExternalSDKTool: Calling MCP tool 'email_sender' for recipient: {recipient}")

                    tool_args = {"content": content, "recipient": recipient}
                    # Consider mcp_types.ToolCallArguments if SDK requires strict typing for arguments
                    # tool_args = mcp_types.ToolCallArguments(argument={"content": content, "recipient": recipient})


                    result = await session.call_tool("email_sender", arguments=tool_args) # type: ignore

                    print(f"EmailSenderExternalSDKTool: Received result from MCP server: {result}")
                    # Expect result to be something like {"status": "success", "message": "Email sent"}
                    return result

        except ImportError:
             return {"error": "MCP SDK is not installed."} # Fallback, should be caught earlier
        except Exception as e:
            print(f"EmailSenderExternalSDKTool: Error during MCP SDK operation: {e} ({type(e).__name__})")
            details = str(e)
            if hasattr(e, 'details'): # Example for more detailed error from SDK
                details = getattr(e, 'details')
            return {"error": f"MCP SDK operation failed: {type(e).__name__} - {details}"}

# Define the Langflow component
class EmailSenderToolComponent(LCToolComponent):
    display_name = "Email Sender Tool (MCP SDK)"
    description = "Sends an email using an MCP server via the mcp-sdk."
    # name = "EmailSenderTool" # Retain original component name for UI consistency
    icon = "Mail"
    tool_class: Type[BaseTool] = EmailSenderExternalSDKTool

    _field_order = ["content", "recipient", "mcp_server_url"] # To influence UI order if needed

    # For LCToolComponent, inputs are often derived. If specific Langflow input types
    # (like MultilineInput for 'content') are desired beyond what Pydantic model hints provide,
    # manual definition or customization of `get_fields_from_class` might be needed.
    # The current setup relies on LCToolComponent's default behavior for args_schema.
    # To explicitly set 'content' as MultilineInput, one might need to override `get_input_fields`
    # or adjust how `inputs` is defined.
    # For this iteration, we use the default derivation and add mcp_server_url.

    inputs = LCToolComponent.get_fields_from_class(tool_class) + [
        SecretStrInput(
            name="mcp_server_url",
            display_name="MCP Server URL",
            info=f"Full URL of the MCP server endpoint (e.g., {DEFAULT_MCP_SERVER_URL}).",
            required=False, # Uses default if not provided
            advanced=True,
            value=DEFAULT_MCP_SERVER_URL
        )
    ]

    def build_tool(self, **kwargs: Any) -> BaseTool:
        if not MCP_SDK_AVAILABLE:
            raise ImportError("MCP SDK not installed. This component requires 'pip install mcp'.")

        mcp_url = kwargs.pop("mcp_server_url", DEFAULT_MCP_SERVER_URL)
        if not mcp_url or not mcp_url.strip():
            mcp_url = DEFAULT_MCP_SERVER_URL

        # kwargs for tool constructor should be empty here, as content/recipient are _arun params
        return self.tool_class(mcp_server_url=mcp_url)


async def main():
    if not MCP_SDK_AVAILABLE:
        print("MCP SDK not available, skipping main test logic for EmailSenderTool.")
        return

    print("EmailSenderToolComponent (SDK version) conceptual test:")
    component = EmailSenderToolComponent()

    try:
        tool_default_url = component.build_tool(mcp_server_url="")
        print(f"Tool built with MCP URL: {tool_default_url.mcp_server_url}") # type: ignore
        assert tool_default_url.mcp_server_url == DEFAULT_MCP_SERVER_URL # type: ignore

        custom_url = "http://my-mcp-server.org/mcp_email_path"
        tool_custom_url = component.build_tool(mcp_server_url=custom_url)
        print(f"Tool built with MCP URL: {tool_custom_url.mcp_server_url}") # type: ignore
        assert tool_custom_url.mcp_server_url == custom_url # type: ignore

        print("\nEmailSenderExternalSDKTool instance can be created with different MCP URLs.")
        print("Standalone _arun test would require a running MCP server and the 'mcp' SDK installed.")

        # Example of how _arun might be called (requires mock server & SDK):
        # print("\nSimulating _arun call (requires actual MCP server and SDK)...")
        # test_content = "Hello from Langflow via MCP SDK!"
        # test_recipient = "sdk_test@example.com"
        # # Assuming tool_custom_url is correctly initialized
        # # status = await tool_custom_url._arun(content=test_content, recipient=test_recipient)
        # # print(f"Result from _arun for sending email to '{test_recipient}': {status}")

    except ImportError as e:
        print(f"ImportError during main test: {e}")


if __name__ == "__main__":
    # To run main effectively, LCToolComponent and its methods like get_fields_from_class
    # would need to be available in the execution context, or mocked.
    # asyncio.run(main())
    print("To run main for EmailSenderToolComponent (SDK), LCToolComponent context is needed or mocks for its methods.")
    pass
```
