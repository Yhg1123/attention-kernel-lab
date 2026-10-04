from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analyze_qa_batch import analyze, lf_sha256


def row(trial,method,duration,tokens):
    return dict(trial=trial,variant=method,context='short',clients=1,job_index=0,status='ok',
                client_end_offset_ms=duration,client_first_text_ms=10,client_total_ms=duration,
                queue_ms=0,generation_ms=duration-10,output_tokens=len(tokens),output_token_ids=tokens,
                answer=str(tokens),question_id='price',fact_check_pass=True,peak_allocated_mib=3000)


class BatchAnalysisTests(unittest.TestCase):
    def analyze_rows(self,rows,fixed=False):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)
            for name in ('metadata.json','requests.jsonl'):
                (path/name).write_text('mocked verifier input',encoding='utf-8')
            with patch('analyze_qa_batch.verify',return_value=({'arguments':{'fixed_tokens':fixed}},rows)):
                return analyze(path)

    def test_pooled_throughput_uses_total_elapsed_time_and_preserves_paired_ratios(self):
        rows=[row(0,'serial',1000,[1]),row(1,'serial',9000,[1]),
              row(0,'batch2',1000,[1]),row(1,'batch2',3000,[2])]
        result=self.analyze_rows(rows)
        summaries={r['method']:r for r in result['summaries']}
        self.assertAlmostEqual(summaries['serial']['completed_requests_per_second'],0.2)
        self.assertAlmostEqual(summaries['batch2']['completed_requests_per_second'],0.5)
        self.assertEqual(summaries['batch2']['paired_throughput_ratios'],[1.0,3.0])
        self.assertEqual(summaries['batch2']['changed_output_tokens'],1)
        self.assertEqual(summaries['batch2']['matched_serial_outputs'],2)

    def test_failed_requests_still_contribute_to_elapsed_time(self):
        rows=[row(0,'batch2',1000,[1]),dict(trial=1,variant='batch2',context='short',clients=1,
              job_index=0,status='error',client_end_offset_ms=9000)]
        result=self.analyze_rows(rows)
        summary=result['summaries'][0]
        self.assertAlmostEqual(summary['completed_requests_per_second'],0.1)
        self.assertEqual(summary['errors'],1)
        self.assertEqual(summary['paired_throughput_ratios'],[])

    def test_fixed_token_controls_do_not_publish_quality_scores(self):
        rows=[row(0,'serial',1000,[1]),row(0,'batch2',1000,[2])]
        for r in rows:
            del r['fact_check_pass']
        result=self.analyze_rows(rows,fixed=True)
        self.assertTrue(all(r['keyword_passes'] is None for r in result['summaries']))
        self.assertEqual(set(result['input_lf_sha256']),{'metadata.json','requests.jsonl'})
        self.assertIn('analyze_qa_batch.py',result['analysis_source_sha256'])

    def test_input_hash_survives_git_newline_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'input.jsonl'
            path.write_bytes(b'{"answer":"same"}\r\n')
            windows=lf_sha256(path)
            path.write_bytes(b'{"answer":"same"}\n')
            self.assertEqual(lf_sha256(path),windows)
            path.write_bytes(b'{"answer":"changed"}\n')
            self.assertNotEqual(lf_sha256(path),windows)
