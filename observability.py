"""轻量可观测性（LLMOps 的监控部分）。

不引入 Prometheus / OpenTelemetry 等外部依赖，用内存环形缓冲聚合出
「调用次数 / token / 延迟（均值、P95）/ 估算成本」，通过 /metrics 暴露。

覆盖两类模型调用：
1. LangChain 的 ChatOpenAI —— 通过 MetricsCallback 挂在 config["callbacks"] 上
2. 裸 requests 调用（重排器）—— 直接调 record_llm_call
"""
import statistics
import threading
import time
from collections import deque

from langchain_core.callbacks import BaseCallbackHandler

# 单价（元 / 百万 token）—— 按你实际的方舟计费改这里
PRICE_INPUT_PER_M = 0.8
PRICE_OUTPUT_PER_M = 2.0

MAX_RECORDS = 300
_records = deque(maxlen=MAX_RECORDS)
_lock = threading.Lock()  # 多个请求线程会并发写入


def _cost(input_tokens, output_tokens):
    return (input_tokens * PRICE_INPUT_PER_M + output_tokens * PRICE_OUTPUT_PER_M) / 1_000_000


def record_llm_call(label, latency_ms, input_tokens=0, output_tokens=0, ok=True, error=""):
    """记录一次模型调用（线程安全）"""
    rec = {
        "label": label,
        "latency_ms": round(latency_ms, 1),
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "cost": round(_cost(input_tokens or 0, output_tokens or 0), 6),
        "ok": ok,
        "error": error[:150],
        "ts": time.time(),
    }
    with _lock:
        _records.append(rec)
    return rec


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def snapshot():
    """聚合指标（供 /metrics 使用）"""
    with _lock:
        recs = list(_records)
    if not recs:
        return {"calls": 0, "total_tokens": 0, "total_cost": 0, "by_label": {}, "recent": []}

    lat = [r["latency_ms"] for r in recs]
    by_label = {}
    for r in recs:
        b = by_label.setdefault(r["label"], {"calls": 0, "tokens": 0, "cost": 0.0, "latency_ms": 0.0})
        b["calls"] += 1
        b["tokens"] += r["input_tokens"] + r["output_tokens"]
        b["cost"] = round(b["cost"] + r["cost"], 6)
        b["latency_ms"] = round(b["latency_ms"] + r["latency_ms"], 1)

    return {
        "calls": len(recs),
        "failed": sum(1 for r in recs if not r["ok"]),
        "total_input_tokens": sum(r["input_tokens"] for r in recs),
        "total_output_tokens": sum(r["output_tokens"] for r in recs),
        "total_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in recs),
        "total_cost": round(sum(r["cost"] for r in recs), 4),
        "avg_latency_ms": round(statistics.fmean(lat), 1),
        "p95_latency_ms": round(percentile(lat, 95), 1),
        "max_latency_ms": round(max(lat), 1),
        "by_label": by_label,
        "recent": recs[-8:],
    }


def reset():
    with _lock:
        _records.clear()


class MetricsCallback(BaseCallbackHandler):
    """挂在 LangChain 调用链上，捕获每一次底层模型调用的耗时与 token。

    用「开始时间列表」而不是 run_id 做配对：同一次 Agent 运行里的模型调用是
    顺序的，FIFO 配对足够，也避免了 run_id 不可靠的问题。
    """

    def __init__(self, label="llm"):
        self.label = label
        self._starts = []

    def on_llm_start(self, *args, **kwargs):
        self._starts.append(time.perf_counter())

    def on_llm_end(self, response, **kwargs):
        t0 = self._starts.pop(0) if self._starts else time.perf_counter()
        usage = (getattr(response, "llm_output", None) or {}).get("token_usage") or {}
        record_llm_call(self.label, (time.perf_counter() - t0) * 1000,
                        usage.get("prompt_tokens"), usage.get("completion_tokens"))

    def on_llm_error(self, error, **kwargs):
        t0 = self._starts.pop(0) if self._starts else time.perf_counter()
        record_llm_call(self.label, (time.perf_counter() - t0) * 1000, ok=False, error=str(error))