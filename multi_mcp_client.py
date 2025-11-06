import asyncio
import os
import json

from typing import Optional, Dict
from contextlib import AsyncExitStack

from openai import AzureOpenAI
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

class MultiServerMCPClient:
    def __init__(self):
        "初始化客户端"
        self.session = None 
        self.exit_stack = AsyncExitStack()

        self.azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

        if not self.azure_openai_api_key:
            raise ValueError("未找到 OpenAI API key")

        self.client = AzureOpenAI(api_key=self.azure_openai_api_key,
                                    azure_endpoint=self.azure_endpoint,
                                    api_version=self.api_version
                                    )
        self.sessions: Dict[str, ClientSession] = {}

        self.tools_by_session: Dict[str,list] = {}
        self.all_tools: list = []
        self.tool_call_history: list = [] # 记录工具调用历史

    async def connect_to_servers(self, servers:dict):

        for server_name, script_path in servers.items():
            session = await self._start_one_server(script_path)
            self.sessions[server_name] = session 

            resp = await session.list_tools()
            self.tools_by_session[server_name] = resp.tools

            for tool in resp.tools:
                function_name = f"{server_name}_{tool.name}"

                self.all_tools.append({
                    "type":"function",
                    "function":{
                        "name": function_name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema}
                })

        self.all_tools = await self.transform_json(self.all_tools)
        
        print("\n已经连接到下列服务器:")
        for name in servers:
            print(f"- {name} ({servers[name]})")
        print("\n支持以下工具:")
        for t in self.all_tools:
            print(f"- {t['function']['name']}")

    async def transform_json(self, json2data):
        """
        将Claude function call格式转换为OpenAI function call格式,多余字段直接删除
        :param json2data: Claude function call格式的输入
        :return: OpenAI function call格式的输出
        """
        result = []

        for item in json2data:
            if not isinstance(item, dict) or "type" not in item or "function" not in item:
                continue

            old_func = item["function"]

            if not isinstance(old_func, dict) or "name" not in old_func or "description" not in old_func:
                continue

            new_func = {
                "name": old_func["name"],
                "description": old_func["description"],
                "parameters": {}            
            }

            if "input_schema" in old_func and isinstance(old_func["input_schema"], dict):
                old_schema = old_func["input_schema"]
                new_func["parameters"]["type"] = old_schema.get("type", "object")
                new_func["parameters"]["properties"] = old_schema.get("properties", {})
                new_func["parameters"]["required"] = old_schema.get("required", [])

            new_item = {
                "type" : item["type"],
                "function": new_func
            }
            result.append(new_item)

        return result

    async def _start_one_server(self, script_path:str)-> ClientSession:
        """
        启动单个MCP服务器并返回session
        """
        is_python = script_path.endswith('.py')
        is_js = script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本需要是.py/.js")

        command ="python" if is_python else "node" 
        server_params = StdioServerParameters(
            command = command,
            args = [script_path],
            env = None 
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await session.initialize()
        return session
    
    async def chat_base(self, messages:list)->list:

        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            tools=self.all_tools
        )

        if response.choices[0].finish_reason == "tool_calls":
            while True:
                messages = await self.create_function_response_messages(messages, response)
                response = self.client.chat.completions.create(
                    model=self.deployment_name,
                    messages=messages,
                    tools=self.all_tools
                )
                if response.choices[0].finish_reason != "tool_calls":
                    break

        return response 
    
    async def create_function_response_messages(self, messages, response):
        function_call_messages = response.choices[0].message.tool_calls
        messages.append(response.choices[0].message.model_dump())

        for function_call_message in function_call_messages:
            tool_name = function_call_message.function.name
            tool_args = json.loads(function_call_message.function.arguments)

            function_response = await self._call_mcp_tool(tool_name, tool_args)

            messages.append({
                "role":"tool",
                "content": function_response,
                "tool_call_id": function_call_message.id
            })

        return messages
    
    async def _call_mcp_tool(self, full_tool_name:str, tool_args:dict) -> str:
        """
        根据完整工具名称调用对应MCP服务器的工具
        :param full_tool_name: 完整工具名称,格式为"{server_name}_{tool_name}"
        :param tool_args: 工具参数
        :return: 工具调用结果
        """
        parts = full_tool_name.split("_",1)
        if len(parts) != 2:
            raise ValueError("无效的工具名称:{full_tool_name}")
        
        server_name, tool_name = parts

        session = self.sessions.get(server_name)

        if not session:
            raise ValueError(f"未找到服务器:{server_name}")
        
        #resp = await session.call_tool(tool_name, tool_args)
        #print(resp)
        #return resp.content if resp.content else "工具执行没有输出"

        seq = len(self.tool_call_history) + 1
        print(f"\n[工具调用#{seq}]调用：{full_tool_name}")
        try:
            print(f"输入:{json.dumps(tool_args,ensure_ascii=False)}")
        except Exception:
            print(f"输入：{tool_args}")

        resp = await session.call_tool(tool_name, tool_args)
        output = resp.content if resp.content else "工具执行没有输出"

        self.tool_call_history.append({
            "seq":seq,
            "tool":full_tool_name,
            "args":tool_args,
            "output":output
        })
        try:
            print(f"工具调用输出：{json.dumps(output,ensure_ascii=False)}")
        except Exception:
            print(f"工具调用输出：{output}")

        return output 
    
    async def chat_loop(self):
        print("多服务器MCP客户端启动,输入quit退出")
        #messages = []

        system_prompt = os.getenv("SYSTEM_PROMPT", "你是一个有帮助的助手。")
        messages = [{"role": "system", "content": system_prompt}]

        while True:
            query = input("\nUser:").strip()
            if query.lower() == "quit":
                break
            try:
                messages.append({"role":"user","content":query})
                messages = messages[-20:]
                
                prev_history_len = len(self.tool_call_history)
                response = await self.chat_base(messages)

                messages.append(response.choices[0].message.model_dump())
                result = response.choices[0].message.content

                print(f"\nGPT:{result}")

                new_calls = self.tool_call_history[prev_history_len:]
                if new_calls:
                    print("\n本次请求调用的工具顺序：")
                    for c in new_calls:
                        try:
                            args_str = json.dumps(c['args'], ensure_ascii=False)
                        except Exception:
                            args_str = str(c['args'])
                        try:
                            out_str = json.dumps(c['output'], ensure_ascii=False)
                        except Exception:
                            out_str = str(c['output'])
                        print(f"#{c['seq']} {c['tool']} 输入:{args_str} 输出:{out_str}")
                else:
                    print("\n本次请求未调用任何工具。")

            except Exception as e:
                print(f"error:{str(e)}")

    async def cleanup(self):
        await self.exit_stack.aclose()
    
async def main():
    servers = {
        "SQLServer":"sql_server.py",
        "WeatherServer":"weather_server.py"
    }
    client = MultiServerMCPClient()
    try:
        await client.connect_to_servers(servers)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())


        
