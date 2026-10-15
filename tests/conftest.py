"""pytest 公共配置：把项目根目录加入 sys.path，提供共用 fixture 与条件跳过。"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _kb_ready():
    """本机是否已有可用的知识库（CI 环境没有，会返回 False）"""
    try:
        import main
        return main.vectorstore is not None and main.vectorstore._collection.count() > 0
    except Exception:
        return False


KB_READY = _kb_ready()


def pytest_configure(config):
    config.addinivalue_line("markers", "requires_kb: 需要本地已构建的知识库")


def pytest_collection_modifyitems(config, items):
    """知识库不可用时，自动跳过标了 requires_kb 的用例（而不是让它们失败）。"""
    if KB_READY:
        return
    skip = pytest.mark.skip(reason="需要本地已构建的知识库（CI 环境会跳过）")
    for item in items:
        if "requires_kb" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def df():
    """一个小的示例表格"""
    return pd.DataFrame({
        "城市": ["北京", "上海", "北京", "上海"],
        "销售额": [100, 200, 300, 400],
        "数量": [1, 2, 3, 4],
    })