from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from qa_batch import BatchStreamer, MicroBatchWorker


class Decoder:
    def __init__(self,tokenizer,**kwargs):
        pass
    def put(self,value):
        self.on_finalized_text(''.join({1:'甲',2:'乙',3:'丙',9:''}[x] for x in value.tolist()))
    def end(self):
        self.on_finalized_text('',stream_end=True)


class BatchTests(unittest.TestCase):
    def test_stream_routes_rows_and_drops_padding_after_individual_eos(self):
        events=[[],[]]
        stream=BatchStreamer(None,[events[0].append,events[1].append],[9],decoder_factory=Decoder)
        stream.put(torch.tensor([[99,1],[99,2]]))
        stream.put(torch.tensor([1,2]))
        stream.put(torch.tensor([9,3]))
        stream.put(torch.tensor([9,9]))
        stream.end()
        self.assertEqual(stream.tokens,[[1,9],[2,3,9]])
        self.assertEqual([''.join(e['text'] for e in part) for part in events],['甲','乙丙'])
        self.assertEqual(stream.finished,[True,True])
        self.assertTrue(all(t is not None for t in stream.first_token))

    def test_stream_rejects_wrong_batch_dimension(self):
        stream=BatchStreamer(None,[lambda event:None],[9],decoder_factory=Decoder)
        with self.assertRaises(ValueError):
            stream.put(torch.tensor([[1],[2]]))

    def test_compatible_requests_coalesce_without_cross_delivery(self):
        groups=[]
        def generate(batch):
            groups.append([r['question'] for r,_,_ in batch])
            for request,emit,_ in batch:
                emit(request['question'])
        worker=MicroBatchWorker(generate,4,100)
        self.addCleanup(worker.close)
        barrier=threading.Barrier(5)
        def run(i):
            barrier.wait()
            events=[]
            worker.run(dict(question=str(i),max_new_tokens=96,fixed_tokens=False),events.append)
            return events
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(run,i) for i in range(4)]
            barrier.wait()
            self.assertEqual([f.result(timeout=3) for f in futures],[[str(i)] for i in range(4)])
        self.assertEqual(len(groups),1)

    def test_incompatible_limits_do_not_mix_and_batch_failure_does_not_kill_worker(self):
        groups=[]
        def generate(batch):
            groups.append({r['max_new_tokens'] for r,_,_ in batch})
            if any(r['question']=='bad' for r,_,_ in batch):
                raise RuntimeError('deliberate batch failure')
            for request,emit,_ in batch:
                emit(request['question'])
        worker=MicroBatchWorker(generate,2,10)
        self.addCleanup(worker.close)
        with self.assertRaisesRegex(RuntimeError,'deliberate'):
            worker.run(dict(question='bad',max_new_tokens=1),lambda e:None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(worker.run,dict(question='ok',max_new_tokens=n),lambda e:None) for n in (1,2)]
            for f in futures: f.result(timeout=3)
        self.assertTrue(all(len(g)==1 for g in groups))
        worker.close()
        with self.assertRaises(RuntimeError):
            worker.run(dict(question='late',max_new_tokens=1),lambda e:None)

    def test_invalid_scheduler_settings_are_rejected(self):
        for size,wait in ((0,10),(5,10),(1,-1),(2,float('nan'))):
            with self.assertRaises(ValueError):
                MicroBatchWorker(lambda batch:None,size,wait)
