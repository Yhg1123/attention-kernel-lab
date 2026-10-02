import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa_quality import grade, is_refusal
from qa_app import ROOT, validate_request


class QualityGateTests(unittest.TestCase):
    def test_refusal_cannot_hide_fabricated_answer(self):
        unknown = dict(unanswerable=True)
        self.assertTrue(grade(unknown, "文档未提供。\n")["fact_check_pass"])
        self.assertFalse(grade(unknown, "文档未提供，但价格是99元。")["fact_check_pass"])
        self.assertFalse(is_refusal("文档未提供关于价格的信息。"))

    def test_false_refusal_is_distinct_from_wrong_fact(self):
        known = dict(required=[["99"], ["200GB"]])
        self.assertTrue(grade(known, "文档未提供。")["false_refusal"])
        self.assertFalse(grade(known, "每月39元。")["false_refusal"])
        self.assertTrue(grade(known, "每月99元，200GB。")["fact_check_pass"])

    def test_split_is_disjoint_and_covers_answerable_and_unknown_cases(self):
        cases = json.loads((ROOT / "qa_quality_cases.json").read_text(encoding="utf-8"))["questions"]
        self.assertEqual(len({c["id"] for c in cases}), 32)
        for split, total in (("dev", 8), ("heldout", 24)):
            chosen = [c for c in cases if c["split"] == split]
            self.assertEqual(len(chosen), total)
            self.assertTrue(any(c.get("unanswerable") for c in chosen))
            self.assertTrue(any(not c.get("unanswerable") for c in chosen))

    def test_policy_is_explicit_and_original_default_is_preserved(self):
        self.assertEqual(validate_request({"question":"x"})["answer_policy"], "baseline")
        self.assertEqual(validate_request({"question":"x", "answer_policy":"strict"})["answer_policy"], "strict")
        for bad in ([], {}, None, "unknown"):
            with self.assertRaises(ValueError):
                validate_request({"question":"x", "answer_policy":bad})

    def test_known_negation_false_positives_are_rejected(self):
        cases = {c["id"]: c for c in json.loads((ROOT / "qa_quality_cases.json").read_text(encoding="utf-8"))["questions"]}
        for case, answer in (("refund_allowed", "不符合。只有7天内且没有创建项目才能申请。"),
                             ("storage_count", "不计入。")):
            self.assertFalse(grade(cases[case], answer)["fact_check_pass"])
        self.assertTrue(grade(cases["refund_allowed"], "符合，可以申请全额退款。")["fact_check_pass"])
        self.assertTrue(grade(cases["storage_count"], "回收站里的文件也计入团队容量。")["fact_check_pass"])
