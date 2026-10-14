"""核心纯函数的单元测试（不调用大模型）。"""
import numpy as np
import pytest

import main


# ---------- 文本切片 ----------
class TestSplitText:
    def test_no_content_loss(self):
        text = "这是一个用于测试切片完整性的长文本。" * 60
        chunks = main.split_text(text, chunk_size=300, chunk_overlap=30)
        assert len(chunks) > 1
        joined = "".join(chunks)
        assert text[:50] in joined      # 开头没丢
        assert text[-50:] in joined     # 结尾没丢

    def test_chunk_size_respected(self):
        chunks = main.split_text("测试句子。" * 300, chunk_size=200, chunk_overlap=20)
        assert all(len(c) <= 200 for c in chunks)

    def test_empty_input(self):
        assert main.split_text("") == []


# ---------- NaN / numpy 归一化（否则前端 JSON.parse 会崩） ----------
class TestToNative:
    def test_nan_and_inf_to_none(self):
        out = main.to_native({"a": float("nan"), "b": float("inf"), "c": float("-inf")})
        assert out == {"a": None, "b": None, "c": None}

    def test_numpy_scalars(self):
        out = main.to_native({"i": np.int64(3), "f": np.float64(1.5), "b": np.bool_(True)})
        assert isinstance(out["i"], int)
        assert isinstance(out["f"], float)
        assert isinstance(out["b"], bool)

    def test_nested_structures(self):
        out = main.to_native({"lst": [np.int64(1), float("nan")]})
        assert out["lst"] == [1, None]


# ---------- 路径穿越防御 ----------
class TestSafeFilename:
    @pytest.mark.parametrize("bad", [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\config",
        "/etc/passwd",
    ])
    def test_strips_directory_components(self, bad):
        out = main.safe_filename(bad)
        assert ".." not in out
        assert "/" not in out and "\\" not in out


# ---------- 重排输出解析（容错性最关键的一段） ----------
class TestParseRanked:
    def test_comma_format(self):
        assert main._parse_ranked("3,7,1", 10) == [3, 7, 1]

    def test_json_format(self):
        assert main._parse_ranked('{"ranked": [2, 0]}', 10) == [2, 0]

    def test_markdown_wrapped_json(self):
        assert main._parse_ranked('```json\n{"ranked": [1]}\n```', 10) == [1]

    def test_out_of_range_and_negative_filtered(self):
        assert main._parse_ranked("1,99,-3", 5) == [1]

    def test_unparsable_returns_empty(self):
        assert main._parse_ranked("我无法判断", 5) == []

    def test_empty_input(self):
        assert main._parse_ranked("", 5) == []


# ---------- 工具函数（纯 pandas） ----------
class TestPandasTools:
    def test_overview(self, df):
        _, info = main.tool_get_overview(df)
        assert info["rows"] == 4
        assert info["columns"] == 3
        assert "城市" in info["column_names"]

    def test_stats(self, df):
        _, res = main.tool_get_stats(df, ["销售额"])
        assert res["销售额"]["mean"] == 250.0
        assert res["销售额"]["count"] == 4.0

    def test_group_agg_mean(self, df):
        _, data = main.tool_group_agg(df, "城市", "销售额", "mean")
        got = {d["城市"]: d["销售额"] for d in data}
        assert got == {"北京": 200.0, "上海": 300.0}

    def test_group_agg_sum(self, df):
        _, data = main.tool_group_agg(df, "城市", "销售额", "sum")
        got = {d["城市"]: d["销售额"] for d in data}
        assert got == {"北京": 400, "上海": 600}

    def test_filter(self, df):
        _, data = main.tool_filter(df, "销售额", ">", 250)
        assert len(data) == 2

    def test_filter_bad_operator(self, df):
        text, data = main.tool_filter(df, "销售额", "~~", 1)
        assert data is None
        assert "不支持的运算符" in text

    def test_sort_desc(self, df):
        _, data = main.tool_sort(df, "销售额", ascending=False)
        assert data[0]["销售额"] == 400


# ---------- 图表推导（确定性，不靠模型猜） ----------
class TestDeriveChart:
    def test_group_agg_uses_real_column_names(self):
        chart = main.derive_chart("group_agg", {"group_col": "城市", "agg_col": "销售额"}, [])
        assert chart == {"type": "bar", "x_field": "城市", "y_field": "销售额"}

    def test_filter_picks_numeric_column_for_y(self):
        data = [{"城市": "北京", "销售额": 200.0}]
        chart = main.derive_chart("filter", {}, data)
        assert chart["x_field"] == "城市"
        assert chart["y_field"] == "销售额"

    def test_overview_has_no_chart(self):
        assert main.derive_chart("get_overview", {}, {"rows": 1}) is None