"""pytest 公共配置：把项目根目录加入 sys.path，并提供共用 fixture。"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture
def df():
    """一个小的示例表格"""
    return pd.DataFrame({
        "城市": ["北京", "上海", "北京", "上海"],
        "销售额": [100, 200, 300, 400],
        "数量": [1, 2, 3, 4],
    })