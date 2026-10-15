"""代码生成安全校验的单元测试（不调用大模型）。"""
import pandas as pd
import pytest

import codegen


@pytest.fixture
def small_df():
    return pd.DataFrame({"城市": ["北京", "上海", "北京"], "销售额": [100, 200, 300]})


SAFE_SNIPPETS = [
    "print(df.head())",
    "print(df.groupby('城市')['销售额'].mean())",
    "result = df['销售额'].sum()\nprint(result)",
    "print(len(df))",
    "print(df['销售额'].max() - df['销售额'].min())",
]

DANGEROUS_SNIPPETS = [
    "import os",
    "import os\nos.system('whoami')",
    "from os import system",
    "open('secret.txt')",
    "__import__('os').system('whoami')",
    "eval('1+1')",
    "exec('a=1')",
    "df.__class__",
    "print(getattr(df, '__class__'))",
    "print((1).__class__.__bases__)",
]


@pytest.mark.parametrize("code", SAFE_SNIPPETS)
def test_safe_code_passes(code):
    ok, issues = codegen.check_code_safety(code)
    assert ok, f"误判为不安全: {code} -> {issues}"


@pytest.mark.parametrize("code", DANGEROUS_SNIPPETS)
def test_dangerous_code_blocked(code):
    ok, issues = codegen.check_code_safety(code)
    assert not ok, f"漏放了危险代码: {code}"
    assert issues


def test_empty_code_rejected():
    assert codegen.check_code_safety("")[0] is False


def test_syntax_error_rejected():
    ok, issues = codegen.check_code_safety("print(")
    assert ok is False
    assert "语法错误" in issues[0]


def test_exec_returns_printed_output(small_df):
    out = codegen.exec_pandas_code("print(df['销售额'].sum())", small_df)
    assert out["ok"] is True
    assert "600" in out["output"]


def test_exec_blocks_dangerous_code(small_df):
    out = codegen.exec_pandas_code("import os", small_df)
    assert out["ok"] is False
    assert "安全检查" in out["error"]


def test_second_layer_blocks_unavailable_builtins(small_df):
    """第二层防御：静态检查放行、但受限命名空间里根本没有 open"""
    out = codegen.exec_pandas_code("print(open)", small_df)
    assert out["ok"] is False
    assert "NameError" in out["error"]


def test_exec_does_not_mutate_input_df(small_df):
    """模型代码不能改坏传入的 DataFrame（执行的是副本）"""
    before = small_df.copy()
    codegen.exec_pandas_code("df.drop(columns=['城市'], inplace=True)", small_df)
    pd.testing.assert_frame_equal(small_df, before)


def test_strip_code_fence():
    assert codegen.strip_code_fence("```python\nprint(1)\n```") == "print(1)"
    assert codegen.strip_code_fence("print(1)") == "print(1)"