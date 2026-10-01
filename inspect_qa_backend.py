"""Record actual attention dispatcher operations on the persistent QA worker."""
import argparse
import json
from pathlib import Path

from qa_app import Engine, validate_request


def main():
    import torch
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Refusing to overwrite previous evidence")
    records = []
    engine = Engine("cuda_eager_fp16", local_files_only=True)
    precision_check = dict(variant="cuda_eager_fp16")
    try:
        request = validate_request(dict(question=engine.kb.questions[0]["question"], max_new_tokens=4))
        events = []
        try:
            engine.answer(request, events.append)
            precision_check.update(status="completed", answer=events[-1]["answer"])
        except FloatingPointError as exc:
            precision_check.update(status="rejected_invalid_logits", reason=str(exc))
    finally:
        engine.close()
    print(precision_check, flush=True)
    for variant in ("cuda_eager_bf16", "cuda_sdpa_bf16", "cuda_cudnn_bf16"):
        engine = Engine(variant, local_files_only=True)
        request = validate_request(dict(question=engine.kb.questions[0]["question"], context="long", max_new_tokens=4))
        try:
            engine.answer(request, lambda event: None)
            generate = engine.worker.generate
            def profiled(request, emit, arrival):
                with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as trace:
                    generate(request, emit, arrival)
                records.append(dict(variant=variant, question_id="price", context="long", max_new_tokens=4,
                                    attention_ops={e.key: e.count for e in trace.key_averages()
                                                   if "scaled_dot_product" in e.key}))
            engine.worker.generate = profiled
            engine.answer(request, lambda event: None)
        finally:
            engine.close()
        print(records[-1], flush=True)
    args.output.write_text(json.dumps(dict(
        note="CPU dispatcher operator names recorded inside the persistent inference worker. Includes prefill and 3 cached decode steps. Profiling is separate from benchmark timings; no latency claim is made from this trace.",
        torch=str(torch.__version__), precision_check=precision_check, records=records), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
