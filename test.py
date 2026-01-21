# from typing import Optional
# from contextlib import AsyncExitStack

# from openai import OpenAI

# exit_stack = AsyncExitStack()
# model = "Qwen/Qwen2.5-72B-Instruct"
# api_base = "http://180.85.206.19:8123/v1"
# api_key = "local"
# client = OpenAI(
#             api_key=self.api_key,
#             base_url=self.api_base
#         )
# session: Optional[ClientSession] = None
# promt="你可以做什么"
#  response = client.completions.create(
#                 model=model,
#                 prompt=prompt,
#                 max_tokens=200,
#                 temperature=0.7
#             )
#  print("response",response)

from typing import Optional
from contextlib import AsyncExitStack
from openai import OpenAI
import asyncio
from aiohttp import ClientSession

# 配置参数
model = "openai/Qwen/Qwen2.5-72B-Instruct"
api_base = "http://180.85.206.19:8123/v1"
api_key = "local"

class LLMClient:
    def __init__(self):
        self.api_key = api_key
        self.api_base = api_base
        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )

    async def __aenter__(self):
        # 初始化异步资源
        self.session = ClientSession()
        await self.exit_stack.enter_async_file(self.session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 释放异步资源
        await self.exit_stack.aclose()

    async def chat(self, prompt: str):
        # 使用 OpenAI 兼容的 API 发送请求
        try:
            response = self.client.completions.create(
                model=model,
                prompt=prompt,
                max_tokens=200,
                temperature=0.7
            )
            return response.choices[0].text.strip()
        except Exception as e:
            print(f"Error occurred: {e}")
            return None

# 示例用法
async def main():
    async with LLMClient() as client:
        user_input = "请介绍一下你自己。"
        response = await client.chat(user_input)
        print("Model response:", response)

if __name__ == "__main__":
    asyncio.run(main())
