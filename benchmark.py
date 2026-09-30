"""Compare eager attention with PyTorch SDPA backends on reproducible inputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import statistics
import time
import warnings
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel


def eager_attention(q: torch.Tensor, k: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    scores = (q @ k.transpose(-2, -1)) / math.sqrt(q.shape[-1])
    length = q.shape[-2]
    mask = torch.ones((length, length), device=q.device, dtype=torch.bool).tril()
    scores = scores.masked_fill(~mask, torch.finfo(scores.dtype).min)
    return torch.softmax(scores, dim=-1) @ v


def run_backend(name: str, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    if name == "eager":
        return eager_attention(q, k, v)
    if name == "sdpa_auto":
        return F.scaled_dot_product_attention(q, k, v, is_causal=True)
    selected = {
        "sdpa_math": SDPBackend.MATH,
        "sdpa_flash": SDPBackend.FLASH_ATTENTION,
        "sdpa_efficient": SDPBackend.EFFICIENT_ATTENTION,
        "sdpa_cudnn": SDPBackend.CUDNN_ATTENTION,
    }[name]
    with sdpa_kernel(selected):
        return F.scaled_dot_product_attention(q, k, v, is_causal=True)


def time_backend(name: str, q: torch.Tensor, k: torch.Tensor, v: torch.Tensor,
                 warmup: int, repeats: int) -> tuple[float, float, int | None]:
    device = q.device
    with torch.inference_mode():
        for _ in range(warmup):
            run_backend(name, q, k, v)
        if device.type == "cuda":
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            baseline_bytes = torch.cuda.memory_allocated()
            starts = [torch.cuda.Event(enable_timing=True) for _ in range(repeats)]
            ends = [torch.cuda.Event(enable_timing=True) for _ in range(repeats)]
            for start, end in zip(starts, ends):
                start.record()
                run_backend(name, q, k, v)
                end.record()
            torch.cuda.synchronize()
            times_ms = [start.elapsed_time(end) for start, end in zip(starts, ends)]
            peak_bytes = max(0, torch.cuda.max_memory_allocated() - baseline_bytes)
        else:
            times_ms = []
            for _ in range(repeats):
                start = time.perf_counter()
                run_backend(name, q, k, v)
                times_ms.append((time.perf_counter() - start) * 1000)
            peak_bytes = None
    return statistics.median(times_ms), statistics.pstdev(times_ms), peak_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--lengths", nargs="+", type=int, default=[128, 256, 512, 1024])
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--repeats", type=int, default=100)
    args = parser.parse_args()
    if any(n < 1 for n in args.lengths) or args.warmup < 0 or args.repeats < 2:
        parser.error("lengths must be positive; repeats must be at least 2")
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else args.device
    if device_name == "auto":
        device_name = "cpu"
    if device_name == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was selected but this PyTorch installation cannot use it")
    device = torch.device(device_name)
    torch.manual_seed(2026)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(2026)
        torch.backends.cuda.matmul.allow_tf32 = False
    dtypes = [torch.float32, torch.float16] if device.type == "cuda" else [torch.float32]
    backends = ["eager", "sdpa_math", "sdpa_auto", "sdpa_flash", "sdpa_efficient", "sdpa_cudnn"] if device.type == "cuda" else ["eager", "sdpa_math", "sdpa_auto"]
    rows: list[dict] = []

    for length in args.lengths:
        for dtype in dtypes:
            shape = (1, 4, length, 64)
            q32, k32, v32 = [torch.randn(shape, device=device, dtype=torch.float32) for _ in range(3)]
            with torch.inference_mode():
                reference = eager_attention(q32, k32, v32)
            q, k, v = (t.to(dtype) for t in (q32, k32, v32))
            for backend in backends:
                row = {"length": length, "dtype": str(dtype).split(".")[-1], "backend": backend}
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        with torch.inference_mode():
                            result = run_backend(backend, q, k, v).float()
                        if device.type == "cuda":
                            torch.cuda.synchronize()
                        difference = result - reference
                        row["max_abs_error"] = float(difference.abs().max())
                        row["relative_l2_error"] = float(torch.linalg.vector_norm(difference) / torch.linalg.vector_norm(reference))
                        median_ms, stdev_ms, peak_bytes = time_backend(backend, q, k, v, args.warmup, args.repeats)
                        row.update(median_ms=median_ms, stdev_ms=stdev_ms, peak_extra_mib=round(peak_bytes / 2**20, 3) if peak_bytes is not None else None, status="ok")
                except (RuntimeError, NotImplementedError) as exc:
                    row.update(median_ms=None, stdev_ms=None, peak_extra_mib=None,
                               max_abs_error=None, relative_l2_error=None,
                               status=f"unsupported: {str(exc).splitlines()[0][:120]}")
                rows.append(row)
                print(f"L={length:4d} {row['dtype']:7s} {backend:11s} {row['status']:12s} {row['median_ms']}", flush=True)
            del q, k, v, q32, k32, v32, reference
            if device.type == "cuda":
                torch.cuda.empty_cache()

    for row in rows:
        baseline = next((r["median_ms"] for r in rows if r["length"] == row["length"] and r["dtype"] == row["dtype"] and r["backend"] == "eager"), None)
        row["speedup_vs_eager"] = baseline / row["median_ms"] if baseline and row["median_ms"] else None

    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "results.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "torch": torch.__version__, "python": platform.python_version(),
        "platform": platform.platform(), "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "cuda_runtime": torch.version.cuda, "seed": 2026,
        "shape": "batch=1, heads=4, head_dim=64", "causal": True,
        "warmup": args.warmup, "repeats": args.repeats,
        "timing": "CUDA events per call, or wall clock on CPU; median of repeats",
        "peak_extra_mib": "PyTorch allocator peak above allocated input baseline; includes output and temporary tensors",
        "note": "FP16 error includes input casting relative to FP32 eager reference; no model quality is measured",
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(rows)} rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()
