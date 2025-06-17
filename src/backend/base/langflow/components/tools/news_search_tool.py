import asyncio
from typing import cast, Type, Optional, Any, Dict

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import MessageTextInput, SecretStrInput

# Attempt to import MCP SDK components
try:
    from mcp import ClientSession, types as mcp_types # Assuming types might be needed for arguments
    from mcp.client.streamable_http import streamablehttp_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    # Define dummy classes if SDK is not available, to allow module to load
    class ClientSession:
        def __init__(self, *args, **kwargs):
            # This will be raised if someone tries to instantiate it when SDK is not there.
            # The component's build_tool should ideally prevent this.
            if not MCP_SDK_AVAILABLE: # Redundant check, but for clarity
                 raise ImportError("MCP SDK not installed. Please install 'mcp' to use this tool.")
        async def initialize(self, *args, **kwargs):
            pass
        async def call_tool(self, *args, **kwargs):
            # Should not be reached if build_tool checks MCP_SDK_AVAILABLE
            return {"error": "MCP SDK call_tool called on dummy session."}
        async def __aenter__(self):
            # Ensure __aenter__ returns self for the 'async with' context
            return self
        async def __aexit__(self, *args, **kwargs):
            pass

    def streamablehttp_client(*args, **kwargs):
        class DummyStreamableClient:
            async def __aenter__(self):
                # Simulate returning dummy read_stream, write_stream for ClientSession constructor
                async def dummy_read_stream():
                    if False: # Make it an async generator
                        yield b""

                async def dummy_write_stream(data):
                    pass

                return (dummy_read_stream(), dummy_write_stream)
            async def __aexit__(self, *args, **kwargs):
                pass

        # This check is crucial. If the SDK isn't there, this function itself should signal that
        # streamablehttp_client cannot be properly used.
        if not MCP_SDK_AVAILABLE:
             raise ImportError("MCP SDK not installed. Please install 'mcp' to use this tool.")
        return DummyStreamableClient()

# Configuration for the MCP server
DEFAULT_MCP_SERVER_URL = "http://localhost:8765/mcp" # MCP servers often mount at /mcp

# Define the input schema for the tool's Langchain execution
class NewsSearchSDKInput(BaseModel):
    query: str = Field(description="The search query for news articles.")

# Define the actual Langchain Tool using MCP SDK
class NewsSearchExternalSDKTool(BaseTool):
    name: str = "news_search_mcp_sdk" # Renamed to reflect SDK usage
    description: str = (
        "Searches for news articles by submitting a task to an MCP server using the mcp-sdk. "
        "Returns the search results directly."
    )
    args_schema: Type[BaseModel] = NewsSearchSDKInput
    mcp_server_url: str

    def __init__(self, mcp_server_url: str = DEFAULT_MCP_SERVER_URL, **data: Any):
        super().__init__(**data)
        self.mcp_server_url = mcp_server_url if mcp_server_url and mcp_server_url.strip() else DEFAULT_MCP_SERVER_URL

    async def _arun(self, query: str, **kwargs: Any) -> Any: # Return type is Any, could be Dict or List
        if not MCP_SDK_AVAILABLE:
            # This error will be returned if the component was somehow built without the SDK.
            return {"error": "MCP SDK not installed. Please install 'mcp' to use this tool."}

        print(f"NewsSearchExternalSDKTool: Connecting to MCP server at {self.mcp_server_url} for tool 'news_search'")

        try:
            # streamablehttp_client expects the full URL to the MCP endpoint.
            async with streamablehttp_client(self.mcp_server_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session: # type: ignore
                    await session.initialize()
                    print(f"NewsSearchExternalSDKTool: Calling MCP tool 'news_search' with query: {query}")

                    # The tool name 'news_search' must match the name defined on the MCP server.
                    # The arguments must match what the server-side tool expects.
                    # Assuming mcp_types.ToolCallArguments is the correct way if types are strictly enforced by SDK.
                    # For simplicity, passing dict if SDK allows. Let's assume dict is okay for now.
                    tool_args = {"query": query} # mcp_types.ToolCallArguments(argument={"query": query})

                    result = await session.call_tool("news_search", arguments=tool_args) # type: ignore

                    print(f"NewsSearchExternalSDKTool: Received result from MCP server: {result}")
                    # Assuming 'result' is the actual data (e.g., list of articles or a dict)
                    # If the SDK has specific result objects, they might need conversion to dict/list.
                    # e.g. if result is an SDK object: return result.to_dict() or similar
                    return result

        except ImportError: # Should be caught by the top-level check, but good practice
            return {"error": "MCP SDK is not installed."}
        except Exception as e:
            # Catch specific SDK exceptions if known, otherwise general Exception
            print(f"NewsSearchExternalSDKTool: Error during MCP SDK operation: {e} ({type(e).__name__})")
            # Attempt to get more details from the exception if it's an SDK-specific one with more info
            details = str(e)
            if hasattr(e, 'details'): # Example of a potential custom attribute on SDK errors
                details = getattr(e, 'details')
            return {"error": f"MCP SDK operation failed: {type(e).__name__} - {details}"}

# Define the Langflow component
class NewsSearchToolComponent(LCToolComponent):
    display_name = "News Search Tool (MCP SDK)"
    description = "Searches for news using an MCP server via the mcp-sdk."
    # name = "NewsSearchTool" # Retain original component name for UI consistency
    icon = "FileSearch"
    tool_class: Type[BaseTool] = NewsSearchExternalSDKTool

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
            # This error is raised when trying to add/build the component in Langflow if SDK is missing.
            raise ImportError("MCP SDK not installed. This component requires 'pip install mcp'.")

        mcp_url = kwargs.pop("mcp_server_url", DEFAULT_MCP_SERVER_URL)
        if not mcp_url or not mcp_url.strip(): # Ensure not empty or just whitespace
            mcp_url = DEFAULT_MCP_SERVER_URL

        # kwargs should be empty here as 'query' is an _arun parameter, not a constructor one.
        return self.tool_class(mcp_server_url=mcp_url) # Removed **kwargs


async def main():
    if not MCP_SDK_AVAILABLE:
        print("MCP SDK not available, skipping main test logic for NewsSearchTool.")
        return

    print("NewsSearchToolComponent (SDK version) conceptual test:")

    # Simulate component instantiation and tool building
    component = NewsSearchToolComponent()

    # Test with default URL
    try:
        tool_default_url = component.build_tool(mcp_server_url="") # "" should trigger default
        print(f"Tool built with MCP URL: {tool_default_url.mcp_server_url}") # type: ignore
        assert tool_default_url.mcp_server_url == DEFAULT_MCP_SERVER_URL # type: ignore

        # Test with custom URL
        custom_url = "http://my-custom-mcp.com:8000/mcp_custom_path"
        tool_custom_url = component.build_tool(mcp_server_url=custom_url)
        print(f"Tool built with MCP URL: {tool_custom_url.mcp_server_url}") # type: ignore
        assert tool_custom_url.mcp_server_url == custom_url # type: ignore

        print("\nNewsSearchExternalSDKTool instance can be created with different MCP URLs.")
        print("Standalone _arun test would require a running MCP server and the 'mcp' SDK installed.")

        # Example of how it might be called (requires mock server & SDK):
        # print("\nSimulating _arun call (requires actual MCP server and SDK)...")
        # test_query = "latest AI advancements"
        # # Assuming tool_custom_url is correctly initialized
        # # result = await tool_custom_url._arun(query=test_query)
        # # print(f"Result from _arun for query '{test_query}': {result}")

    except ImportError as e:
        print(f"ImportError during main test: {e}") # Should be caught if SDK not installed

if __name__ == "__main__":
    # To run main effectively, LCToolComponent and its methods like get_fields_from_class
    # would need to be available in the execution context, or mocked.
    # asyncio.run(main())
    print("To run main for NewsSearchToolComponent (SDK), LCToolComponent context is needed or mocks for its methods.")
    pass
```
