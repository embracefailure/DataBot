import asyncio 
import json
import os
from typing import Optional 
from openai import AzureOpenAI 
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack

load_dotenv()

class MCPClient:
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
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.history = [{"role": "system", "content": "你是一个智能助手，帮助用户回答问题。"}]


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


    async def connect_to_server(self, server_script_path:str):
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本需要是.py/.js")

        command ="python" if is_python else "node" 
        server_params = StdioServerParameters(
            command = command,
            args = [server_script_path],
            env = None 
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        response = await self.session.list_tools()
        tools = response.tools
        print("\n已连接到服务器,支持以下工具:",[tool.name for tool in tools])
        print("\n描述:",[tool.description for tool in tools])
        print("\n输入格式:",[tool.inputSchema for tool in tools])


    async def process_query(self, query:str) -> str:
        self.history.append({"role":"user","content":query})
        messages = self.history
        response = await self.session.list_tools()

        available_tools = [{
            "type":"function",
            "function":{
                "name":tool.name,
                "description":tool.description,
                "input_schema":tool.inputSchema
            }
        }for tool in response.tools]
        print(f"available_tools:{available_tools}\n")
        
        available_tools = await self.transform_json(available_tools)
        print(f"Transformed available_tools:{available_tools}\n")

        response = self.client.chat.completions.create(
            model = self.deployment_name,
            messages = messages,
            tools = available_tools
        )

        content = response.choices[0]
        if content.finish_reason == "tool_calls":
            tool_call = content.message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            result = await self.session.call_tool(tool_name,tool_args)
            print(tool_args)
            print(f"\n\n[Calling tool {tool_name} with args {tool_args}]\n\n")

            self.history.append(content.message.model_dump())
            self.history.append({
                "role":"tool",
                "content":result.content[0].text,
                "tool_call_id":tool_call.id,
            })

            response = self.client.chat.completions.create(
                model = self.deployment_name,
                messages = self.history,

            )
            #print(messages)
            #return response.choices[0].message.content
            assistant_content = response.choices[0].message.content
            self.history.append({"role":"assistant","content":assistant_content})
            return assistant_content
        return content.message.content



    async def chat_loop(self):
        "运行聊天循环"
        print("MCP客户端启动,输入quit退出")
        
        while True:
            try:
                query = input("\nQuery:").strip()
                if query.lower() == 'quit':
                    break
                
                response = await self.process_query(query)

                print(f"\n GPT:{response}")

            except Exception as e:
                print(f"error:{str(e)}")

    async def cleanup(self):
        "清理资源"
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) <2 :
        print("Usage:python client.py <path_to_server_script>")
        sys.exit(1)
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys 
    asyncio.run(main())