"""切片算法对比实验：不同 chunk 策略对检索质量的影响。

对比 4 种策略：
  A 固定 300 字（无重叠）
  B 递归 500 字 + 50 重叠      ← 当前线上方案（基线）
  C 递归 1000 字 + 100 重叠
  D 按段落切（按空行/小标题边界，合并不超过 700 字）

设计要点：
1. 实验用**内存模式**向量库（chromadb.EphemeralClient），完全不落盘
   —— 既不干扰线上向量库（嵌入式 Chroma 是单写入者模型，跨进程写同一个库
   会让运行中的服务句柄失效），也避免 SQLite 打开新目录时的偶发 code 14 错误。
2. 原始文档上传后存的是临时文件（已删除），所以这里**从线上向量库按片段序号重建文本**
   并做重叠消除。4 种策略用同一份重建文本，横向对比依然公平。
3. 全程只做向量检索，**不调用大模型** —— 免费、几秒到一分钟出结果。

用法：
    venv\\Scripts\\python.exe eval/chunk_experiment.py
"""
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

import main

QA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_set.json")
RECALL_K = 10
SEPARATORS = ["\n\n", "\n", "。", "！", "？", " ", ""]


# ---------- 从线上库重建原文 ----------
def join_chunks(parts, probe=80):
    """把重叠切片拼回原文：若下一段开头与已拼内容尾部重复，则去掉重复部分"""
    if not parts:
        return ""
    out = parts[0]
    for p in parts[1:]:
        cut = 0
        for L in range(min(len(out), len(p), probe), 0, -1):
            if out.endswith(p[:L]):
                cut = L
                break
        out += p[cut:]
    return out


def rebuild_documents():
    if main.vectorstore is None:
        raise SystemExit(f"知识库不可用：{main._kb_init_error}")
    data = main.vectorstore.get(include=["documents", "metadatas"])
    by_source = {}
    for cid, doc, meta in zip(data["ids"], data["documents"], data["metadatas"]):
        src = (meta or {}).get("source", "unknown")
        try:
            seq = int(str(cid).rsplit("-", 1)[-1])
        except ValueError:
            seq = 0
        by_source.setdefault(src, []).append((seq, doc))
    return {src: join_chunks([d for _, d in sorted(items)]) for src, items in by_source.items()}


# ---------- 4 种切片策略 ----------
def split_paragraph(text, max_len=700):
    """按空行 / 中文小标题边界切，再合并到不超过 max_len"""
    parts = [
        p.strip() for p in re.split(r"\n\s*\n|\n(?=[一二三四五六七八九十]+、)|(?=图\d+)", text)
        if p.strip()
    ]
    chunks, buf = [], ""
    for p in parts:
        while len(p) > max_len:              # 超长段落硬切
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(p[:max_len])
            p = p[max_len:]
        if len(buf) + len(p) + 1 <= max_len:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def _recursive(size, overlap):
    def _split(text):
        return RecursiveCharacterTextSplitter(
            chunk_size=size, chunk_overlap=overlap,
            length_function=len, separators=SEPARATORS,
        ).split_text(text)
    return _split


STRATEGIES = [
    {"key": "exp_a300", "name": "A 固定 300 字（无重叠）", "split": _recursive(300, 0)},
    {"key": "exp_b500", "name": "B 递归 500+50（当前）", "split": _recursive(500, 50)},
    {"key": "exp_c1000", "name": "C 递归 1000+100", "split": _recursive(1000, 100)},
    {"key": "exp_dpara", "name": "D 按段落切（≤700）", "split": split_paragraph},
]


# ---------- 评测 ----------
def evaluate(strategy, texts, cases, embedder, client):
    vs = Chroma(collection_name=strategy["key"], embedding_function=embedder, client=client)
    chunks, metas, ids = [], [], []
    for src, text in texts.items():
        for i, chunk in enumerate(strategy["split"](text)):
            chunks.append(chunk)
            metas.append({"source": src})
            ids.append(f"{src}-{i}")
    vs.add_texts(texts=chunks, metadatas=metas, ids=ids)

    retriever = vs.as_retriever(search_kwargs={"k": RECALL_K})
    hit1 = hit3 = recall = 0
    mrr = 0.0
    for c in cases:
        sources = [(d.metadata or {}).get("source") for d in retriever.invoke(c["question"])]
        rank = next((i + 1 for i, s in enumerate(sources) if s == c["expected_source"]), None)
        if rank:
            recall += 1
            mrr += 1.0 / rank
            hit1 += (rank == 1)
            hit3 += (rank <= 3)
    n = len(cases)
    total = len(chunks)
    return {
        "chunks": total,
        "avg_len": sum(len(x) for x in chunks) / total if total else 0,
        "hit1": hit1 / n, "hit3": hit3 / n, "recall": recall / n, "mrr": mrr / n,
    }


def main_run():
    texts = rebuild_documents()
    cases = json.load(open(QA_PATH, encoding="utf-8"))
    embedder = main.ChromaONNXEmbeddings()
    client = chromadb.EphemeralClient()          # 内存模式：完全不落盘

    print(f"重建文档 {len(texts)} 份，评测集 {len(cases)} 条，召回 top-{RECALL_K}")
    print("向量库：内存模式（EphemeralClient），不写任何磁盘文件\n")
    for src, text in texts.items():
        print(f"  {src}  →  {len(text)} 字")
    print()

    rows = [(s["name"], evaluate(s, texts, cases, embedder, client)) for s in STRATEGIES]

    header = f"{'策略':<24}{'片段数':>7}{'平均长度':>9}{'Hit@1':>9}{'Hit@3':>9}{'Recall@10':>11}{'MRR':>8}"
    print(header)
    print("-" * len(header))
    for name, r in rows:
        print(f"{name:<24}{r['chunks']:>7}{r['avg_len']:>9.0f}"
              f"{r['hit1']:>9.1%}{r['hit3']:>9.1%}{r['recall']:>11.1%}{r['mrr']:>8.3f}")

    best = max(rows, key=lambda x: (x[1]["hit1"], x[1]["mrr"]))
    print(f"\n按 Hit@1 + MRR 综合最优：{best[0]}")


if __name__ == "__main__":
    main_run()