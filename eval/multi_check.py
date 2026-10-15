"""多智能体协同的并行性检查：跑一次跨模块问题，打印各专家的时间线。

用法：
    venv\\Scripts\\python.exe eval/multi_check.py [表格文件名]
"""
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

QUESTION = "知识库里项目分析报告的主要结论是什么？我上传的表格数据能支持这些结论吗？"


def main_run():
    filename = sys.argv[1] if len(sys.argv) > 1 else "hny.csv"
    print(f"问题：{QUESTION}")
    print(f"表格：{filename}\n")

    t0 = time.perf_counter()
    res = main.multi_analyze(main.MultiRequest(question=QUESTION, filename=filename))
    total = time.perf_counter() - t0

    if not res.get("success"):
        print("执行失败：", res.get("error"))
        return

    findings = res.get("findings", [])
    print(f"总耗时 {total:.1f} 秒    plan = {res.get('plan')}")
    if not findings:
        return

    base = min(f.get("wall_start", 0) for f in findings)
    for f in findings:
        start = f.get("wall_start", 0) - base
        end = f.get("wall_end", base) - base
        bar = " " * int(start) + "█" * max(1, int(end - start))
        print(f"  [{f['agent']:4s}] 自身 {f['elapsed_ms']:>7} ms   "
              f"时间线 {start:6.1f}s -> {end:6.1f}s  |{bar}")

    if len(findings) >= 2:
        overlap = (min(f.get("wall_end", 0) for f in findings)
                   - max(f.get("wall_start", 0) for f in findings))
        verdict = "✅ 并行" if overlap > 5 else "❌ 串行"
        print(f"\n两个专家的重叠时长：{overlap:.1f} 秒  ->  {verdict}")
        if overlap > 5:
            print("   说明 LangGraph 的 fan-out 生效（总耗时 ≈ 最慢的那个专家）")
        else:
            print("   说明两个专家首尾相接 —— 要排查为什么没有真并行")


if __name__ == "__main__":
    main_run()