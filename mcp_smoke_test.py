"""用官方 SDK 的客户端，对本项目的 MCP Server 做端到端自测。

它会真的以 stdio 方式拉起 mcp_server.py（和 Claude Desktop 的做法一样），
完成 MCP 握手 → 列出工具 → 实际调用工具。

用法：
    venv\\Scripts\\python.exe mcp_smoke_test.py
"""
import asyncio
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(HERE, "venv", "Scripts", "python.exe")
SERVER = os.path.join(HERE, "mcp_server.py")


async def run():
    params = StdioServerParameters(
        command=PYTHON,
        args=[SERVER],
        cwd=HERE,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("MCP 握手成功 ✅\n")

            tools = await session.list_tools()
            print(f"服务端共暴露 {len(tools.tools)} 个工具：")
            for t in tools.tools:
                desc = (t.description or "").strip().splitlines()
                print(f"  - {t.name:24s} {desc[0] if desc else ''}")

            print("\n" + "=" * 62)
            for name, args in [
                ("list_tables", {}),
                ("table_overview", {"filename": "hny.csv"}),
            ]:
                res = await session.call_tool(name, args)
                text = "\n".join(c.text for c in res.content if getattr(c, "text", None))
                print(f"\n【调用 {name}】")
                print(text[:600])


if __name__ == "__main__":
    asyncio.run(run())