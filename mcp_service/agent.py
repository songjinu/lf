import asyncio
import httpx
import json
from typing import Type, Any, Dict, List, Optional
from langchain_core.tools import BaseTool
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI # Using OpenAI for agent capabilities
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Assuming models.py is in the same directory level
from mcp_service.models import ReportRequest, EmailRequest, ToolProgress

# --- Configuration ---
MCP_SERVER_URL = "http://localhost:8000" # Make sure the server is running
# Ensure OPENAI_API_KEY is set in your environment for ChatOpenAI

# --- Custom Langchain Tools for SSE communication ---

class SSERequestError(Exception):
    """Custom exception for errors during SSE requests."""
    pass

async def _stream_sse_tool(url: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Helper function to connect to an SSE endpoint and collect all messages."""
    all_progress = []
    try:
        async with httpx.AsyncClient(timeout=60.0) as client: # Increased timeout for long tasks
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_content = await response.aread()
                    raise SSERequestError(f"Server error {response.status_code}: {error_content.decode()}")

                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_json = line[len("data:"):].strip()
                        try:
                            data = json.loads(data_json)
                            all_progress.append(data)
                            # Optional: print(f"SSE Data: {data}")
                            if data.get("step") == "error" or data.get("status") == "failed":
                                print(f"Error from tool stream: {data.get('details')}")
                                # Depending on desired behavior, could raise an error here
                        except json.JSONDecodeError:
                            print(f"Warning: Could not decode JSON from SSE stream: {data_json}")
                    elif line.startswith("event: error"):
                        # This might be redundant if data part also contains error, but good for explicit server error events
                        print(f"SSE Event Error: {line}") # Further parsing might be needed based on server.py error format
                    elif line.startswith("event: eof"):
                        print("End of SSE stream.")
                        break
    except httpx.RequestError as e:
        raise SSERequestError(f"HTTP request to SSE endpoint failed: {e}")
    except Exception as e:
        raise SSERequestError(f"An unexpected error occurred while streaming SSE: {e}")
    return all_progress


class ReportToolInput(BaseModel):
    report_type: str = Field(description="Type of report to generate, e.g., 'weekly', 'monthly'")
    # recipient_email is not directly used by this tool, but might be part of a larger flow.
    # The agent should decide to call the email tool separately.

class EmailToolInput(BaseModel):
    to_email: str = Field(description="Recipient email address")
    subject: str = Field(description="Subject of the email")
    body: str = Field(description="Body content of the email")
    attachment_path: Optional[str] = Field(None, description="Path to a file to attach (mocked)")


class GenerateReportSSETool(BaseTool):
    name: str = "generate_report_sse"
    description: str = "Generates a report (e.g., 'weekly', 'monthly summary') and streams progress. Returns all progress updates including the final one with report details."
    args_schema: Type[BaseModel] = ReportToolInput

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        # Langchain tools are often synchronous by default in their _run methods.
        # We'll use asyncio.run to call our async helper.
        # For a fully async agent, this would be _arun.
        raise NotImplementedError("This tool must be run with `arun`")

    async def _arun(self, report_type: str, **kwargs: Any) -> List[Dict[str, Any]]:
        payload = ReportRequest(report_type=report_type).model_dump()
        url = f"{MCP_SERVER_URL}/tools/report"
        try:
            return await _stream_sse_tool(url, payload)
        except SSERequestError as e:
            return [{"error": str(e)}] # Return error as part of the result

class SendEmailSSETool(BaseTool):
    name: str = "send_email_sse"
    description: str = "Sends an email with the given details and streams progress. Takes recipient email, subject, body, and an optional attachment path."
    args_schema: Type[BaseModel] = EmailToolInput

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("This tool must be run with `arun`")

    async def _arun(self, to_email: str, subject: str, body: str, attachment_path: Optional[str] = None, **kwargs: Any) -> List[Dict[str, Any]]:
        payload = EmailRequest(to_email=to_email, subject=subject, body=body, attachment_path=attachment_path).model_dump()
        url = f"{MCP_SERVER_URL}/tools/email"
        try:
            return await _stream_sse_tool(url, payload)
        except SSERequestError as e:
            return [{"error": str(e)}]

# --- Agent Setup ---
def create_mcp_agent():
    # Ensure OPENAI_API_KEY is in env
    llm = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0) # Or gpt-4 if available/needed
    tools = [GenerateReportSSETool(), SendEmailSSETool()]

    # More descriptive prompt for the agent to understand sequential tasks and SSE nature
    # The prompt needs to guide the agent on how to interpret "주간보고를 작성해서, 메일로 보내줘"
    # Specifically, it needs to understand:
    # 1. First, generate the report.
    # 2. Then, use information from the report generation (like the file path) to send the email.
    # This requires the agent to "remember" the output of the first tool for the second.
    prompt_template = ChatPromptTemplate.from_messages([
        SystemMessage(content=(
            "You are a helpful assistant that can manage reports and emails using specialized tools. "
            "When asked to generate a report and then email it, you must first use the 'generate_report_sse' tool. "
            "Inspect its output carefully; the final progress update should contain the 'details' field with the report's file path (e.g., 'Report generated: /tmp/reports/report_....pdf'). "
            "You must then use this file path as the 'attachment_path' for the 'send_email_sse' tool. "
            "The tools provide progress updates as a list of JSON objects via Server-Sent Events (SSE). The final result from a tool call will be this list."
            "If a user asks for a task like 'Create a weekly report and send it by email', break it down: "
            "1. Call `generate_report_sse` with the report type (e.g., 'weekly'). "
            "2. Examine the result from `generate_report_sse`. Find the message where `status` is 'completed'. The `details` field of this message will contain the file path. "
            "3. Call `send_email_sse`, using the extracted file path as `attachment_path`. You might need to ask the user for the recipient email if not provided."
        )),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        HumanMessage(content="{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    agent = create_openai_functions_agent(llm, tools, prompt_template)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    return agent_executor

async def run_agent_query(agent_executor: AgentExecutor, query: str):
    print(f"\nRunning agent with query: '{query}'")
    # For agents that might have conversational memory, you'd pass chat_history
    # For this stateless example, it's simpler.
    response = await agent_executor.ainvoke({"input": query})
    print("\nAgent Response:")
    print(response.get("output", "No output field in response"))

    # If you want to see the intermediate steps and tool calls:
    # This part might need to be adjusted based on how create_openai_functions_agent structures its response
    # when return_intermediate_steps=True is used with AgentExecutor.
    # For now, focusing on the final output.

async def main():
    # This is a basic test.
    # Ensure your MCP server (mcp_service/server.py) is running in a separate terminal.
    # Also, ensure OPENAI_API_KEY environment variable is set.

    print("Initializing MCP Agent...")
    mcp_agent_executor = create_mcp_agent()

    # Test case 1: Simple report generation
    # await run_agent_query(mcp_agent_executor, "Generate a monthly sales report.")

    # Test case 2: Simple email sending
    # await run_agent_query(mcp_agent_executor, "Send an email to manager@example.com with subject 'Update' and body 'System is now online.'")

    # Test case 3: Combined task as per user request
    # "주간보고를 작성해서, 메일로 보내줘" (Create a weekly report and send it via email)
    # The agent might need to ask for the recipient email for the second part.
    # Or we can provide it in the prompt if known.
    korean_query = "주간보고를 작성해서, john.doe@example.com 에게 메일로 보내줘"
    await run_agent_query(mcp_agent_executor, korean_query)

    # Example of direct tool testing (without agent, useful for debugging tools)
    # print("\nDirectly testing GenerateReportSSETool:")
    # report_tool = GenerateReportSSETool()
    # report_result = await report_tool.arun(report_type="adhoc_summary")
    # print(f"Report tool direct result: {report_result}")

    # print("\nDirectly testing SendEmailSSETool:")
    # email_tool = SendEmailSSETool()
    # # Assuming a report was generated and we have a path
    # mock_report_path = "/tmp/reports/report_example_adhoc_summary.pdf"
    # email_result = await email_tool.arun(
    #     to_email="test@example.com",
    #     subject="Adhoc Summary Report",
    #     body=f"Please find attached the adhoc summary report: {mock_report_path}",
    #     attachment_path=mock_report_path
    # )
    # print(f"Email tool direct result: {email_result}")


if __name__ == "__main__":
    # This requires OPENAI_API_KEY to be set in the environment
    # And the mcp_service.server to be running (uvicorn mcp_service.server:app --reload --port 8000)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error running agent main: {e}")
        print("Please ensure your OpenAI API key is set and the MCP server is running on port 8000.")
