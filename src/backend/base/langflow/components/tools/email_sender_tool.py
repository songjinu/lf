import asyncio
from typing import cast, Type, Optional, Any, Dict, List
from uuid import uuid4

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool # BaseTool is Langchain's, Tool could be Langflow's specific type alias
from langflow.inputs import MessageTextInput, MultilineInput
from langflow.schema import Data
from langflow.services.deps import get_task_service, get_socket_service
from langflow.utils.pending_tasks_store import set_task_result

# Define the input schema for the tool
class EmailSenderInput(BaseModel):
    content: str = Field(description="The content of the email to be sent.")
    recipient: str = Field(description="The email address of the recipient.")
    callback_url: Optional[str] = Field(description="Optional callback URL to send status to.", default=None)

# Define the actual Langchain Tool
class EmailSenderLangchainTool(BaseTool):
    name: str = "email_sender"
    description: str = "Sends an email with the given content to the recipient and returns a task_id. Status is sent via callback."
    args_schema: Type[BaseModel] = EmailSenderInput
    task_service: Any # Will be injected
    socket_service: Any # Will be injected for callback simulation

    def _run(self, content: str, recipient: str, callback_url: Optional[str] = None, **kwargs: Any) -> str:
        raise NotImplementedError("Use arun for asynchronous operation")

    async def _arun(self, content: str, recipient: str, callback_url: Optional[str] = None, **kwargs: Any) -> str:
        task_id = uuid4().hex

        async def actual_email_task(content: str, recipient: str, task_id: str, callback_url: Optional[str], session_id: Optional[str] = None):
            await asyncio.sleep(1) # Simulate email sending delay
            email_status = f"Email to {recipient} with content snippet '{content[:30]}...' sent successfully."

            log_message = f"MCP Server (EmailSenderTool): Task {task_id} complete. Result: {email_status}. Calling back to {callback_url or 'internal handler'}."
            print(log_message) # Keep for logging

            # Store result for WaitForTaskResultTool
            set_task_result(task_id, {"status": "success", "message": email_status})

            if self.socket_service and callback_url is None:
                if session_id:
                    await self.socket_service.emit_message(to=session_id, data={
                        "type": "tool_callback",
                        "task_id": task_id,
                        "tool_name": self.name,
                        "results": {"status": "success", "message": email_status}
                    })
                else:
                    print(f"Warning: session_id not provided for internal callback for task {task_id}. Cannot emit socket message.")
            elif callback_url:
                # In a real scenario, you'd make an HTTP POST request to callback_url
                # Example:
                # async with aiohttp.ClientSession() as session:
                #     await session.post(callback_url, json={"task_id": task_id, "results": {"status": "success", "message": email_status}})
                print(f"MCP Server: Would attempt HTTP POST to {callback_url} with status for task {task_id}.")
                pass # Placeholder for actual HTTP callback

            return {"task_id": task_id, "status": "completed", "message": email_status} # This return is for the task_service

        print(f"EmailSenderTool: Received request to send email to '{recipient}'. Requesting MCP server to process. Task ID will be {task_id}.")

        session_id = kwargs.get("session_id")

        await self.task_service.launch_task(actual_email_task, content, recipient, task_id, callback_url, session_id)

        return f"Task {task_id} initiated for sending email to {recipient}. Status will be sent via callback to {callback_url or 'internal handler (requires session_id)'}."

# Define the Langflow component
class EmailSenderToolComponent(LCToolComponent):
    display_name = "Email Sender Tool (Async)"
    description = "A tool that simulates sending an email and returns a task_id. Status is delivered via callback."
    name = "EmailSenderTool"
    icon = "Mail"

    inputs = [
        MultilineInput(
            name="content",
            display_name="Email Content",
            info="The full content of the email."
        ),
        MessageTextInput(
            name="recipient",
            display_name="Recipient Email",
            info="The email address of the recipient."
        ),
        MessageTextInput(
            name="callback_url",
            display_name="Callback URL (Optional)",
            info="If provided, status will be POSTed to this URL. Otherwise, internal handling via websockets (requires session_id).",
            required=False,
            advanced=True,
        )
    ]

    def build_tool(self) -> BaseTool: # Should return BaseTool as per LCToolComponent's expectation
        task_service = get_task_service()
        socket_service = get_socket_service()

        tool_instance = EmailSenderLangchainTool(
            task_service=task_service,
            socket_service=socket_service
        )
        return cast(BaseTool, tool_instance) # Ensure it's cast to BaseTool if there's any ambiguity with langflow.field_typing.Tool

    def _build_wrapper(self): # Minimal implementation as build_tool is primary
        pass

# To make it runnable for testing if needed
async def main():
    class MockTaskService:
        async def launch_task(self, func, *args, **kwargs):
            # Simplified arg passing for the mock
            _content, _recipient, _task_id, _callback_url, _session_id = args[0], args[1], args[2], args[3], args[4]
            print(f"MockTaskService: Launching {func.__name__} for recipient '{_recipient}', task_id='{_task_id}', callback_url='{_callback_url}', session_id='{_session_id}'")
            asyncio.create_task(func(_content, _recipient, _task_id, _callback_url, _session_id))
            return "mock_task_instance_id"

    class MockSocketService:
        async def emit_message(self, to, data):
            print(f"MockSocketService: Emitting message to {to}: {data}")

    # Instantiate services
    mock_task_service = MockTaskService()
    mock_socket_service = MockSocketService()

    # Create tool instance
    tool = EmailSenderLangchainTool(task_service=mock_task_service, socket_service=mock_socket_service)

    print("\n--- Test Case 1: Email to editor (with callback_url) ---")
    task_id_info_1 = await tool._arun(
        content="Hello Editor, here is the draft of the article.",
        recipient="editor@example.com",
        callback_url="http://localhost:8000/editor_callback",
        session_id="user_editor_session"
    )
    print(f"Tool output 1: {task_id_info_1}")

    await asyncio.sleep(2) # Allow task 1 to simulate completion

    print("\n--- Test Case 2: Email to reviewer (internal callback) ---")
    task_id_info_2 = await tool._arun(
        content="Hi Reviewer, please take a look at this submission.",
        recipient="reviewer@example.com",
        callback_url=None, # Implies internal handling
        session_id="user_reviewer_session" # Crucial for internal callback
    )
    print(f"Tool output 2: {task_id_info_2}")

    await asyncio.sleep(3) # Allow all background tasks to complete

if __name__ == "__main__":
    asyncio.run(main())
```
