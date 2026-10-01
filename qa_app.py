"""Local streaming document QA application; no API key or remote model code required."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext
import gc
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
from queue import Queue
import re
import threading
import time

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
REVISION = "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
ROOT = Path(__file__).resolve().parent
VARIANTS = ("cuda_eager_fp16", "cuda_sdpa_fp16", "cuda_eager_bf16", "cuda_sdpa_bf16", "cuda_cudnn_bf16",
            "cpu_eager_fp32", "cpu_eager_int8", "cpu_eager_int8_mlp", "cpu_eager_int8_mlp_per_channel")
DEFAULT_VARIANTS = ("cuda_eager_bf16", "cuda_sdpa_bf16", "cuda_cudnn_bf16", "cpu_eager_fp32")
SYSTEM = "你是青禾云文档助手。只根据提供的资料回答；资料没有答案时，只回答‘文档未提供’。请简洁、准确，最多三句话，不复述问题。"


def terms(text):
    """ASCII words and Chinese character bigrams for deterministic local retrieval."""
    out = re.findall(r"[a-z0-9]+", text.lower())
    for part in re.findall(r"[\u4e00-\u9fff]+", text):
        out.extend(part[i:i + 2] for i in range(max(1, len(part) - 1)))
    return out


class KnowledgeBase:
    def __init__(self, path=ROOT / "qa_fixtures.json"):
        self.raw = Path(path).read_bytes()
        data = json.loads(self.raw)
        self.documents, self.questions = data["documents"], data["questions"]
        self.counts = [Counter(terms(d["title"] + " " + d["text"])) for d in self.documents]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.average = sum(self.lengths) / len(self.lengths)

    def retrieve(self, question, top_k=2):
        query = set(terms(question))
        scores = []
        for doc, counts, length in zip(self.documents, self.counts, self.lengths):
            score = 0.0
            for term in query:
                frequency = counts[term]
                df = sum(term in c for c in self.counts)
                idf = math.log(1 + (len(self.documents) - df + .5) / (df + .5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / self.average))
            scores.append((score, doc))
        return [d for _, d in sorted(scores, key=lambda x: (-x[0], x[1]["id"]))[:top_k]]

    def context(self, question, size):
        chosen = self.retrieve(question)
        if size == "long":
            chosen += [d for d in self.documents if d not in chosen]
        return "\n\n".join(f"[{d['id']}] {d['title']}\n{d['text']}" for d in chosen), [d["id"] for d in chosen]


def check_answer(case, answer):
    normalized = answer.lower()
    required = [any(option.lower() in normalized for option in group) for group in case["required"]]
    forbidden = [term for term in case.get("forbidden", []) if term.lower() in normalized]
    return {"fact_check_pass": all(required) and not forbidden,
            "required_groups_pass": required, "forbidden_matches": forbidden}


def validate_scores(scores):
    # Generation processors intentionally mask EOS with -inf for min_new_tokens.
    invalid = (scores.isnan() | scores.isposinf()).any() | (~scores.isfinite().any(dim=-1)).any()
    if invalid:
        raise FloatingPointError("Invalid model logits; this precision/backend is unusable")


class InferenceWorker:
    """Keep GPU execution on one persistent thread across HTTP requests."""
    def __init__(self, generate):
        self.generate = generate
        self.tasks = Queue()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while True:
            task = self.tasks.get()
            if task is None:
                return
            request, events, arrival = task
            try:
                self.generate(request, lambda event: events.put(("event", event)), arrival)
            except Exception as exc:
                events.put(("error", exc))
            finally:
                events.put(("end", None))

    def run(self, request, emit):
        events = Queue()
        self.tasks.put((request, events, time.perf_counter()))
        while True:
            kind, value = events.get()
            if kind == "end":
                return
            if kind == "error":
                raise value
            emit(value)

    def close(self):
        self.tasks.put(None)
        self.thread.join()


class Engine:
    def __init__(self, variant, *, local_files_only=False, threads=4):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if variant not in VARIANTS:
            raise ValueError(f"Unknown variant: {variant}")
        torch.set_num_threads(threads)
        torch.manual_seed(2026)
        torch.backends.cuda.matmul.allow_tf32 = False
        self.torch, self.variant = torch, variant
        self.device = "cuda" if variant.startswith("cuda") else "cpu"
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        start = time.perf_counter()
        kwargs = dict(revision=REVISION, local_files_only=local_files_only, trust_remote_code=False)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL, **kwargs)
        dtype = torch.bfloat16 if variant.endswith("bf16") else torch.float16 if self.device == "cuda" else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL, **kwargs, use_safetensors=True,
            dtype=dtype, attn_implementation="sdpa" if "sdpa" in variant or "cudnn" in variant else "eager").eval().to(self.device)
        if variant.startswith("cpu_eager_int8"):
            from torch.ao.quantization import quantize_dynamic
            engine = next((e for e in ("x86", "fbgemm", "qnnpack", "onednn")
                           if e in torch.backends.quantized.supported_engines), None)
            if engine is None:
                raise RuntimeError("No supported CPU dynamic quantization backend")
            torch.backends.quantized.engine = engine
            # In-place conversion avoids a second full FP32 model in host memory.
            selected = ({name for name, module in self.model.named_modules()
                         if isinstance(module, torch.nn.Linear) and ".mlp." in name}
                        if "_mlp" in variant else {torch.nn.Linear})
            if variant.endswith("per_channel"):
                from torch.ao.quantization import per_channel_dynamic_qconfig
                selected = {name: per_channel_dynamic_qconfig for name in selected}
            self.model = quantize_dynamic(self.model, selected, dtype=torch.qint8, inplace=True).eval()
        self.sync()
        self.load_seconds = time.perf_counter() - start
        self.kb = KnowledgeBase()
        self.lock = threading.Lock()
        self.worker = InferenceWorker(self._generate)

    def sync(self):
        if self.device == "cuda":
            self.torch.cuda.synchronize()

    def close(self):
        self.worker.close()
        del self.model
        gc.collect()
        if self.device == "cuda":
            self.torch.cuda.empty_cache()

    def answer(self, request, emit):
        self.worker.run(request, emit)

    def _generate(self, request, emit, arrival):
        from transformers import TextStreamer, LogitsProcessor

        with self.lock:
            start = time.perf_counter()
            context, ids = self.kb.context(request["question"], request["context"])
            retrieved = time.perf_counter()
            prompt = self.tokenizer.apply_chat_template([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"资料：\n{context}\n\n问题：{request['question']}"}
            ], tokenize=False, add_generation_prompt=True)
            encoded = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
            input_ids = encoded["input_ids"][0].tolist()
            encoded = {k: v.to(self.device) for k, v in encoded.items()}
            self.sync()
            tokenized = time.perf_counter()
            if self.device == "cuda":
                baseline = self.torch.cuda.memory_allocated()
                self.torch.cuda.reset_peak_memory_stats()
            generation_start = time.perf_counter()

            class Streamer(TextStreamer):
                def __init__(stream):
                    super().__init__(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
                    stream.first_token = None
                    stream.tokens = []
                    stream.parts = []

                def put(stream, value):
                    if not stream.next_tokens_are_prompt:
                        if stream.first_token is None:
                            stream.first_token = time.perf_counter()
                        stream.tokens.extend(value.flatten().tolist())
                    super().put(value)

                def on_finalized_text(stream, text, stream_end=False):
                    if text:
                        stream.parts.append(text)
                        emit({"event": "text", "text": text})

            streamer = Streamer()
            class FiniteLogits(LogitsProcessor):
                def __call__(self, input_ids, scores):
                    validate_scores(scores)
                    return scores

            limit = request["max_new_tokens"]
            if "cudnn" in self.variant:
                from torch.nn.attention import sdpa_kernel, SDPBackend
                backend_context = sdpa_kernel(SDPBackend.CUDNN_ATTENTION)
            else:
                backend_context = nullcontext()
            with self.torch.inference_mode(), backend_context:
                output = self.model.generate(
                    **encoded, do_sample=False, use_cache=True, max_new_tokens=limit,
                    min_new_tokens=limit if request["fixed_tokens"] else 0,
                    streamer=streamer, logits_processor=[FiniteLogits()], pad_token_id=self.tokenizer.eos_token_id)
            self.sync()
            end = time.perf_counter()
            answer = "".join(streamer.parts)
            eos = self.model.generation_config.eos_token_id
            eos = eos if isinstance(eos, list) else [eos]
            result = {
                "event": "done", "variant": self.variant, "answer": answer,
                "retrieved_ids": ids, "input_tokens": len(input_ids), "output_tokens": len(streamer.tokens),
                "input_sha256": hashlib.sha256(json.dumps(input_ids).encode()).hexdigest(),
                "output_token_ids": streamer.tokens,
                "stopped_on_eos": bool(streamer.tokens and streamer.tokens[-1] in eos),
                "hit_token_limit": len(streamer.tokens) >= limit and not (streamer.tokens and streamer.tokens[-1] in eos),
                "queue_ms": (start - arrival) * 1000, "retrieval_ms": (retrieved - start) * 1000,
                "tokenize_transfer_ms": (tokenized - retrieved) * 1000,
                "generation_ms": (end - generation_start) * 1000,
                "server_first_token_ms": (streamer.first_token - arrival) * 1000 if streamer.first_token else None,
                "server_total_ms": (end - arrival) * 1000,
                "peak_allocated_mib": self.torch.cuda.max_memory_allocated() / 2**20 if self.device == "cuda" else None,
                "peak_extra_mib": (self.torch.cuda.max_memory_allocated() - baseline) / 2**20 if self.device == "cuda" else None,
            }
            del output, encoded
            emit(result)


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError("Request must be an object")
    question = data.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("question must contain 1..2000 characters")
    context = data.get("context", "short")
    limit = data.get("max_new_tokens", 96)
    fixed = data.get("fixed_tokens", False)
    if context not in ("short", "long") or type(limit) is not int or not 1 <= limit <= 256 or type(fixed) is not bool:
        raise ValueError("context short/long; max_new_tokens 1..256; fixed_tokens boolean")
    return dict(question=question.strip(), context=context, max_new_tokens=limit, fixed_tokens=fixed)


def make_server(engine, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            page = (ROOT / "qa_ui.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):
            if self.path != "/ask":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16000:
                    raise ValueError("Invalid request length")
                request = validate_request(json.loads(self.rfile.read(length)))
            except (ValueError, UnicodeDecodeError) as exc:
                self.send_error(400, str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

            def emit(event):
                self.wfile.write((json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n").encode())
                self.wfile.flush()
            try:
                engine.answer(request, emit)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except Exception as exc:
                emit({"event": "error", "message": f"{type(exc).__name__}: {exc}"})
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=VARIANTS, default="cuda_sdpa_bf16")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--local-files-only", action="store_true")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("threads must be positive")
    engine = Engine(args.variant, local_files_only=args.local_files_only, threads=args.threads)
    server = make_server(engine, args.port)
    print(f"{args.variant}: http://127.0.0.1:{server.server_port} (load {engine.load_seconds:.2f}s)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()


if __name__ == "__main__":
    main()
