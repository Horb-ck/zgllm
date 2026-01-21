# server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(name="Demo",
               host="0.0.0.0",
                port=8080,
                sse_path='/sse'
                )

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.tool()
def hello_world() -> str:
    """Say hello to the world"""
    return "Hello, world!"


if __name__ == "__main__":
    # mcp.run(transport="sse", host="0.0.0.0", port=8888)
    mcp.run(transport="sse")