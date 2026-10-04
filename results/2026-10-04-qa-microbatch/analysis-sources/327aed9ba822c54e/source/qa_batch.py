"""Experimental static microbatches for local QA; not continuous batching.

Each row streams independently. Completion is conservatively emitted only after
the whole batch completes, so short answers may wait for the longest member.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from queue import Queue
import threading
import time

from qa_app import ANSWER_POLICIES, Engine, make_server, validate_scores


class MicroBatchWorker:
    def __init__(self, generate, max_batch=4, wait_ms=10):
        if type(max_batch) is not int or not 1 <= max_batch <= 4 or not math.isfinite(wait_ms) or wait_ms < 0:
            raise ValueError("max_batch must be 1..4 and wait_ms finite and nonnegative")
        self.generate, self.max_batch, self.wait_ms = generate, max_batch, wait_ms
        self.pending = []
        self.condition = threading.Condition()
        self.closed = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    @staticmethod
    def key(request):
        return (request['max_new_tokens'], request.get('fixed_tokens', False),
                request.get('answer_policy', 'baseline'))

    def _loop(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.closed)
                if not self.pending:
                    return
                selected = [self.pending.pop(0)]
                key = self.key(selected[0][0])
                deadline = time.perf_counter() + self.wait_ms / 1000
                while len(selected) < self.max_batch:
                    i = 0
                    while i < len(self.pending) and len(selected) < self.max_batch:
                        if self.key(self.pending[i][0]) == key:
                            selected.append(self.pending.pop(i))
                        else:
                            i += 1
                    remaining = deadline - time.perf_counter()
                    if len(selected) == self.max_batch or self.closed or remaining <= 0:
                        break
                    self.condition.wait(remaining)
            try:
                batch = [(r, lambda event, q=q: q.put(('event', event)), arrival)
                         for r, q, arrival in selected]
                self.generate(batch)
            except Exception as exc:
                for _, q, _ in selected:
                    q.put(('error', exc))
            finally:
                for _, q, _ in selected:
                    q.put(('end', None))

    def run(self, request, emit):
        events = Queue()
        with self.condition:
            if self.closed:
                raise RuntimeError('Microbatch worker is closed')
            self.pending.append((request, events, time.perf_counter()))
            self.condition.notify()
        while True:
            kind, value = events.get()
            if kind == 'end':
                return
            if kind == 'error':
                raise value
            emit(value)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.thread.join()


class BatchStreamer:
    def __init__(self, tokenizer, emitters, eos, decoder_factory=None):
        if decoder_factory is None:
            from transformers import TextStreamer
            decoder_factory = TextStreamer
        self.tokens = [[] for _ in emitters]
        self.parts = [[] for _ in emitters]
        self.first_token = [None for _ in emitters]
        self.eos_time = [None for _ in emitters]
        self.finished = [False for _ in emitters]
        self.ended = [False for _ in emitters]
        self.eos = set(eos)
        self.prompt = True
        self.decoders = []
        for i, emit in enumerate(emitters):
            decoder = decoder_factory(tokenizer, skip_prompt=False, skip_special_tokens=True)
            def on_text(text, stream_end=False, i=i, emit=emit):
                if text:
                    self.parts[i].append(text)
                    emit({'event': 'text', 'text': text})
            decoder.on_finalized_text = on_text
            self.decoders.append(decoder)

    def put(self, value):
        size = len(self.tokens)
        if self.prompt:
            if value.ndim != 2 or value.shape[0] != size:
                raise ValueError('Prompt batch dimension mismatch')
            self.prompt = False
            return
        if value.ndim != 1 or value.shape[0] != size:
            raise ValueError('Token batch dimension mismatch')
        now = time.perf_counter()
        for i, token in enumerate(value.tolist()):
            if self.finished[i]:
                continue
            if self.first_token[i] is None:
                self.first_token[i] = now
            self.tokens[i].append(token)
            self.decoders[i].put(value[i:i+1])
            if token in self.eos:
                self.finished[i] = True
                self.eos_time[i] = now
                self.decoders[i].end()
                self.ended[i] = True

    def end(self):
        for i, decoder in enumerate(self.decoders):
            if not self.ended[i]:
                decoder.end()
                self.ended[i] = True


class BatchEngine(Engine):
    def __init__(self, *, max_batch=4, wait_ms=10, local_files_only=False, threads=4):
        # Restrict this experiment to the validated eager BF16 baseline.
        super().__init__('cuda_eager_bf16', local_files_only=local_files_only, threads=threads)
        self.worker.close()
        self.tokenizer.padding_side = 'left'
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.batch_sequence = 0
        self.worker = MicroBatchWorker(self._generate_batch, max_batch, wait_ms)

    def _generate_batch(self, batch):
        from transformers import LogitsProcessor
        start = time.perf_counter()
        contexts = [self.kb.context(r['question'], r['context']) for r, _, _ in batch]
        retrieved = time.perf_counter()
        prompts = [self.tokenizer.apply_chat_template([
            {'role': 'system', 'content': ANSWER_POLICIES[r.get('answer_policy', 'baseline')]},
            {'role': 'user', 'content': f"资料：\n{context}\n\n问题：{r['question']}"}
        ], tokenize=False, add_generation_prompt=True)
            for (r, _, _), (context, _) in zip(batch, contexts)]
        encoded = self.tokenizer(prompts, padding=True, return_tensors='pt', add_special_tokens=False)
        inputs = [ids[mask.bool()].tolist() for ids, mask in zip(encoded['input_ids'], encoded['attention_mask'])]
        width = encoded['input_ids'].shape[1]
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        self.sync()
        tokenized = time.perf_counter()
        baseline = self.torch.cuda.memory_allocated()
        self.torch.cuda.reset_peak_memory_stats()
        eos = self.model.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        streamer = BatchStreamer(self.tokenizer, [emit for _, emit, _ in batch], eos)
        class FiniteLogits(LogitsProcessor):
            def __call__(self, input_ids, scores):
                validate_scores(scores)
                return scores
        request = batch[0][0]
        limit = request['max_new_tokens']
        generation_start = time.perf_counter()
        with self.torch.inference_mode():
            output = self.model.generate(
                **encoded, do_sample=False, use_cache=True, max_new_tokens=limit,
                min_new_tokens=limit if request['fixed_tokens'] else 0,
                streamer=streamer, logits_processor=[FiniteLogits()], pad_token_id=self.tokenizer.eos_token_id)
        self.sync()
        end = time.perf_counter()
        self.batch_sequence += 1
        for i, ((r, emit, arrival), (_, ids)) in enumerate(zip(batch, contexts)):
            tokens = streamer.tokens[i]
            # Verify every demultiplexed token against generate's returned tensor.
            if output[i, width:width+len(tokens)].tolist() != tokens:
                raise RuntimeError('Streamed token IDs differ from generated output')
            emit({
                'event': 'done', 'variant': self.variant, 'answer': ''.join(streamer.parts[i]),
                'answer_policy': r.get('answer_policy', 'baseline'), 'retrieved_ids': ids,
                'retrieved_documents': [next(dict(d) for d in self.kb.documents if d['id'] == key) for key in ids],
                'input_tokens': len(inputs[i]), 'output_tokens': len(tokens),
                'input_sha256': hashlib.sha256(json.dumps(inputs[i]).encode()).hexdigest(),
                'output_token_ids': tokens, 'stopped_on_eos': streamer.finished[i],
                'hit_token_limit': len(tokens) >= limit and not streamer.finished[i],
                'queue_ms': (start-arrival)*1000, 'retrieval_ms': (retrieved-start)*1000,
                'tokenize_transfer_ms': (tokenized-retrieved)*1000,
                'generation_ms': (end-generation_start)*1000,
                'server_first_token_ms': (streamer.first_token[i]-arrival)*1000 if streamer.first_token[i] else None,
                'server_total_ms': (end-arrival)*1000,
                'peak_allocated_mib': self.torch.cuda.max_memory_allocated()/2**20,
                'peak_extra_mib': (self.torch.cuda.max_memory_allocated()-baseline)/2**20,
                'memory_scope': 'batch', 'actual_batch_size': len(batch), 'batch_id': self.batch_sequence,
                'padded_input_tokens': width, 'padding_tokens': width-len(inputs[i]),
                'post_eos_wait_ms': (end-streamer.eos_time[i])*1000 if streamer.eos_time[i] else 0,
            })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-batch', type=int, choices=(1,2,4), default=4)
    parser.add_argument('--wait-ms', type=float, default=10)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--local-files-only', action='store_true')
    args = parser.parse_args()
    engine = BatchEngine(max_batch=args.max_batch, wait_ms=args.wait_ms, local_files_only=args.local_files_only)
    server = make_server(engine, args.port)
    print(f'Experimental microbatch QA: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()


if __name__ == '__main__':
    main()
