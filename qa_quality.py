"""Quality-focused HTTP application comparison with a predeclared development/heldout split."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import threading

from qa_app import Engine, MODEL, REVISION, ROOT, check_answer, make_server
from qa_benchmark import request_qa
from qa_evidence import snapshot_sources, source_directory


def is_refusal(answer):
    return answer.strip().rstrip("。.!！ ").strip() == "文档未提供"


def grade(case, answer):
    refusal = is_refusal(answer)
    passed = refusal if case.get("unanswerable") else check_answer(case, answer)["fact_check_pass"] and not refusal
    return dict(fact_check_pass=passed, exact_refusal=refusal,
                refusal_contract_fail=bool(case.get("unanswerable") and not refusal),
                false_refusal=bool(not case.get("unanswerable") and refusal))


def summarize(rows):
    groups = sorted({(r["answer_policy"], r["context"]) for r in rows})
    out = []
    for policy, context in groups:
        selected = [r for r in rows if (r["answer_policy"], r["context"]) == (policy, context)]
        known = [r for r in selected if not r["unanswerable"]]
        unknown = [r for r in selected if r["unanswerable"]]
        out.append(dict(answer_policy=policy, context=context, requests=len(selected),
                        answerable=len(known), answerable_pass=sum(r["fact_check_pass"] for r in known),
                        unanswerable=len(unknown), correct_refusal=sum(r["exact_refusal"] for r in unknown),
                        refusal_contract_failures=sum(r.get("refusal_contract_fail", r.get("unsupported_answer", False)) for r in selected),
                        false_refusals=sum(r["false_refusal"] for r in selected),
                        retrieval_misses=sum(not r["retrieval_contains_gold"] for r in known),
                        token_limit_hits=sum(r["hit_token_limit"] for r in selected),
                        first_text_median_ms=statistics.median(r["client_first_text_ms"] for r in selected),
                        total_median_ms=statistics.median(r["client_total_ms"] for r in selected)))
    return out


def verify(run):
    meta = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    if meta.get("schema") != "qa-quality-v1" or not meta.get("completed_utc"):
        raise ValueError("Not a completed quality run")
    source = source_directory(run, meta["source_sha256"], ROOT)
    suite = json.loads((source / "qa_quality_cases.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in suite["questions"] if c["split"] == meta["split"]}
    rows = [json.loads(line) for line in (run / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = {(case, context, policy) for case in cases for context in ("short", "long") for policy in ("baseline", "strict")}
    actual = {(r["question_id"], r["context"], r["answer_policy"]) for r in rows}
    if actual != expected or len(rows) != len(expected):
        raise ValueError("Missing, extra or duplicate request")
    for row in rows:
        if row["question"] != cases[row["question_id"]]["question"]:
            raise ValueError("Question mismatch")
        # The development archive used an overly broad legacy field name.
        if any(row.get(k, row.get("unsupported_answer") if k == "refusal_contract_fail" else None) != v
               for k, v in grade(cases[row["question_id"]], row["answer"]).items()):
            raise ValueError("Quality grade mismatch")
        if not row["client_total_ms"] >= row["client_first_text_ms"] > 0:
            raise ValueError("Invalid client timings")
        if row["output_tokens"] != len(row["output_token_ids"]):
            raise ValueError("Output token count mismatch")
    for case in cases:
        for context in ("short", "long"):
            pair = [r for r in rows if r["question_id"] == case and r["context"] == context]
            if pair[0]["retrieved_ids"] != pair[1]["retrieved_ids"]:
                raise ValueError("Policies received different retrieved documents")
    review_path = run / "answer_review.json"
    if review_path.exists():
        review = json.loads(review_path.read_text(encoding="utf-8"))["decisions"]
        keys = {(r["question_id"], r["context"], r["answer_policy"]): r for r in review}
        if len(review) != len(expected) or set(keys) != expected:
            raise ValueError("Incomplete or duplicate answer review")
        for row in rows:
            decision = keys[(row["question_id"], row["context"], row["answer_policy"])]
            if decision["answer_sha256"] != hashlib.sha256(row["answer"].encode()).hexdigest():
                raise ValueError("Review does not match saved answer")
    return rows


def main():
    from bench_utils import environment, write_csv, write_json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("dev", "heldout"), default="dev")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        print(f"Verified {len(verify(args.output))} requests and archived sources")
        return
    if args.output.exists():
        parser.error("output must not exist; historical evidence is never overwritten")
    suite = json.loads((ROOT / "qa_quality_cases.json").read_text(encoding="utf-8"))
    cases = [c for c in suite["questions"] if c["split"] == args.split]
    if len({c["id"] for c in suite["questions"]}) != len(suite["questions"]):
        raise ValueError("Duplicate question ID")
    files = ("qa_app.py", "qa_benchmark.py", "qa_quality.py", "qa_quality_cases.json", "qa_fixtures.json",
             "qa_evidence.py", "qa_ui.html", "bench_utils.py")
    args.output.mkdir(parents=True)
    meta = dict(schema="qa-quality-v1", started_utc=datetime.now(timezone.utc).isoformat(),
                split=args.split, model=MODEL, revision=REVISION, variant="cuda_eager_bf16",
                source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
                protocol=suite["protocol"], unique_questions=len(cases),
                grading="refusal_contract_fail means not the exact required refusal, NOT necessarily hallucination; benign paraphrases also fail this strict formatting contract. Inspect raw text and review separately for factual support.",
                timing="Sequential loopback HTTP, warm model, no answer cache; includes prompt/retrieval/generation. One observation per case/policy/context, natural output lengths; descriptive only, not kernel speedup or robust tail latency.")
    snapshot_sources(args.output, meta["source_sha256"], ROOT)
    write_json(args.output / "metadata.json", meta)
    engine = Engine("cuda_eager_bf16", local_files_only=True, threads=4)
    meta["environment"] = environment()
    meta["load_seconds"] = engine.load_seconds
    write_json(args.output / "metadata.json", meta)
    server = make_server(engine)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    rows = []
    try:
        for policy in ("baseline", "strict"):
            request_qa(url, dict(question="青禾云专业版每月多少钱？", answer_policy=policy, max_new_tokens=16))
        jobs = [(case, context) for case in cases for context in ("short", "long")]
        random.Random(20261002).shuffle(jobs)
        for index, (case, context) in enumerate(jobs):
            policies = ("baseline", "strict") if index % 2 == 0 else ("strict", "baseline")
            for policy in policies:
                row = request_qa(url, dict(question=case["question"], context=context, answer_policy=policy, max_new_tokens=96))
                row.pop("event")
                row.update(question_id=case["id"], question=case["question"], context=context, split=args.split,
                           category=case["category"], unanswerable=bool(case.get("unanswerable")),
                           retrieval_contains_gold=set(case["documents"]).issubset(row["retrieved_ids"]))
                row.update(grade(case, row["answer"]))
                rows.append(row)
                with (args.output / "requests.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                print(f"{policy} {context} {case['id']}: pass={row['fact_check_pass']} {row['answer']}", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        engine.close()
    meta["completed_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(args.output / "metadata.json", meta)
    verify(args.output)
    write_csv(args.output / "summary.csv", summarize(rows))


if __name__ == "__main__":
    main()
