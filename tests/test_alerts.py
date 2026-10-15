"""告警判定逻辑的单元测试（纯函数，不调用大模型）。"""
import observability as ob


def test_no_alerts_when_no_data():
    ob.reset()
    assert ob.evaluate_alerts({"calls": 0}) == []


def test_slow_call_triggers_warning(monkeypatch):
    monkeypatch.setattr(ob, "ALERT_LATENCY_MS", 1000)
    stats = {"calls": 1, "failed": 0, "max_latency_ms": 5000, "total_tokens": 10}
    alerts = ob.evaluate_alerts(stats)
    assert [a["code"] for a in alerts] == ["slow_call"]
    assert alerts[0]["level"] == "warning"


def test_high_fail_rate_triggers_error(monkeypatch):
    monkeypatch.setattr(ob, "ALERT_LATENCY_MS", 10 ** 9)     # 屏蔽慢调用告警
    monkeypatch.setattr(ob, "ALERT_FAIL_RATE", 0.2)
    stats = {"calls": 10, "failed": 5, "max_latency_ms": 100, "total_tokens": 10}
    alerts = ob.evaluate_alerts(stats)
    assert [a["code"] for a in alerts] == ["high_fail_rate"]
    assert alerts[0]["level"] == "error"


def test_token_budget_triggers_warning(monkeypatch):
    monkeypatch.setattr(ob, "ALERT_LATENCY_MS", 10 ** 9)
    monkeypatch.setattr(ob, "ALERT_FAIL_RATE", 1.0)
    monkeypatch.setattr(ob, "ALERT_TOKENS", 100)
    stats = {"calls": 1, "failed": 0, "max_latency_ms": 1, "total_tokens": 5000}
    assert [a["code"] for a in ob.evaluate_alerts(stats)] == ["token_budget"]


def test_multiple_alerts_coexist(monkeypatch):
    monkeypatch.setattr(ob, "ALERT_LATENCY_MS", 1)
    monkeypatch.setattr(ob, "ALERT_FAIL_RATE", 0.1)
    monkeypatch.setattr(ob, "ALERT_TOKENS", 1)
    stats = {"calls": 10, "failed": 9, "max_latency_ms": 999, "total_tokens": 9999}
    codes = [a["code"] for a in ob.evaluate_alerts(stats)]
    assert set(codes) == {"slow_call", "high_fail_rate", "token_budget"}


def test_snapshot_carries_alerts_and_thresholds(monkeypatch):
    """端到端：写入一条慢调用 → snapshot 里的 alerts 应该出现"""
    monkeypatch.setattr(ob, "ALERT_LATENCY_MS", 100)
    ob.reset()
    try:
        ob.record_llm_call("t", 5000)
        snap = ob.snapshot()
        assert [a["code"] for a in snap["alerts"]] == ["slow_call"]
        assert snap["thresholds"]["max_latency_ms"] == 100
    finally:
        ob.reset()          # 别污染其他测试


def test_empty_snapshot_has_alert_fields():
    ob.reset()
    snap = ob.snapshot()
    assert snap["alerts"] == []
    assert "thresholds" in snap