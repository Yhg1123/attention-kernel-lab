import json
from pathlib import Path
import sys
import threading
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa_app import InferenceWorker, make_server
from qa_load import run_clients, summarize_load, validate_rows


class SerialEngine:
    def __init__(self):
        self.worker = InferenceWorker(self.generate)

    def answer(self, request, emit):
        self.worker.run(request, emit)

    def generate(self, request, emit, arrival):
        started = time.perf_counter()
        time.sleep(.03)
        if request['question'] == 'bad':
            raise ValueError('deliberate failure')
        emit(dict(event='text', text=request['question']))
        emit(dict(event='done', answer=request['question'], queue_ms=(started-arrival)*1000))


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.engine = SerialEngine()
        self.server = make_server(self.engine)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.engine.worker.close()

    def test_real_http_clients_complete_each_job_once_and_observe_queue(self):
        payloads = [dict(question=f'question-{i}') for i in range(8)]
        rows, duration = run_clients(self.url, payloads, 4)
        self.assertEqual(sorted(r['job_index'] for r in rows), list(range(8)))
        self.assertTrue(all(r['status'] == 'ok' for r in rows))
        self.assertEqual({r['client_id'] for r in rows}, set(range(4)))
        self.assertTrue(any(r['queue_ms'] > 10 for r in rows))
        for r in rows:
            self.assertEqual(r['answer'], payloads[r['job_index']]['question'])
        self.assertGreater(duration, 0)

    def test_failed_requests_remain_in_denominator(self):
        rows, duration = run_clients(self.url, [dict(question='ok'), dict(question='bad')], 2)
        summary = summarize_load(rows, duration)
        self.assertEqual(summary['attempted'], 2)
        self.assertEqual(summary['completed'], 1)
        self.assertEqual(summary['errors'], 1)
        self.assertAlmostEqual(summary['completed_requests_per_second'], 1000 / duration)
        self.assertIn('deliberate failure', next(r for r in rows if r['status']=='error')['error'])

    def test_clients_must_fit_nonempty_workload(self):
        for jobs, clients in (([],1), ([{}],0), ([{}],2)):
            with self.assertRaises(ValueError):
                run_clients(self.url, jobs, clients)

    def test_validator_rejects_incomplete_duplicate_and_inconsistent_evidence(self):
        groups = [dict(trial=0,variant='test',context='short',clients=1,jobs=1)]
        row = dict(trial=0,variant='test',context='short',clients=1,job_index=0,status='ok',
                   client_id=0,client_first_text_ms=2,client_total_ms=10,queue_ms=1,
                   client_start_offset_ms=0,client_end_offset_ms=11,
                   output_tokens=1,output_token_ids=[9],input_sha256='x')
        validate_rows([row],groups)
        for bad in ([],[row,row],[dict(row,client_first_text_ms=20)],
                    [dict(row,queue_ms=float('nan'))], [dict(row,output_tokens=2)]):
            with self.assertRaises(ValueError):
                validate_rows(bad,groups)
