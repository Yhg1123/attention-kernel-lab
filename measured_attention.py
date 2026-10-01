"""Use a measured attention policy with strict environment and workload checks."""
import hashlib
import json
from pathlib import Path

from bench_utils import environment, fingerprint
from profile_workloads import GROUPS, attention


class MeasuredAttention:
    """Inference-only helper; unknown shapes/environments fail instead of guessing."""

    def __init__(self, policy_path):
        policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
        if policy.get("schema_version") != 2:
            raise ValueError("A schema-v2 measured policy is required")
        if fingerprint(environment()) != policy["environment_fingerprint"]:
            raise ValueError("Environment differs from profiling; remeasure before using this policy")
        source = Path(__file__).with_name("profile_workloads.py")
        if hashlib.sha256(source.read_bytes()).hexdigest() != policy["profiler_source_sha256"][source.name]:
            raise ValueError("Attention implementation changed; remeasure before using this policy")
        self.decisions = {tuple(str(d["workload"][k]) for k in GROUPS): d for d in policy["decisions"]}

    def __call__(self, q, k, v, *, mode):
        if any(t.requires_grad for t in (q, k, v)):
            raise ValueError("Policy covers inference, not gradients/training")
        if any(t.ndim != 4 or not t.is_contiguous() for t in (q, k, v)):
            raise ValueError("Policy requires contiguous rank-4 inputs")
        if len({(t.device, t.dtype) for t in (q, k, v)}) != 1:
            raise ValueError("Q/K/V must have the same device and dtype")
        key = (q.device.type, mode, str(q.shape[0]), str(q.shape[1]), str(k.shape[2]),
               str(q.shape[3]), str(q.dtype).split(".")[-1])
        decision = self.decisions.get(key)
        if decision is None or decision["status"] != "selected":
            raise ValueError("No feasible measured configuration for this exact workload")
        return attention(decision["selected"], q, k, v, mode)
