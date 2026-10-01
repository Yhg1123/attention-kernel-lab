"""Revalidate complete QA evidence and produce an auditable application report."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from qa_app import KnowledgeBase
from qa_benchmark import paired_comparisons, summarize


def validate(run):
    meta = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    if not meta.get("completed_utc"):
        raise ValueError("Refusing incomplete run without completed_utc")
    rows = [json.loads(line) for line in (run / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    args = meta["arguments"]
    cases = KnowledgeBase().questions
    if args.get("question_ids"):
        cases = [c for c in cases if c["id"] in args["question_ids"]]
    expected = {(v, t, c["id"], context, "natural") for v in args["variants"]
                for t in range(args["trials"]) for c in cases for context in ("short", "long")}
    expected |= {(v, t, cases[0]["id"], context, "fixed") for v in args["variants"]
                 for t in range(args["trials"]) for context in ("short", "long")}
    observed = [(r["variant"], r["trial"], r["question_id"], r["context"], r["mode"]) for r in rows]
    if len(observed) != len(set(observed)) or set(observed) != expected or len(rows) != meta["requests"]:
        raise ValueError("Duplicate, missing or unexpected request")
    for row in rows:
        for key in ("client_total_ms", "client_first_text_ms", "server_first_token_ms", "generation_ms"):
            if not isinstance(row[key], (int, float)) or not math.isfinite(row[key]) or row[key] <= 0:
                raise ValueError(f"Invalid timing: {key}")
        if row["client_first_text_ms"] > row["client_total_ms"]:
            raise ValueError("First text arrived after completion")
        if row["output_tokens"] != len(row["output_token_ids"]):
            raise ValueError("Token count mismatch")
        if row["mode"] == "fixed" and row["output_tokens"] != args["fixed_tokens"]:
            raise ValueError("Fixed token control mismatch")
    for name, digest in meta["source_sha256"].items():
        path = Path(__file__).parent / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Current source differs from measured source: {name}")
    if hashlib.sha256(KnowledgeBase().raw).hexdigest() != meta["fixture_sha256"]:
        raise ValueError("Fixture differs from measured fixture")
    return meta, rows


def main():
    from bench_utils import write_csv, write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    meta, rows = validate(args.run)
    summaries = summarize(rows)
    pairs = paired_comparisons(rows)
    write_csv(args.run / "summary.csv", summaries)
    write_csv(args.run / "paired_comparisons.csv", pairs)
    pair_summary = []
    for key in sorted({(r["baseline"], r["candidate"], r["context"], r["mode"]) for r in pairs}):
        subset = [r for r in pairs if (r["baseline"], r["candidate"], r["context"], r["mode"]) == key]
        pair_summary.append(dict(zip(("baseline", "candidate", "context", "mode"), key), pairs=len(subset),
                                 median_paired_total_speedup=statistics.median(r["total_speedup"] for r in subset),
                                 min_paired_total_speedup=min(r["total_speedup"] for r in subset),
                                 max_paired_total_speedup=max(r["total_speedup"] for r in subset),
                                 identical_outputs=sum(r["same_output_tokens"] for r in subset)))
    write_csv(args.run / "paired_summary.csv", pair_summary)
    grouped = defaultdict(list)
    for row in rows:
        if row["mode"] == "natural":
            grouped[(row["variant"], row["context"], row["question_id"], row["answer"])].append(row)
    answers = ["# 自然回答原文\n", "同一配置、资料长度、问题、回答文本的重复结果合并展示。关键词检查不是人工语义评分。\n"]
    for (variant, context, question, answer), subset in sorted(grouped.items()):
        answers += [f"## {variant} / {context} / {question}\n",
                    f"问题：{subset[0]['question']}\n",
                    f"轮次：{', '.join(str(r['trial']) for r in subset)}；关键词检查：{all(r['fact_check_pass'] for r in subset)}；达到上限：{any(r['hit_token_limit'] for r in subset)}。\n",
                    "\n".join("    " + line for line in answer.splitlines()) + "\n"]
    (args.run / "answers.md").write_text("\n".join(answers), encoding="utf-8")
    report = ["# 本机中文文档问答：完整 HTTP 应用测试\n",
              f"固定推理线程；Qwen2.5-1.5B-Instruct；CPU {meta['arguments']['threads']} 线程；{meta['arguments']['trials']} 轮；{len(rows)} 次正式请求。模型加载和预热不计入请求延迟。\n",
              "## 自然回答：用户等待时间\n",
              "下表为各问题混合后的请求中位数；同一栏使用相同题目。输出长度可能不同，需结合固定长度对照。短资料为检索到的两篇，长资料为全部六篇。\n",
              "| 配置 | 资料 | 首段文字 ms | 总耗时 ms | 总耗时 P95 ms | 输入 token | 输出 token | 每题三轮均通过关键词检查 |",
              "|---|---|---:|---:|---:|---|---|---|"]
    for r in summaries:
        if r["mode"] == "natural":
            report.append(f"| {r['variant']} | {r['context']} | {r['client_first_text_ms_median']:.1f} | {r['client_total_ms_median']:.1f} | {r['client_total_ms_p95']:.1f} | {r['input_tokens_min']}–{r['input_tokens_max']} | {r['output_tokens_min']}–{r['output_tokens_max']} | {r['fact_check_all_trials_pass_questions']}/{r['unique_questions']} |")
    report += ["\n## 固定输出长度控制\n",
               f"每次强制 {meta['arguments']['fixed_tokens']} token，只有价格题，每种资料长度 {meta['arguments']['trials']} 次。样本少，P95 接近最大值；生成内容不纳入答案质量评估。\n",
               "| 配置 | 资料 | 首段文字 ms | 完成 ms | 完成 P95 ms |",
               "|---|---|---:|---:|---:|"]
    for r in summaries:
        if r["mode"] == "fixed":
            report.append(f"| {r['variant']} | {r['context']} | {r['client_first_text_ms_median']:.1f} | {r['client_total_ms_median']:.1f} | {r['client_total_ms_p95']:.1f} |")
    report += ["\n## 显存\n", "PyTorch allocator 峰值，不能等同于整机显存。下表为自然回答中最坏一次；CPU 未测显存，留空。\n",
               "| 配置 | 资料 | 含模型峰值 MiB | 请求峰值增量 MiB |", "|---|---|---:|---:|"]
    for r in summaries:
        if r["mode"] == "natural" and r["peak_allocated_mib_max"] is not None:
            report.append(f"| {r['variant']} | {r['context']} | {r['peak_allocated_mib_max']:.2f} | {r['peak_extra_mib_max']:.2f} |")
    report += ["\n## 原始证据与复现\n",
               "- [逐次请求](requests.jsonl)：完整回答、token ID、计时、显存与关键词检查。",
               "- [回答原文](answers.md)：按配置与问题整理，方便人工核对。",
               "- [汇总](summary.csv)、[配对比较](paired_comparisons.csv)、[配对汇总](paired_summary.csv)。",
               "- [环境、模型版本、执行顺序、加载耗时与源码哈希](metadata.json)。",
               "- [应用运行方式、计时边界与验收局限](../../QA_TESTING.md)。",
               "- [预检失败方案](../2026-10-01-qa-preflight/README.md)：FP16 eager 与三种动态 INT8 方案。\n",
               "```powershell\npython qa_benchmark.py --output results/my-qa-run --trials 3 --local-files-only\npython summarize_qa.py --run results/my-qa-run\n```\n",
               "本次只有六道独立题，短长资料各测一次并重复三轮；不能称为 144 道独立题。结果不含公网延迟或浏览器绘制，也没有验证多人并发或生产 SLA。自然回答质量需结合原文人工核对；错误回答不能因为较快而算作可部署优化。",
               "\n测量在 Windows 笔记本桌面环境进行，未锁定 GPU 时钟或隔离全部后台负载。三轮数据属于本机描述统计，不是严格的跨硬件排名或置信区间。CPU FP32 与 GPU BF16 的差别同时包含设备和精度变化；不能把它们的总速度差归因于注意力优化。"]
    if (args.run / "FINDINGS.md").exists():
        report.insert(2, "[先看面向实际使用的结论](FINDINGS.md) · [回答原文复核](answer_review.json) · [实际后端检查](backend_inspection.json)\n")
    (args.run / "README.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    write_json(args.run / "verification.json", dict(requests=len(rows), paired_comparisons=len(pairs),
               complete_unique_requests=True, finite_timings=True, prompt_pairs_equal=True,
               fixed_token_counts_equal=True, current_source_hashes_match=True,
               analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(f"Verified {len(rows)} requests; wrote report and answer inventory", flush=True)


if __name__ == "__main__":
    main()
