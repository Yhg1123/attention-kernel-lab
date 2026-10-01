import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from bench_utils import fingerprint
from measured_attention import MeasuredAttention


class MeasuredAttentionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "policy.json"
        source = Path(__file__).resolve().parents[1] / "profile_workloads.py"
        self.policy = {"schema_version": 2, "environment_fingerprint": fingerprint({"test": True}),
                       "profiler_source_sha256": {source.name: hashlib.sha256(source.read_bytes()).hexdigest()},
                       "decisions": [{"workload": {"device": "cpu", "mode": "decode", "batch": "1", "heads": "1", "length": "3", "head_dim": "4", "dtype": "float32"},
                                      "status": "selected", "selected": "sdpa_auto"}]}
        self.path.write_text(json.dumps(self.policy), encoding="utf-8")

    def test_exact_workload_runs_and_unknown_shape_is_rejected(self):
        with patch("measured_attention.environment", return_value={"test": True}):
            selected = MeasuredAttention(self.path)
        q, k, v = torch.zeros(1, 1, 1, 4), torch.zeros(1, 1, 3, 4), torch.ones(1, 1, 3, 4)
        torch.testing.assert_close(selected(q, k, v, mode="decode"), torch.ones_like(q))
        with self.assertRaisesRegex(ValueError, "No feasible measured"):
            selected(q, k[:, :, :2].contiguous(), v[:, :, :2].contiguous(), mode="decode")

    def test_environment_mismatch_is_rejected(self):
        with patch("measured_attention.environment", return_value={"test": False}):
            with self.assertRaisesRegex(ValueError, "Environment differs"):
                MeasuredAttention(self.path)

    def test_source_change_is_rejected(self):
        self.policy["profiler_source_sha256"]["profile_workloads.py"] = "changed"
        self.path.write_text(json.dumps(self.policy), encoding="utf-8")
        with patch("measured_attention.environment", return_value={"test": True}):
            with self.assertRaisesRegex(ValueError, "implementation changed"):
                MeasuredAttention(self.path)
