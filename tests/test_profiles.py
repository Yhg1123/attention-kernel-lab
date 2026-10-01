import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import torch
from profile_workloads import attention


class WorkloadTests(unittest.TestCase):
    def test_decode_can_see_every_cached_value(self):
        q = torch.zeros(1, 1, 1, 4)
        k = torch.zeros(1, 1, 3, 4)
        v = torch.tensor([2., 5., 11.]).view(1, 1, 3, 1).expand_as(k)
        for backend in ("eager", "sdpa_math", "sdpa_auto"):
            torch.testing.assert_close(attention(backend, q, k, v, "decode"), torch.full_like(q, 6.))

    def test_cached_decode_matches_last_token_of_full_prefill(self):
        torch.manual_seed(12)
        q, k, v = [torch.randn(2, 2, 9, 8) for _ in range(3)]
        expected = attention("eager", q, k, v, "prefill")[..., -1:, :]
        for backend in ("eager", "sdpa_math", "sdpa_auto"):
            actual = attention(backend, q[..., -1:, :], k, v, "decode")
            torch.testing.assert_close(actual, expected)

    def test_prefill_cannot_see_future(self):
        torch.manual_seed(13)
        q, k, v = [torch.randn(1, 2, 9, 8) for _ in range(3)]
        for backend in ("eager", "sdpa_math", "sdpa_auto"):
            expected = attention(backend, q, k, v, "prefill")
            changed = v.clone()
            changed[..., -1, :] += 100
            actual = attention(backend, q, k, changed, "prefill")
            torch.testing.assert_close(actual[..., :-1, :], expected[..., :-1, :])

    def test_chunked_decode_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):
            attention("sdpa_auto", torch.zeros(1, 1, 2, 4), torch.zeros(1, 1, 5, 4), torch.zeros(1, 1, 5, 4), "decode")
