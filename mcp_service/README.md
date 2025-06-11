# MCP Service for Asynchronous Tools (Report & Email)

This project implements an MCP (Mission Control Proxy, metaphorically) server that provides asynchronous tools for generating reports and sending emails. Communication with these tools is handled via Server-Sent Events (SSE). A Langchain agent is also provided to interact with these tools.

## Project Structure

- `models.py`: Contains Pydantic models for request/response structures and tool progress.
- `tools.py`: Implements the core asynchronous logic for the mock reporting and emailing tools.
- `server.py`: A FastAPI server that exposes the tools via SSE endpoints.
- `agent.py`: A Langchain agent equipped with custom tools to interact with the MCP server.
- `pyproject.toml`: Project metadata and dependencies.

## Setup

This project uses `uv` for environment and package management.

1.  **Navigate to the service directory:**
    ```bash
    cd mcp_service
    ```

2.  **Install dependencies using `uv`:**
    If you haven't installed `uv` yet, you might need to do that first (e.g., `pip install uv`).
    The `pyproject.toml` file lists all necessary dependencies. `uv` should automatically create or use a virtual environment.
    ```bash
    uv pip install -e .
    ```
    The `-e .` will install the current package in editable mode, including its dependencies. If you encounter issues with `uv` finding system packages or requiring a virtual environment, you might need to explicitly create one (e.g., `uv venv` and then `source .venv/bin/activate`) before installing.

3.  **Set Environment Variables:**
    For the Langchain agent to function (as it uses OpenAI's model by default), you need to set your OpenAI API key:
    ```bash
    export OPENAI_API_KEY="your_openai_api_key_here"
    ```

## Running the MCP Server

The FastAPI server exposes the tools over SSE.

1.  **Start the server:**
    Make sure you are in the `mcp_service` directory or that `mcp_service.server:app` is accessible in your Python path.
    ```bash
    uvicorn mcp_service.server:app --reload --port 8000
    ```
    The server will be available at `http://localhost:8000`. You can check its status by navigating to this URL in your browser.

## Running the Langchain Agent

The agent can understand natural language queries and use the tools provided by the MCP server.

1.  **Ensure the MCP server is running** (see previous step).
2.  **Run the agent script:**
    This script contains examples, including the primary use case: "주간보고를 작성해서, 메일로 보내줘" (Create a weekly report and send it via email).
    ```bash
    python mcp_service/agent.py
    ```
    Observe the output in the console. The agent will show its thought process (if `verbose=True`) and the results from tool interactions, including SSE progress messages.

## How it Works

1.  **Tools (`tools.py`)**: Simulate long-running tasks by using `asyncio.sleep` and `yield` progress updates. Each update is a `ToolProgress` Pydantic model.
2.  **Server (`server.py`)**:
    -   Uses FastAPI for routing.
    -   Employs `sse-starlette`'s `EventSourceResponse` to stream tool progress to the client.
    -   Endpoints like `/tools/report` and `/tools/email` accept POST requests with parameters defined in `models.py`.
3.  **Agent (`agent.py`)**:
    -   Uses Langchain's agent framework with `ChatOpenAI`.
    -   Custom tools (`GenerateReportSSETool`, `SendEmailSSETool`) are defined. These tools make HTTP POST requests to the MCP server.
    -   The `_stream_sse_tool` helper function in `agent.py` handles the SSE connection, listens for messages, and collects them.
    -   The agent's prompt is engineered to understand multi-step tasks, such as generating a report and then using its output (file path) to send an email.

## Example Query for the Agent

The primary example handled is:
`"주간보고를 작성해서, john.doe@example.com 에게 메일로 보내줘"`
(Create a weekly report and send it by email to john.doe@example.com)

The agent should:
1.  Call the `generate_report_sse` tool to create a "주간보고" (weekly report).
2.  Extract the mock file path from the report tool's output.
3.  Call the `send_email_sse` tool, using the extracted file path as an attachment, and send it to the specified email.

## Future Considerations / `fastmcp`

-   The current implementation uses standard FastAPI and `sse-starlette` for SSE. If `fastmcp` has specific client/server components for SSE or tool definition, they would be integrated into `server.py` and the Langchain tool implementations in `agent.py`.
-   The `fastmcp` dependency was included in `pyproject.toml`. If it provides utilities that simplify any of the above, the code could be refactored to use them. For example, `fastmcp` might offer wrappers or base classes for tools or SSE handling.
