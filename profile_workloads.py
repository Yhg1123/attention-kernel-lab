"""Profile causal prefill and one-token cached decode on exact, repeated workloads."""
from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path
import random
import warnings

import torch
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel

from bench_utils import error_metrics, finish_run, measure, record, start_run

GROUPS = ["device", "mode", "batch", "heads", "length", "head_dim", "dtype"]
BACKENDS = {"sdpa_math": SDPBackend.MATH, "sdpa_flash": SDPBackend.FLASH_ATTENTION,
            "sdpa_efficient": SDPBackend.EFFICIENT_ATTENTION, "sdpa_cudnn": SDPBackend.CUDNN_ATTENTION}
DTYPES = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}


def attention(backend, q, k, v, mode):
    """Decode Q is the newest token; K/V contain past AND current token, without padding."""
    if mode not in ("prefill", "decode"):
        raise ValueError("mode must be prefill or decode")
    if q.ndim != 4 or k.shape != v.shape or q.shape[:2] != k.shape[:2] or q.shape[-1] != k.shape[-1]:
        raise ValueError("expected compatible [batch, heads, tokens, head_dim] Q/K/V")
    if (mode == "prefill" and q.shape[-2] != k.shape[-2]) or (mode == "decode" and q.shape[-2] != 1):
        raise ValueError("prefill needs equal Q/K lengths; decode needs exactly one query token")
    causal = mode == "prefill"
    if backend == "eager":
        scores = (q @ k.transpose(-2, -1)) / math.sqrt(q.shape[-1])
        if causal:
            mask = torch.ones(q.shape[-2], k.shape[-2], dtype=torch.bool, device=q.device).tril()
            scores = scores.masked_fill(~mask, float("-inf"))
        return scores.softmax(dim=-1) @ v
    # For one-token decode all existing K/V positions are visible. is_causal=True
    # would apply an upper-left mask and incorrectly allow only the first key.
    if backend == "sdpa_auto":
        return F.scaled_dot_product_attention(q, k, v, is_causal=causal)
    with sdpa_kernel(BACKENDS[backend]):
        return F.scaled_dot_product_attention(q, k, v, is_causal=causal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/profiles"))
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--lengths", type=int, nargs="+", default=[256, 1024, 2048])
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--head-dim", type=int, default=64)
    parser.add_argument("--modes", nargs="+", choices=["prefill", "decode"], default=["prefill", "decode"])
    parser.add_argument("--dtypes", nargs="+", choices=list(DTYPES), default=["float32", "float16"])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if min(args.lengths + args.batch_sizes + [args.heads, args.head_dim, args.trials, args.threads]) < 1 or args.samples < 2 or args.warmup < 0:
        parser.error("sizes, trials and threads must be positive; samples >= 2; warmup >= 0")
    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA is unavailable")
    torch.set_num_threads(args.threads)
    torch.backends.cuda.matmul.allow_tf32 = False
    device = torch.device(args.device)
    metadata = start_run(args.output, args, GROUPS, "backend",
                         "GPU-resident attention only. Prefill causal square; decode one query over past+current KV with no future/padding. No projections, cache update or full model included.")
    rows = []
    backends = ["eager", "sdpa_math", "sdpa_auto"] + (list(BACKENDS)[1:] if args.device == "cuda" else [])
    for trial in range(args.trials):
        torch.manual_seed(args.seed + trial)
        rng = random.Random(args.seed + trial)
        shapes = list(itertools.product(args.modes, args.batch_sizes, args.lengths))
        rng.shuffle(shapes)
        for mode, batch, length in shapes:
            qlen = length if mode == "prefill" else 1
            q32 = torch.randn(batch, args.heads, qlen, args.head_dim, device=device)
            k32, v32 = [torch.randn(batch, args.heads, length, args.head_dim, device=device) for _ in range(2)]
            with torch.inference_mode():
                reference = attention("eager", q32, k32, v32, mode)
            options = list(itertools.product(args.dtypes, backends))
            rng.shuffle(options)
            for dtype, backend in options:
                row = dict(device=args.device, mode=mode, batch=batch, heads=args.heads, length=length,
                           head_dim=args.head_dim, dtype=dtype, backend=backend, trial=trial, seed=args.seed + trial,
                           items_per_request=batch * qlen)
                q, k, v = [x.to(DTYPES[dtype]) for x in (q32, k32, v32)]
                try:
                    with warnings.catch_warnings(record=True) as caught, torch.inference_mode():
                        warnings.simplefilter("always")
                        result = attention(backend, q, k, v, mode)
                        metrics = error_metrics(reference, result)
                        del result
                        row.update(measure(lambda: attention(backend, q, k, v, mode), device, args.warmup, args.samples))
                        row.update(metrics, status="ok", reason="", warnings="; ".join(sorted({str(w.message) for w in caught})))
                except torch.cuda.OutOfMemoryError as exc:
                    row.update(status="oom", reason=str(exc).splitlines()[0])
                    torch.cuda.empty_cache()
                except RuntimeError as exc:
                    if "No available kernel" not in str(exc) and "No viable backend" not in str(exc):
                        raise
                    row.update(status="unsupported", reason=str(exc).splitlines()[0])
                rows.append(row)
                record(args.output, row)
                del q, k, v
            del q32, k32, v32, reference
            print(f"trial={trial} {mode} batch={batch} length={length}: recorded {len(options)} options", flush=True)
    summary = finish_run(args.output, metadata, rows)
    print(f"Saved {len(rows)} measurements / {len(summary)} configurations to {args.output}")


if __name__ == "__main__":
    main()
