"""Benchmark the actual local HTTP document-QA application, including streamed text."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import statistics
import threading
import time
import urllib.request

from qa_app import Engine, KnowledgeBase, MODEL, REVISION, ROOT, VARIANTS, DEFAULT_VARIANTS, check_answer, make_server
from qa_evidence import snapshot_sources


def request_qa(url, payload, timeout=300):
    request = urllib.request.Request(url + "/ask", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    first = None
    parts, done = [], None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for line in response:
            event = json.loads(line)
            if event["event"] == "error":
                raise RuntimeError(event["message"])
            if event["event"] == "text":
                if event["text"] and first is None:
                    first = (time.perf_counter() - start) * 1000
                parts.append(event["text"])
            if event["event"] == "done":
                total = (time.perf_counter() - start) * 1000
                done = event
    if done is None or done["answer"] != "".join(parts):
        raise RuntimeError("Incomplete or inconsistent HTTP stream")
    return dict(done, client_first_text_ms=first, client_total_ms=total)


def p95(values):
    import math
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)]


def summarize(rows):
    """Descriptive pooled request statistics; quality counted separately by unique case."""
    result = []
    groups = sorted({(r["variant"], r["context"], r["mode"]) for r in rows})
    for variant, context, mode in groups:
        subset = [r for r in rows if (r["variant"], r["context"], r["mode"]) == (variant, context, mode)]
        row = dict(variant=variant, context=context, mode=mode, requests=len(subset),
                   unique_questions=len({r["question_id"] for r in subset}),
                   output_tokens_min=min(r["output_tokens"] for r in subset),
                   output_tokens_max=max(r["output_tokens"] for r in subset),
                   input_tokens_min=min(r["input_tokens"] for r in subset),
                   input_tokens_max=max(r["input_tokens"] for r in subset),
                   token_limit_hits=sum(r["hit_token_limit"] for r in subset))
        for metric in ("client_first_text_ms", "client_total_ms", "server_first_token_ms", "retrieval_ms",
                       "tokenize_transfer_ms", "generation_ms", "queue_ms"):
            values = [r[metric] for r in subset if r[metric] is not None]
            row[metric + "_median"] = statistics.median(values) if values else None
            row[metric + "_p95"] = p95(values) if values else None
        for metric in ("peak_allocated_mib", "peak_extra_mib"):
            values = [r[metric] for r in subset if r[metric] is not None]
            row[metric + "_max"] = max(values) if values else None
        if mode == "natural":
            row["fact_check_pass_requests"] = sum(r["fact_check_pass"] for r in subset)
            row["fact_check_all_trials_pass_questions"] = sum(
                all(r["fact_check_pass"] for r in subset if r["question_id"] == key)
                for key in {r["question_id"] for r in subset})
        result.append(row)
    return result


def paired_comparisons(rows):
    result = []
    for baseline, candidate in (("cuda_eager_fp16", "cuda_sdpa_fp16"), ("cuda_eager_bf16", "cuda_sdpa_bf16"),
                                ("cuda_eager_bf16", "cuda_cudnn_bf16"), ("cuda_sdpa_bf16", "cuda_cudnn_bf16"),
                                ("cpu_eager_fp32", "cpu_eager_int8"), ("cpu_eager_fp32", "cpu_eager_int8_mlp"),
                                ("cpu_eager_fp32", "cpu_eager_int8_mlp_per_channel")):
        index = {(r["trial"], r["question_id"], r["context"], r["mode"]): r for r in rows if r["variant"] == baseline}
        for row in rows:
            key = row["trial"], row["question_id"], row["context"], row["mode"]
            if row["variant"] != candidate or key not in index:
                continue
            base = index[key]
            if base["input_sha256"] != row["input_sha256"]:
                raise RuntimeError("Comparison has unequal prompt token IDs")
            result.append(dict(baseline=baseline, candidate=candidate, trial=row["trial"],
                               question_id=row["question_id"], context=row["context"], mode=row["mode"],
                               total_speedup=base["client_total_ms"] / row["client_total_ms"],
                               first_text_speedup=base["client_first_text_ms"] / row["client_first_text_ms"]
                               if base["client_first_text_ms"] and row["client_first_text_ms"] else None,
                               same_output_tokens=base["output_token_ids"] == row["output_token_ids"],
                               baseline_output_tokens=base["output_tokens"], candidate_output_tokens=row["output_tokens"],
                               baseline_fact_pass=base.get("fact_check_pass"), candidate_fact_pass=row.get("fact_check_pass")))
    return result


def main():
    import torch
    from bench_utils import environment, write_csv, write_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(DEFAULT_VARIANTS))
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--fixed-tokens", type=int, default=64)
    parser.add_argument("--question-ids", nargs="+")
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args()
    if min(args.trials, args.threads, args.max_new_tokens, args.fixed_tokens) < 1 or max(args.max_new_tokens, args.fixed_tokens) > 256:
        parser.error("positive trials/threads; token limits 1..256 required")
    if len(set(args.variants)) != len(args.variants):
        parser.error("variants must be unique")
    kb = KnowledgeBase()
    cases = [c for c in kb.questions if not args.question_ids or c["id"] in args.question_ids]
    if not cases or (args.question_ids and set(args.question_ids) != {c["id"] for c in cases}):
        parser.error("unknown or empty question selection")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("output directory must be empty; previous evidence is never overwritten")
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(args.threads)
    torch.backends.cuda.matmul.allow_tf32 = False
    jobs = [(case, context, "natural") for case in cases for context in ("short", "long")]
    jobs += [(cases[0], context, "fixed") for context in ("short", "long")]
    orders = []
    for trial in range(args.trials):
        order = list(args.variants)
        random.Random(2026 + trial).shuffle(order)
        orders.append(order)
    meta = dict(schema_version="qa-http-v1", started_utc=datetime.now(timezone.utc).isoformat(),
                model=MODEL, model_revision=REVISION, model_license="Apache-2.0",
                fixture_sha256=hashlib.sha256(kb.raw).hexdigest(), environment=environment(),
                arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                variant_order_by_trial=orders, generation="greedy; KV cache; batch=1; fresh conversation; no answer cache",
                comparison="GPU eager vs stock Transformers SDPA at identical dtype; FP32 CPU eager vs dynamic INT8. _mlp quantizes only named MLP Linear layers; plain int8 quantizes every Linear. Embeddings/norm remain FP32.",
                timing="Loopback HTTP POST through retrieval, tokenization, transfers, generation, decoding and streamed response. Client TTFT is first nonempty text chunk, not GPU first token. Completion is receipt of done event. Browser paint, Internet latency, model loading and warmup excluded.",
                quality="Six authored fixture questions, substring fact assertions plus saved answers for human inspection. Repeats are not independent quality examples. Fixed-length cases are only speed controls, not scored for quality.",
                scope="One sequential user; persistent inference worker across HTTP requests; no production load/concurrency claim. Short=top 2 BM25 docs; long=all 6 docs with top 2 first. Same full documents across variants, no truncation. Every generated step checks invalid logits, including synchronization overhead in both baselines and candidates.",
                packages={d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
                source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               [ROOT / name for name in ("qa_app.py", "qa_benchmark.py", "qa_ui.html", "qa_fixtures.json", "qa_evidence.py", "bench_utils.py")]},
                loads=[])
    snapshot_sources(args.output, meta["source_sha256"], ROOT)
    write_json(args.output / "metadata.json", meta)
    rows = []
    for trial, variants in enumerate(orders):
        for variant in variants:
            print(f"Loading trial={trial} {variant}", flush=True)
            engine = Engine(variant, threads=args.threads, local_files_only=args.local_files_only)
            meta["loads"].append(dict(trial=trial, variant=variant, seconds=engine.load_seconds,
                                      quantization_engine=torch.backends.quantized.engine))
            write_json(args.output / "metadata.json", meta)
            server = make_server(engine)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            try:
                for context in ("short", "long"):
                    request_qa(url, dict(question=cases[0]["question"], context=context, max_new_tokens=16, fixed_tokens=True))
                ordered_jobs = list(jobs)
                random.Random(4200 + trial).shuffle(ordered_jobs)
                for case, context, mode in ordered_jobs:
                    payload = dict(question=case["question"], context=context,
                                   max_new_tokens=args.fixed_tokens if mode == "fixed" else args.max_new_tokens,
                                   fixed_tokens=mode == "fixed")
                    row = request_qa(url, payload)
                    row.pop("event")
                    row.update(trial=trial, question_id=case["id"], question=case["question"], context=context, mode=mode)
                    if mode == "natural":
                        row.update(check_answer(case, row["answer"]))
                        row["retrieval_contains_gold"] = set(case["documents"]).issubset(row["retrieved_ids"])
                    if mode == "fixed" and row["output_tokens"] != args.fixed_tokens:
                        raise RuntimeError("Fixed-length generation did not produce the requested token count")
                    rows.append(row)
                    with (args.output / "requests.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                    print(f"trial={trial} {variant} {context} {case['id']} {mode}: "
                          f"first={row['client_first_text_ms']:.1f}ms total={row['client_total_ms']:.1f}ms "
                          f"tokens={row['output_tokens']} facts={row.get('fact_check_pass', 'n/a')}", flush=True)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                engine.close()
                del engine, server
    if len(rows) != args.trials * len(args.variants) * len(jobs):
        raise RuntimeError("Incomplete run")
    write_csv(args.output / "summary.csv", summarize(rows))
    write_csv(args.output / "paired_comparisons.csv", paired_comparisons(rows))
    meta["completed_utc"] = datetime.now(timezone.utc).isoformat()
    meta["requests"] = len(rows)
    write_json(args.output / "metadata.json", meta)
    print(f"Complete: {len(rows)} measured requests in {args.output}", flush=True)


if __name__ == "__main__":
    main()
