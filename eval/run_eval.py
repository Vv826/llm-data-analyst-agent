"""检索评测：Hit Rate@1 / Hit Rate@3 / MRR，对比"纯向量检索"与"向量召回+LLM重排"。

用法：
    venv\\Scripts\\python.exe eval/run_eval.py            # 纯向量（不消耗额度）
    venv\\Scripts\\python.exe eval/run_eval.py --rerank   # 加 LLM 重排（消耗额度）
"""
import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

K = 3
RECALL_K = 10
QA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_set.json")


def load_cases():
    with open(QA_PATH, encoding="utf-8") as f:
        return json.load(f)


def make_search_fn(use_rerank):
    if not use_rerank:
        retriever = main.vectorstore.as_retriever(search_kwargs={"k": K})
        return lambda q: retriever.invoke(q)
    wide = main.vectorstore.as_retriever(search_kwargs={"k": RECALL_K})
    return lambda q: main.rerank_documents(q, wide.invoke(q), top_n=K)


def eval_retrieval(cases, search_fn, progress=False):
    rows = []
    for idx, c in enumerate(cases, 1):
        if progress:
            print(f"  [{idx}/{len(cases)}] {c['question'][:30]}", flush=True)
        docs = search_fn(c["question"])
        sources = [(d.metadata or {}).get("source") for d in docs]
        rank = next((i + 1 for i, s in enumerate(sources) if s == c["expected_source"]), None)
        rows.append({"question": c["question"], "expected": c["expected_source"],
                     "got": sources, "rank": rank})
    n = len(cases)
    return {
        "hit1": sum(1 for r in rows if r["rank"] == 1) / n,
        "hitk": sum(1 for r in rows if r["rank"]) / n,
        "mrr": sum(1 / r["rank"] for r in rows if r["rank"]) / n,
        "rows": rows,
    }


def show(title, res):
    print(f"\n{'=' * 58}\n{title}\n{'=' * 58}")
    for r in res["rows"]:
        print(f"  {'✅ @' + str(r['rank']) if r['rank'] else '❌ -- '}  {r['question'][:32]}")
        if not r["rank"]:
            print(f"          期望 {r['expected']}")
    print(f"\n  Hit Rate@1 = {res['hit1']:.1%}   Hit Rate@{K} = {res['hitk']:.1%}   MRR = {res['mrr']:.3f}")


def main_eval():
    p = argparse.ArgumentParser()
    p.add_argument("--rerank", action="store_true", help="启用 LLM 重排（消耗模型额度）")
    args = p.parse_args()

    cases = load_cases()
    print(f"评测集 {len(cases)} 条 | 最终 top-{K} | 知识库 {main.vectorstore._collection.count()} 个片段")
    if args.rerank:
        print(f"模式：向量召回 top-{RECALL_K} → LLM 重排 → top-{K}")
    res = eval_retrieval(cases, make_search_fn(args.rerank), progress=args.rerank)
    show("LLM 重排" if args.rerank else "纯向量检索", res)


if __name__ == "__main__":
    main_eval()