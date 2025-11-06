# How to Use

## 1. Configure Environment Variables

Modify the `.env` file in the project root directory and fill in the following variables with your own values:


---

## 2. Add a New MCP Server

- **Step 1:** Place your new server script (e.g., `my_server.py`) in the project directory (alongside `sql_server.py` and `weather_server.py`).
- **Step 2:** Edit the `servers` dictionary in `multi_mcp_client.py` to include your new server. For example:

    ```python
    servers = {
        "SQLServer": "sql_server.py",
        "WeatherServer": "weather_server.py",
        "MyServer": "my_server.py"  # Add this line for your new server
    }
    ```

---

## 3. Run the Program

Use the following command to start the client:

```
uv run multi_mcp_client.py
```

# How It Works

## Overview

`multi_mcp_client.py` is a Python program that connects multiple local MCP servers (each exposing tools/functions) with an Azure OpenAI chat model. It allows the model to call these tools as functions during a conversation, automatically routing requests and responses between the model and the correct server.

---

## Runtime Logic

### 1. Initialization

- Loads environment variables (API keys, endpoints, deployment name, etc.).
- Initializes an Azure OpenAI client.
- Prepares to manage multiple MCP server sessions using `AsyncExitStack`.

### 2. Connecting to MCP Servers

- For each server script (e.g., `sql_server.py`, `weather_server.py`), starts a subprocess and creates a `ClientSession`.
- Discovers available tools from each server and renames them as `{server}_{tool}` to avoid name collisions.
- Converts all tool schemas into the OpenAI function call format.

### 3. Chat and Tool Call Orchestration

- Maintains a conversation history (`messages`).
- Sends user input and conversation history to the Azure OpenAI chat API, along with the list of available tools.
- If the model requests a tool call:
  - Extracts the tool name and arguments.
  - Routes the call to the correct MCP server session.
  - Gets the tool's output and appends it to the conversation as a tool response.
  - Repeats the process if the model requests further tool calls, until a final answer is produced.


### 4. Cleanup

- Ensures all subprocesses and resources are properly closed when the program exits.

---

## Key Methods and Their Roles

- **`__init__`**: Loads configuration, initializes the OpenAI client, and sets up data structures.
- **`connect_to_servers`**: Starts each MCP server, collects tool metadata, and prepares the tool list.
- **`transform_json`**: Converts tool schemas to the OpenAI-compatible format.
- **`_start_one_server`**: Launches a single MCP server and returns its session.
- **`chat_base`**: Handles the main chat logic, including repeated tool call handling.
- **`create_function_response_messages`**: Processes tool call responses and appends them to the conversation.
- **`_call_mcp_tool`**: Routes a tool call to the correct server and logs the result.
- **`chat_loop`**: Runs the interactive user input/output loop.
- **`cleanup`**: Closes all sessions and resources.

---

## How to Build a Program Like This from Scratch

1. **Design the Architecture**
   - Decide how the chat model and tool servers will communicate.
   - Choose protocols (e.g., stdio, HTTP) and libraries for both sides.

2. **Set Up the Environment**
   - Prepare environment variables for API keys and configuration.
   - Install required Python packages (`openai`, `dotenv`, MCP client libraries).

3. **Implement Session Management**
   - Use async context managers to handle multiple server connections.
   - Start each server as a subprocess and wrap it in a session object.

4. **Discover and Register Tools**
   - Query each server for its available tools.
   - Normalize tool names and schemas for the chat model.

5. **Implement the Chat Loop**
   - Collect user input and maintain conversation history.
   - Send messages and tool definitions to the chat model.
   - Detect and handle tool calls by routing them to the correct server.
   - Feed tool outputs back to the model until a final answer is produced.

6. **Handle Cleanup**
   - Ensure all subprocesses and resources are closed on exit.

7. **Test and Improve**
   - Add error handling, logging, and unit tests.
   - Refine the user experience and tool integration as needed.

---

## Example Flow

1. User asks a question (e.g., "Show me all users who registered in 2025.").
2. The chat model decides to call the `SQLServer_query_users` tool.
3. The client routes the call to the SQLServer MCP session.
4. The server executes the SQL query and returns the list of users who registered in 2025.
5. The model uses the tool output to generate a final answer for the user.

---