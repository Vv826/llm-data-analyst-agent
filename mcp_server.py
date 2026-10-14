"""把本项目的表格分析能力与知识库检索，暴露成标准 MCP Server。

任何支持 MCP 的客户端（Claude Desktop、Cursor、自研 Agent 等）都能直接调用这里的工具，
**无需修改本项目任何代码**。

启动（stdio 传输，由 MCP 客户端拉起）：
    venv\\Scripts\\python.exe mcp_server.py

本地自测：
    venv\\Scripts\\python.exe mcp_smoke_test.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 注意：mcp 2.x 把 FastMCP 改名成了 MCPServer（v1 的 mcp.server.fastmcp 在 2.x 会导入失败）
from mcp.server.mcpserver import MCPServer

import main

# MCP 客户端会以任意工作目录拉起本进程，所以一律用绝对路径，不能依赖 os.getcwd()
UPLOAD_DIR = os.path.join(main.BASE_DIR, main.UPLOAD_DIR)

mcp = MCPServer("ai-data-platform")


def _table_path(filename: str) -> str:
    """把文件名解析成 uploads 下的真实路径（带路径穿越防御）"""
    path = os.path.join(UPLOAD_DIR, main.safe_filename(filename))
    if not os.path.exists(path):
        raise ValueError(f"表格不存在：{filename}（可先调用 list_tables 查看可用文件）")
    return path


def _load(filename: str):
    return main.load_dataframe(_table_path(filename))


@mcp.tool()
def list_tables() -> str:
    """列出当前已上传的表格文件（CSV / Excel）。"""
    if not os.path.isdir(UPLOAD_DIR):
        return "上传目录不存在。"
    files = sorted(f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith((".csv", ".xlsx")))
    if not files:
        return "当前没有已上传的表格文件。"
    return "已上传的表格：\n" + "\n".join(f"- {f}" for f in files)


@mcp.tool()
def table_overview(filename: str) -> str:
    """查看表格概览：行数、列数、字段名与数据类型。

    Args:
        filename: 表格文件名，例如 hny.csv
    """
    text, _ = main.tool_get_overview(_load(filename))
    return text


@mcp.tool()
def table_stats(filename: str, columns: list[str]) -> str:
    """对指定数值列做统计（计数 / 均值 / 标准差 / 最小 / 四分位 / 最大）。

    Args:
        filename: 表格文件名
        columns: 要统计的列名列表，例如 ["HINCP", "VALP"]
    """
    df = _load(filename)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        return f"这些列不存在：{missing}。可用列（前 30 个）：{df.columns.tolist()[:30]}"
    text, _ = main.tool_get_stats(df, columns)
    return text


@mcp.tool()
def group_aggregate(filename: str, group_col: str, agg_col: str, method: str = "mean") -> str:
    """按某列分组，对另一列做聚合。

    Args:
        filename: 表格文件名
        group_col: 分组列（如地区、类别）
        agg_col: 被聚合的数值列
        method: 聚合方法，可选 mean / sum / count / max / min
    """
    df = _load(filename)
    for c in (group_col, agg_col):
        if c not in df.columns:
            return f"列不存在：{c}。可用列（前 30 个）：{df.columns.tolist()[:30]}"
    text, _ = main.tool_group_agg(df, group_col, agg_col, method)
    return text


@mcp.tool()
def filter_rows(filename: str, column: str, operator: str, value: str) -> str:
    """按条件过滤行，返回命中数量与前 20 行。

    Args:
        filename: 表格文件名
        column: 过滤依据的列名
        operator: 比较运算符，可选 > < >= <= == !=
        value: 比较值（数值列会自动转成数字）
    """
    df = _load(filename)
    if column not in df.columns:
        return f"列不存在：{column}。可用列（前 30 个）：{df.columns.tolist()[:30]}"
    if str(df[column].dtype) != "object" and value.lstrip("-").replace(".", "", 1).isdigit():
        value = float(value)
    text, _ = main.tool_filter(df, column, operator, value)
    return text


@mcp.tool()
def sort_rows(filename: str, column: str, ascending: bool = True) -> str:
    """按某列排序，返回前 20 行。

    Args:
        filename: 表格文件名
        column: 排序列名
        ascending: True 升序，False 降序
    """
    df = _load(filename)
    if column not in df.columns:
        return f"列不存在：{column}。可用列（前 30 个）：{df.columns.tolist()[:30]}"
    text, _ = main.tool_sort(df, column, ascending)
    return text


@mcp.tool()
def search_knowledge_base(query: str) -> str:
    """在本地知识库中检索资料（两阶段：向量宽召回 + LLM 重排）。

    知识库存放的是上传过的 PDF / Word / TXT / 项目分析报告等文档。

    Args:
        query: 自然语言问题
    """
    if main.vectorstore is None:
        return f"知识库不可用：{main._kb_init_error}"
    candidates = main.vectorstore.as_retriever(
        search_kwargs={"k": main.RECALL_K}
    ).invoke(query)
    docs = main.rerank_documents(query, candidates, top_n=main.FINAL_K)
    if not docs:
        return "知识库中没有检索到相关内容。"
    blocks = []
    for i, d in enumerate(docs, 1):
        src = (d.metadata or {}).get("source", "未知来源")
        blocks.append(f"[{i}] 来源：{src}\n{d.page_content}")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    mcp.run()