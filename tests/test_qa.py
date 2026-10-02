import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa_app import KnowledgeBase, InferenceWorker, check_answer, make_server, validate_request, validate_scores
from qa_benchmark import paired_comparisons, request_qa


class QADataTests(unittest.TestCase):
    def test_answerable_facts_are_retrievable_without_gold_input(self):
        kb = KnowledgeBase()
        for case in kb.questions:
            _, ids = kb.context(case["question"], "short")
            self.assertTrue(set(case["documents"]).issubset(ids), case["id"])

    def test_cross_document_question_needs_both_documents(self):
        kb = KnowledgeBase()
        case = next(c for c in kb.questions if c["id"] == "combined")
        short, ids = kb.context(case["question"], "short")
        long, more = kb.context(case["question"], "long")
        self.assertEqual(set(ids), {"plan", "support"})
        self.assertEqual(len(more), len(set(more)))
        self.assertTrue(long.startswith(short))

    def test_quality_gate_rejects_missing_fact_and_unknown_hallucination(self):
        cases = {c["id"]: c for c in KnowledgeBase().questions}
        self.assertTrue(check_answer(cases["price"], "每月99元，200GB。")['fact_check_pass'])
        self.assertFalse(check_answer(cases["price"], "每月99元。")['fact_check_pass'])
        self.assertFalse(check_answer(cases["unknown"], "企业版9999元。")['fact_check_pass'])

    def test_invalid_requests_fail_before_model_generation(self):
        for data in ([], {}, {"question": " "}, {"question": "x", "max_new_tokens": True},
                     {"question": "x", "fixed_tokens": "false"}, {"question": "x", "context": "huge"}):
            with self.assertRaises(ValueError):
                validate_request(data)

    def test_invalid_logits_fail_but_deliberate_eos_mask_is_valid(self):
        import torch
        validate_scores(torch.tensor([[0.2, float('-inf'), 0.4]]))
        for values in ([[float('nan'), 1.]], [[float('inf'), 1.]], [[float('-inf'), float('-inf')]]):
            with self.assertRaises(FloatingPointError):
                validate_scores(torch.tensor(values))


class FakeEngine:
    def answer(self, request, emit):
        if request["question"] == "error":
            raise RuntimeError("deliberate test error")
        emit({"event": "text", "text": "回答"})
        emit({"event": "text", "text": "完成。"})
        emit({"event": "done", "answer": "回答完成。", "retrieved_documents": [
            {"id":"fixture", "title":"测试原文", "text":"<script>not executable</script> 中文资料"}]})


class QAHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(FakeEngine())
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def test_ui_and_stream_work_through_http(self):
        with urllib.request.urlopen(self.url) as response:
            self.assertIn(b"/ask", response.read())
        result = request_qa(self.url, {"question": "test"})
        self.assertEqual(result["answer"], "回答完成。")
        self.assertEqual(result["retrieved_documents"][0]["text"], "<script>not executable</script> 中文资料")
        self.assertLessEqual(result["client_first_text_ms"], result["client_total_ms"])

    def test_model_exception_is_not_counted_as_completed_request(self):
        with self.assertRaisesRegex(RuntimeError, "deliberate test error"):
            request_qa(self.url, {"question": "error"})

    def test_bad_request_is_rejected_over_http(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            request_qa(self.url, {"question": "x", "max_new_tokens": -1})
        self.assertEqual(ctx.exception.code, 400)


class QAPairTests(unittest.TestCase):
    def test_mismatched_prompts_cannot_claim_speedup(self):
        base = dict(trial=0, question_id="x", context="short", mode="fixed", input_sha256="a")
        with self.assertRaisesRegex(RuntimeError, "unequal prompt"):
            paired_comparisons([dict(base, variant="cuda_eager_fp16"),
                                dict(base, variant="cuda_sdpa_fp16", input_sha256="b")])

    def test_inference_reuses_one_thread_and_recovers_after_error(self):
        identities, events = [], []
        def generate(request, emit, arrival):
            identities.append(threading.get_ident())
            if request == "bad":
                raise ValueError("rejected")
            emit(request)
        worker = InferenceWorker(generate)
        try:
            worker.run("first", events.append)
            with self.assertRaisesRegex(ValueError, "rejected"):
                worker.run("bad", events.append)
            worker.run("last", events.append)
            self.assertEqual(events, ["first", "last"])
            self.assertEqual(len(set(identities)), 1)
            self.assertNotEqual(identities[0], threading.get_ident())
        finally:
            worker.close()
