import asyncio
from typing import cast, Type, Optional, Any, Dict, List
from uuid import uuid4

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool
from langflow.inputs import MessageTextInput, MultilineInput
from langflow.schema import Data
from langflow.services.deps import get_task_service, get_socket_service # Assuming socket_service for callback simulation
from langflow.utils.pending_tasks_store import set_task_result

# Define the input schema for the tool
class NewsSearchInput(BaseModel):
    query: str = Field(description="The search query for news articles.")
    callback_url: Optional[str] = Field(description="Optional callback URL to send results to.", default=None)

# Define the actual Langchain Tool
class NewsSearchLangchainTool(BaseTool):
    name: str = "news_search"
    description: str = "Searches for news articles based on a query and returns a task_id. Results are sent via callback."
    args_schema: Type[BaseModel] = NewsSearchInput
    task_service: Any # Will be injected
    socket_service: Any # Will be injected for callback simulation

    def _run(self, query: str, callback_url: Optional[str] = None, **kwargs: Any) -> str:
        # This is the synchronous version, but Langchain agents usually call arun for async tools
        raise NotImplementedError("Use arun for asynchronous operation")

    async def _arun(self, query: str, callback_url: Optional[str] = None, **kwargs: Any) -> str:
        task_id = uuid4().hex

        # Simulate launching the task on the MCP server
        # In a real scenario, this would be a more complex task_func
        async def actual_search_task(query: str, task_id: str, callback_url: Optional[str], session_id: Optional[str] = None):
            await asyncio.sleep(2) # Simulate network delay and processing
            search_results = [
                {"title": f"Article on {query} 1", "snippet": "Details about AI news 1..."},
                {"title": f"Article on {query} 2", "snippet": "More details about AI news 2..."},
            ]

            # Simulate MCP server calling the callback_url
            log_message = f"MCP Server (NewsSearchTool): Task {task_id} complete. Result for '{query}': {search_results}. Calling back to {callback_url or 'internal handler'}."
            print(log_message) # Keep for logging

            # Store result for WaitForTaskResultTool
            set_task_result(task_id, {"status": "completed", "results": search_results})

            # If a socket_service is available (for internal simulation), emit an event
            if self.socket_service and callback_url is None: # Assuming internal callbacks use socket for this example
                if session_id: # Make sure session_id is available for targeted emit
                    await self.socket_service.emit_message(to=session_id, data={
                        "type": "tool_callback",
                        "task_id": task_id,
                        "tool_name": self.name,
                        "results": search_results
                    })
                else:
                    # Fallback or error if session_id is crucial for internal callbacks
                    print(f"Warning: session_id not provided for internal callback for task {task_id}. Cannot emit socket message.")
            elif callback_url:
                # In a real scenario, you'd make an HTTP POST request to callback_url
                # Example:
                # async with aiohttp.ClientSession() as session:
                #     await session.post(callback_url, json={"task_id": task_id, "results": search_results})
                print(f"MCP Server: Would attempt HTTP POST to {callback_url} with results for task {task_id}.")
                pass # Placeholder for actual HTTP callback

            return {"task_id": task_id, "status": "completed", "results": search_results} # This return is for the task_service, not the agent tool


        print(f"NewsSearchTool: Received query '{query}'. Requesting MCP server to process. Task ID will be {task_id}.")

        # The session_id should be passed from the agent's context if available
        # It's crucial for socket_service to target the correct client.
        session_id = kwargs.get("session_id")

        # Using task_service to run the simulated async task
        await self.task_service.launch_task(actual_search_task, query, task_id, callback_url, session_id)

        return f"Task {task_id} initiated for news search: {query}. Results will be sent via callback to {callback_url or 'internal handler (requires session_id)'}."


# Define the Langflow component
class NewsSearchToolComponent(LCToolComponent):
    display_name = "News Search Tool (Async)"
    description = "A tool that simulates searching for news and returns a task_id. Results are delivered via callback."
    name = "NewsSearchTool"
    icon = "FileSearch"

    inputs = [
        MessageTextInput(
            name="query",
            display_name="Search Query",
            info="The query to search for news articles."
        ),
        MessageTextInput(
            name="callback_url",
            display_name="Callback URL (Optional)",
            info="If provided, results will be POSTed to this URL. Otherwise, internal handling via websockets (requires session_id).",
            required=False,
            advanced=True,
        )
    ]

    def build_tool(self) -> BaseTool:
        task_service = get_task_service()
        socket_service = get_socket_service()

        tool_instance = NewsSearchLangchainTool(
            task_service=task_service,
            socket_service=socket_service
        )
        return cast(BaseTool, tool_instance) # Return as BaseTool, Langflow handles the rest

    # _build_wrapper is not strictly needed if build_tool is correctly implemented
    # and the component primarily serves as a factory for a Langchain BaseTool.
    # LCToolComponent's primary role is to adapt a BaseTool for Langflow.


# To make it runnable for testing if needed (outside Langflow context)
async def main():
    class MockTaskService:
        async def launch_task(self, func, *args, **kwargs):
            # Extract actual keyword arguments for the function if they are at the end of args
            # This is a simplified mock; a real TaskService might have a more robust way to pass args/kwargs
            actual_func_args = args[:-len(kwargs)] if kwargs else args
            actual_func_kwargs = {k:v for i, (k,v) in enumerate(kwargs.items())} #This is wrong, need to fix

            # A better way to handle args for the mock, assuming args are positional and kwargs are named
            # Let's assume the last few positional arguments might be kwargs if not explicitly named
            # For this specific case: actual_search_task(query, task_id, callback_url, session_id)

            _query, _task_id, _callback_url, _session_id = args[0], args[1], args[2], args[3]

            print(f"MockTaskService: Launching {func.__name__} with query='{_query}', task_id='{_task_id}', callback_url='{_callback_url}', session_id='{_session_id}'")
            asyncio.create_task(func(_query, _task_id, _callback_url, _session_id)) # Run in background
            return "mock_task_instance_id"

    class MockSocketService:
        async def emit_message(self, to, data):
            print(f"MockSocketService: Emitting message to {to}: {data}")

    # Instantiate services
    mock_task_service = MockTaskService()
    mock_socket_service = MockSocketService()

    # Create tool instance with mocked services
    tool = NewsSearchLangchainTool(task_service=mock_task_service, socket_service=mock_socket_service)

    print("\n--- Test Case 1: With callback_url ---")
    # Pass kwargs to _arun, which will be forwarded. session_id is not strictly needed here as callback_url is provided.
    task_id_1_info = await tool._arun(query="AI in healthcare", callback_url="http://localhost:8000/callback", session_id="user_session_for_test1")
    print(f"Tool output 1: {task_id_1_info}")

    await asyncio.sleep(3) # Allow task 1 to simulate completion

    print("\n--- Test Case 2: Without callback_url (internal handling via socket) ---")
    # session_id is crucial here for the socket emission
    task_id_2_info = await tool._arun(query="Climate change impact", callback_url=None, session_id="user123")
    print(f"Tool output 2: {task_id_2_info}")

    await asyncio.sleep(5) # Allow all background tasks to complete

if __name__ == "__main__":
    asyncio.run(main())
```
