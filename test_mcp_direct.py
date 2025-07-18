
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient


async def test_get_mcp_tools():
    client = MultiServerMCPClient(
        {
            # # 数学计算 sse  --> server-math-sse.py
            "math-sse": {
                "url":"http://localhost:9090/sse/",
                "transport": "sse"
            },
            # 数学计算 stdio --> server-math-stdio.py
            # "math-stdio": {
            #     "command": "python",
            #     "args": ["src/example/server-math-stdio.py"],
            #     "transport": "stdio",
            # }
        }
    )

    tools = await client.get_tools()

    print(tools)

if __name__ == "__main__":
    asyncio.run(test_get_mcp_tools()) 