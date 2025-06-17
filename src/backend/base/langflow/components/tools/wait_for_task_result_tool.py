import asyncio
import re
import time # Imported for the _run method, though _arun is primary
from typing import cast, Type, Any, Dict, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langflow.base.langchain_utilities.model import LCToolComponent
from langflow.field_typing import Tool # Langflow's specific Tool type alias
from langflow.inputs import MessageTextInput, IntInput, FloatInput
from langflow.utils.pending_tasks_store import get_task_result, peek_task_result

# Define the input schema for the tool
class WaitForTaskResultInput(BaseModel):
    task_id_message: str = Field(description="The message containing the task ID, typically from a previous tool call (e.g., 'Task abc123 initiated...').")
    timeout_seconds: int = Field(default=30, description="Maximum time to wait for the task result in seconds.")
    poll_interval: float = Field(default=0.5, description="How often to check for the task result in seconds.")

# Define the actual Langchain Tool
class WaitForTaskResultLangchainTool(BaseTool):
    name: str = "wait_for_task_result"
    description: str = (
        "Waits for the result of an asynchronous task, given a message containing its task_id. "
        "This tool should be used after a tool that initiates an async task and returns a task_id message."
    )
    args_schema: Type[BaseModel] = WaitForTaskResultInput

    def _parse_task_id(self, task_id_message: str) -> Optional[str]:
        # Example message: "Task abc123xyz initiated for news search: AI. Results will be sent via callback."
        # More robust regex: looks for "Task" followed by an alphanumeric ID
        match = re.search(r"Task\s+([a-zA-Z0-9]+)\s+initiated", task_id_message)
        if match:
            parsed_id = match.group(1)
            print(f"WaitForTaskResultTool: Parsed task_id '{parsed_id}' from message: '{task_id_message}'")
            return parsed_id
        # Fallback for just a plain task_id (hex or alphanumeric)
        if re.fullmatch(r"[a-fA-F0-9]{32}", task_id_message): # common 32-char hex
             print(f"WaitForTaskResultTool: Parsed task_id '{task_id_message}' directly (hex).")
             return task_id_message
        if re.fullmatch(r"[a-zA-Z0-9]+", task_id_message): # general alphanumeric
             print(f"WaitForTaskResultTool: Parsed task_id '{task_id_message}' directly (alphanumeric).")
             return task_id_message
        print(f"WaitForTaskResultTool: Could not parse task_id from message: '{task_id_message}'")
        return None

    def _run(self, task_id_message: str, timeout_seconds: int = 30, poll_interval: float = 0.5, **kwargs: Any) -> Any:
        task_id = self._parse_task_id(task_id_message)
        if not task_id:
            return {"error": "Could not parse task_id from the input message.", "input_message": task_id_message}

        print(f"WaitForTaskResultTool (_run): Waiting for task {task_id}. Timeout: {timeout_seconds}s")

        start_time = time.monotonic()
        while (time.monotonic() - start_time) < timeout_seconds:
            result = get_task_result(task_id) # get_task_result pops the result
            if result is not None:
                print(f"WaitForTaskResultTool (_run): Result found for task {task_id}: {result}")
                return result

            time.sleep(poll_interval)
            print(f"WaitForTaskResultTool (_run): Still waiting for task {task_id}...")

        print(f"WaitForTaskResultTool (_run): Timeout waiting for task {task_id}.")
        return {"error": f"Timeout waiting for result of task {task_id}.", "task_id": task_id}

    async def _arun(self, task_id_message: str, timeout_seconds: int = 30, poll_interval: float = 0.5, **kwargs: Any) -> Any:
        task_id = self._parse_task_id(task_id_message)
        if not task_id:
            return {"error": "Could not parse task_id from the input message.", "input_message": task_id_message}

        print(f"WaitForTaskResultTool (_arun): Waiting for task {task_id}. Timeout: {timeout_seconds}s, Poll: {poll_interval}s")

        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            # First, peek to see if the result is there without removing it, for logging
            result_peek = peek_task_result(task_id)
            if result_peek is not None:
                print(f"WaitForTaskResultTool (_arun): Result found for task {task_id} (peek). Will attempt to get.")
                # Brief pause to ensure the task setting the result has fully completed,
                # especially if set_task_result isn't atomic with other operations in the producing task.
                # This is a pragmatic addition for potential race conditions in a simple in-memory store.
                await asyncio.sleep(0.05)
                result = get_task_result(task_id) # Actually get and remove it
                if result is not None: # Double check after get
                    print(f"WaitForTaskResultTool (_arun): Successfully retrieved result for task {task_id}: {result}")
                    return result
                else:
                    # This case might happen if another waiter gets the result between peek and get.
                    # Or if the result was cleared. For this lab, we assume one waiter or result stays until timeout.
                    print(f"WaitForTaskResultTool (_arun): Result was present on peek, but gone on get for task {task_id}. Continuing to wait.")


            remaining_time = timeout_seconds - (asyncio.get_event_loop().time() - start_time)
            if remaining_time <= 0:
                break

            sleep_duration = min(poll_interval, remaining_time)
            await asyncio.sleep(sleep_duration)

            print(f"WaitForTaskResultTool (_arun): Still waiting for task {task_id}... ({(asyncio.get_event_loop().time() - start_time):.1f}s / {timeout_seconds}s)")

        final_peek = peek_task_result(task_id) # One last check after the loop
        if final_peek is not None:
            result = get_task_result(task_id)
            if result is not None:
                print(f"WaitForTaskResultTool (_arun): Result retrieved for task {task_id} just before/at timeout: {result}")
                return result

        print(f"WaitForTaskResultTool (_arun): Timeout waiting for task {task_id} after {(asyncio.get_event_loop().time() - start_time):.1f} seconds.")
        return {"error": f"Timeout waiting for result of task {task_id}.", "task_id": task_id}


# Define the Langflow component
class WaitForTaskResultToolComponent(LCToolComponent):
    display_name = "Wait For Task Result"
    description = "Polls a shared store for the result of an asynchronous task identified by a task_id."
    name = "WaitForTaskResultTool"
    icon = "Clock"

    inputs = [
        MessageTextInput(
            name="task_id_message",
            display_name="Task ID Message",
            info="The message from a previous tool containing the task ID (e.g., 'Task abc123xyz initiated...'). Can also be just the task ID string."
        ),
        IntInput(
            name="timeout_seconds",
            display_name="Timeout (seconds)",
            value=30,
            advanced=True,
            info="Maximum time to wait for the task result."
        ),
        FloatInput(
            name="poll_interval",
            display_name="Poll Interval (seconds)",
            value=0.5,
            advanced=True,
            info="How often to check for the task result."
        )
    ]

    def build_tool(self) -> BaseTool: # Should return BaseTool
        return cast(BaseTool, WaitForTaskResultLangchainTool()) # Cast to BaseTool

    def _build_wrapper(self): # Minimal implementation
        pass

# To make it runnable for testing if needed
async def main():
    from langflow.utils.pending_tasks_store import set_task_result, clear_all_pending_tasks, list_pending_tasks

    tool = WaitForTaskResultLangchainTool()

    async def set_later(delay, task_id, data):
        await asyncio.sleep(delay)
        set_task_result(task_id, data)
        print(f"BACKGROUND TASK: Result set for {task_id}")

    # Test case 1: Result arrives in time
    clear_all_pending_tasks()
    print("\n--- Test Case 1: Result arrives (standard message) ---")
    test_task_id_1 = uuid4().hex
    print(f"Simulating initiation of task {test_task_id_1}...")
    asyncio.create_task(set_later(2, test_task_id_1, {"data": "Test 1 Success!"}))
    result1 = await tool._arun(task_id_message=f"Task {test_task_id_1} initiated for something.", timeout_seconds=5, poll_interval=0.5)
    print(f"Tool output 1: {result1}")
    assert result1 == {"data": "Test 1 Success!"}, f"Test Case 1 Failed: {result1}"
    assert not peek_task_result(test_task_id_1), "Test Case 1 Failed: Result not popped."

    # Test case 2: Timeout
    clear_all_pending_tasks()
    print("\n--- Test Case 2: Timeout ---")
    test_task_id_2 = uuid4().hex
    print(f"Simulating initiation of task {test_task_id_2} (result will not be set)...")
    result2 = await tool._arun(task_id_message=f"Task {test_task_id_2} initiated.", timeout_seconds=2, poll_interval=0.2)
    print(f"Tool output 2: {result2}")
    assert "error" in result2 and "Timeout" in result2["error"], f"Test Case 2 Failed: {result2}"

    # Test case 3: Invalid task_id message
    clear_all_pending_tasks()
    print("\n--- Test Case 3: Invalid message ---")
    result3 = await tool._arun(task_id_message="Some other random message without a parsable ID", timeout_seconds=1)
    print(f"Tool output 3: {result3}")
    assert "error" in result3 and "Could not parse task_id" in result3["error"], f"Test Case 3 Failed: {result3}"

    # Test case 4: Task ID only (direct ID)
    clear_all_pending_tasks()
    print("\n--- Test Case 4: Task ID only ---")
    test_task_id_4 = uuid4().hex
    print(f"Simulating initiation of task {test_task_id_4}...")
    asyncio.create_task(set_later(1, test_task_id_4, {"data": "Test 4 Success!"}))
    result4 = await tool._arun(task_id_message=test_task_id_4, timeout_seconds=3, poll_interval=0.5)
    print(f"Tool output 4: {result4}")
    assert result4 == {"data": "Test 4 Success!"}, f"Test Case 4 Failed: {result4}"
    assert not peek_task_result(test_task_id_4), "Test Case 4 Failed: Result not popped."

    # Test case 5: Result arrives very close to timeout
    clear_all_pending_tasks()
    print("\n--- Test Case 5: Result arrives very close to timeout ---")
    test_task_id_5 = uuid4().hex
    print(f"Simulating initiation of task {test_task_id_5}...")
    asyncio.create_task(set_later(2.8, test_task_id_5, {"data": "Test 5 Success!"}))
    result5 = await tool._arun(task_id_message=f"Task {test_task_id_5} initiated.", timeout_seconds=3, poll_interval=0.5)
    print(f"Tool output 5: {result5}")
    assert result5 == {"data": "Test 5 Success!"}, f"Test Case 5 Failed: {result5}"

    # Test case 6: Poll interval larger than timeout (should check once)
    clear_all_pending_tasks()
    print("\n--- Test Case 6: Poll interval larger than timeout ---")
    test_task_id_6 = uuid4().hex
    print(f"Simulating initiation of task {test_task_id_6}...")
    asyncio.create_task(set_later(0.1, test_task_id_6, {"data": "Test 6 Success!"})) # Result ready quickly
    result6 = await tool._arun(task_id_message=test_task_id_6, timeout_seconds=1, poll_interval=2)
    print(f"Tool output 6: {result6}")
    assert result6 == {"data": "Test 6 Success!"}, f"Test Case 6 Failed: {result6}"

    # Test case 7: Task ID is a simple non-hex alphanumeric string
    clear_all_pending_tasks()
    print("\n--- Test Case 7: Simple alphanumeric Task ID ---")
    test_task_id_7 = "SimpleTaskID1"
    print(f"Simulating initiation of task {test_task_id_7}...")
    asyncio.create_task(set_later(0.5, test_task_id_7, {"data": "Test 7 Success!"}))
    result7 = await tool._arun(task_id_message=test_task_id_7, timeout_seconds=2, poll_interval=0.2)
    print(f"Tool output 7: {result7}")
    assert result7 == {"data": "Test 7 Success!"}, f"Test Case 7 Failed: {result7}"

    print("\nAll tests completed.")
    print(f"Final pending tasks (should be empty if all tests involving results passed): {list_pending_tasks()}")

if __name__ == "__main__":
    asyncio.run(main())
```
