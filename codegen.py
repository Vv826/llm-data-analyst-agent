"""AI 代码生成 + 受限执行（安全优先）。

设计原则：**不自动执行模型生成的代码**。
    1. 生成：模型只负责产出 pandas 代码
    2. 校验：AST 静态检查（禁 import / 禁下划线属性 / 禁危险内置函数）
    3. 执行：清空 __builtins__，只注入白名单内置函数与 pd/df 副本
    4. 复核：接口层会再次校验，不信任前端传来的代码

为什么不直接 exec：模型生成的代码等价于"陌生人写的代码"。
靠提示词要求模型"别写危险代码"是不可靠的，安全边界必须由代码保证。
"""
import ast
import builtins
import contextlib
import io

import pandas as pd

# 允许注入的内置函数白名单
# 故意不含 open / __import__ / eval / exec / getattr / globals / vars
SAFE_BUILTINS = {
    "len", "print", "sum", "min", "max", "abs", "round", "sorted",
    "list", "dict", "set", "tuple", "float", "int", "str", "bool",
    "enumerate", "zip", "range", "any", "all", "reversed",
}

# 显式禁止调用的名字
FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "open", "input", "__import__",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "breakpoint", "memoryview", "exit", "quit", "help",
}

MAX_OUTPUT_CHARS = 4000


def check_code_safety(code):
    """AST 静态检查。返回 (是否安全, 问题列表)。"""
    if not code or not code.strip():
        return False, ["代码为空"]

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"语法错误：{e.msg}（第 {e.lineno} 行）"]

    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            issues.append(f"禁止导入模块（第 {node.lineno} 行）")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            issues.append(f"禁止访问下划线属性 `{node.attr}`（第 {node.lineno} 行）")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            issues.append(f"禁止访问 `{node.id}`（第 {node.lineno} 行）")
        elif (isinstance(node, ast.Call)
              and isinstance(node.func, ast.Name)
              and node.func.id in FORBIDDEN_CALLS):
            issues.append(f"禁止调用 `{node.func.id}()`（第 {node.lineno} 行）")

    seen, uniq = set(), []
    for x in issues:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return (not uniq), uniq


def strip_code_fence(text):
    """模型常把代码包在 ```python ... ``` 里，剥掉围栏"""
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines)
    return t.strip()


def _safe_builtins():
    return {k: getattr(builtins, k) for k in SAFE_BUILTINS}


def exec_pandas_code(code, df):
    """在受限命名空间里执行 pandas 代码，捕获标准输出。

    返回：{"ok": True, "output": "..."} 或 {"ok": False, "error": "..."}
    """
    ok, issues = check_code_safety(code)
    if not ok:
        return {"ok": False, "error": "代码未通过安全检查：" + "；".join(issues)}

    namespace = {
        "pd": pd,
        "df": df.copy(),                  # 执行副本，避免模型代码改坏缓存里的 DataFrame
        "__builtins__": _safe_builtins(),  # 第二层防御：即使静态检查漏了也调不到危险函数
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<ai-generated>", "exec"), namespace)
    except Exception as e:
        return {"ok": False,
                "error": f"{type(e).__name__}: {e}",
                "output": buf.getvalue()[:MAX_OUTPUT_CHARS]}

    return {"ok": True, "output": buf.getvalue()[:MAX_OUTPUT_CHARS]}