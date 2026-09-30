import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch

from benchmark import eager_attention, run_backend


class AttentionTests(unittest.TestCase):
    def test_causal_eager_matches_sdpa_math(self):
        torch.manual_seed(7)
        q, k, v = [torch.randn(1, 2, 12, 16) for _ in range(3)]
        actual = eager_attention(q, k, v)
        expected = run_backend("sdpa_math", q, k, v)
        torch.testing.assert_close(actual, expected, rtol=1e-5, atol=1e-6)

    def test_future_tokens_do_not_change_previous_output(self):
        torch.manual_seed(8)
        q, k, v = [torch.randn(1, 1, 8, 16) for _ in range(3)]
        baseline = eager_attention(q, k, v)
        k[..., 7, :] += 10
        v[..., 7, :] += 10
        changed = eager_attention(q, k, v)
        torch.testing.assert_close(baseline[..., :7, :], changed[..., :7, :])


if __name__ == "__main__":
    unittest.main()
