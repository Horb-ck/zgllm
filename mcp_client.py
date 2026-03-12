
# import asyncio
# import os
# import json
# from typing import Optional
# from contextlib import AsyncExitStack
 
# from openai import OpenAI
# from dotenv import load_dotenv
 
# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client
 

 
# class MCPClient:
#     def __init__(self):
#         """初始化 MCP 客户端"""
#         self.exit_stack = AsyncExitStack()
#         self.openai_api_key = "sk-Km4Up8WO0GXHX6vNyzhFN9wBSnkVPWcxYrJ4lwYswE8Ik8PO"
#         self.base_url = "https://aiyjg.lol/v1" 
#         self.model = "deepseek-chat"  
        
#         if not self.openai_api_key:
#             raise ValueError("❌ 未找到 OpenAI API Key，请在 .env 文件中设置 OPENAI_API_KEY")
#         self.client = OpenAI(api_key=self.openai_api_key, base_url=self.base_url) 
#         self.session: Optional[ClientSession] = None
#         self.exit_stack = AsyncExitStack()        
 
#     async def connect_to_server(self, server_script_path: str):
#         """连接到 MCP 服务器并列出可用工具"""
#         is_python = server_script_path.endswith('.py')
#         is_js = server_script_path.endswith('.js')
#         if not (is_python or is_js):
#             raise ValueError("服务器脚本必须是 .py 或 .js 文件")
 
#         command = "python"if is_python else"node"
#         server_params = StdioServerParameters(
#             command=command,
#             args=[server_script_path],
#             env=None
#         )
 
#         # 启动 MCP 服务器
#         stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
#         self.stdio, self.write = stdio_transport
#         self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
 
#         await self.session.initialize()
 

#         response = await self.session.list_tools()
#         tools = response.tools
#         print("\n已连接到服务器，支持以下工具:", [tool.name for tool in tools])     
        
#     async def process_query(self, query: str) -> str:
#         """
#         使用大模型处理查询并调用可用的 MCP 工具 (Function Calling)
#         """
#         messages = [{"role": "user", "content": query}]
        
#         response = await self.session.list_tools()
        
#         available_tools = [{
#             "type": "function",
#             "function": {
#                 "name": tool.name,
#                 "description": tool.description,
#                 "input_schema": tool.inputSchema
#             }
#         } for tool in response.tools]

        
#         response = self.client.chat.completions.create(
#             model=self.model,            
#             messages=messages,
#             tools=available_tools     
#         )
#         print("response",response)
 
#         content = response.choices[0]
#         if content.finish_reason == "tool_calls":
#             tool_call = content.message.tool_calls[0]
#             tool_name = tool_call.function.name
#             tool_args = json.loads(tool_call.function.arguments)
#             result = await self.session.call_tool(tool_name, tool_args)
#             print(f"\n\n[Calling tool {tool_name} with args {tool_args}]\n\n")
#             messages.append(content.message.model_dump())
#             messages.append({
#                 "role": "tool",
#                 "content": result.content[0].text,
#                 "tool_call_id": tool_call.id,
#             })
            
#             response = self.client.chat.completions.create(
#                 model=self.model,
#                 messages=messages,
#             )
#             return response.choices[0].message.content
            
#         return content.message.content
    
#     async def chat_loop(self):
#         """运行交互式聊天循环"""
#         print("\n🤖 MCP 客户端已启动！输入 'quit' 退出")
 
#         while True:
#             try:
#                 query = input("\n你: ").strip()
#                 if query.lower() == 'quit':
#                     break
                
#                 response = await self.process_query(query)  
#                 print(f"\n🤖 OpenAI: {response}")
 
#             except Exception as e:
#                 print(f"\n⚠️ 发生错误: {str(e)}")
 
#     async def cleanup(self):
#         """清理资源"""
#         await self.exit_stack.aclose()
 
# async def main():
#     if len(sys.argv) < 2:
#         print("Usage: python client.py <path_to_server_script>")
#         sys.exit(1)
 
#     client = MCPClient()
#     try:
#         await client.connect_to_server(sys.argv[1])
#         await client.chat_loop()
#     finally:
#         await client.cleanup()
 
# if __name__ == "__main__":
#     import sys
#     asyncio.run(main())


import os
import json
import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from openai import AsyncOpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    def __init__(self):
        """初始化 MCP 客户端，使用你指定的 Qwen 模型"""
        self.exit_stack = AsyncExitStack()
        self.model = "openai/Qwen/Qwen2.5-72B-Instruct"
        self.api_base = "https://api.chatanywhere.com.cn"
        self.api_key = "sk-z6SChqVEGLMV5bQh8SwHaAY4ZmuSuwu84Wz5RBoJZobJzGJc"
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )

        self.session: Optional[ClientSession] = None
        
        # self.loop = None
        
        self._tools_cache = None

    async def connect_to_server(self, server_script_path: str):
        """连接到 MCP 服务器并列出可用工具"""
        
        # self.loop = asyncio.get_event_loop()
        
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 .py 或 .js 文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        # 启动 MCP 服务器
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        print("启动成功")
        
        await self.session.initialize() #卡死在这
        print("初始化会话成功")
        response = await self.session.list_tools()
        print("获取工具集")
        tools = response.tools
        print("\n已连接到服务器，支持以下工具:", [tool.name for tool in tools])
        self._tools_cache = response.tools   # 缓存

    async def process_query(self, query: str) -> str:
        """
        使用大模型处理查询并调用可用的 MCP 工具 (Function Calling)
        """
        
        print("[DEBUG] process_query start")  
        
        messages = [{"role": "user", "content": query}]
        print("messages")
        print("[DEBUG] tools listed", messages)
        # 获取可用工具
        
        print("[DEBUG] session is None?", self.session is None)
        #response = await self.session.list_tools() #卡死在这句代码
        response = self._tools_cache

        # available_tools = [{
        #     "type": "function",
        #     "function": {
        #         "name": tool.name,
        #         "description": tool.description,
        #         "parameters": tool.inputSchema
        #     }
        # } for tool in response.tools]
        available_tools = [{
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
        }} for tool in response] 
        print("[DEBUG] available_tools:", available_tools)
        
        # 第一次调用大模型，决定是否调用工具
        tool_response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=available_tools,
            tool_choice="auto"
        )
        print("1st tool_response:", tool_response)  
        
        choice = tool_response.choices[0]
        message = choice.message

        if message.tool_calls:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # 调用 MCP 工具
            result = await self.session.call_tool(tool_name, tool_args)

            # 构建新的消息历史，让大模型总结结果
            messages.append(message.model_dump())
            messages.append({
                "role": "tool",
                "content": result.content[0].text if result.content else "",
                "tool_call_id": tool_call.id,
            })

            # 第二次调用大模型，返回自然语言结果
            final_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            print("2nd tool_response:", final_response)  
            return final_response.choices[0].message.content
        else:
            return message.content

    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose()


