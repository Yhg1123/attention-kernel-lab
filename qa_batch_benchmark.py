"""Matched HTTP comparisons of serial QA and experimental static microbatches."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import threading

from qa_app import Engine, KnowledgeBase, MODEL, REVISION, ROOT, check_answer, make_server
from qa_batch import BatchEngine
from qa_evidence import snapshot_sources, source_directory
from qa_load import run_clients, summarize_load, validate_rows

METHODS = ('serial', 'batch1', 'batch2', 'batch4')


def planned_groups(args, count):
    return [dict(trial=t, variant=m, context=c, clients=n, jobs=count*args['repetitions'])
            for t in range(args['trials']) for m in args['methods']
            for c in ('short','long') for n in args['clients']]


def verify(run):
    meta = json.loads((run/'metadata.json').read_text(encoding='utf-8'))
    if meta.get('schema') != 'qa-microbatch-v1' or not meta.get('completed_utc'):
        raise ValueError('Incomplete microbatch experiment')
    source = source_directory(run, meta['source_sha256'], ROOT)
    cases = json.loads((source/'qa_fixtures.json').read_text(encoding='utf-8'))['questions']
    planned = planned_groups(meta['arguments'], len(cases))
    key = lambda g: (g['trial'],g['variant'],g['context'],g['clients'])
    if sorted(meta['groups'],key=key) != sorted(planned,key=key):
        raise ValueError('Measured groups differ from declared plan')
    rows = [json.loads(line) for line in (run/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    validate_rows(rows, planned)
    if len(rows) != meta['requests']:
        raise ValueError('Request count mismatch')
    prompts = {}
    workloads = {}
    for trial in range(meta['arguments']['trials']):
        items = cases*meta['arguments']['repetitions']
        random.Random(10400+trial).shuffle(items)
        workloads[trial] = items
    for row in rows:
        case = workloads[row['trial']][row['job_index']]
        if (row['question_id'],row['question']) != (case['id'],case['question']):
            raise ValueError('Unexpected workload item')
        if row['status'] != 'ok':
            continue
        prompt_key = (row['trial'],row['context'],row['job_index'])
        if prompt_key in prompts and prompts[prompt_key] != row['input_sha256']:
            raise ValueError('Input mismatch across methods or client counts')
        prompts[prompt_key] = row['input_sha256']
        if row['model_variant'] != 'cuda_eager_bf16':
            raise ValueError('Unexpected model variant')
        if row['variant'] != 'serial' and not 1 <= row['actual_batch_size'] <= int(row['variant'][-1]):
            raise ValueError('Invalid actual batch size')
        if meta['arguments']['fixed_tokens'] and row['output_tokens'] != meta['arguments']['max_new_tokens']:
            raise ValueError('Fixed token count mismatch')
        if check_answer(case,row['answer'])['fact_check_pass'] != row['fact_check_pass']:
            raise ValueError('Keyword grade mismatch')
    return meta, rows


def main():
    from bench_utils import environment, write_json, write_csv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--repetitions', type=int, default=2)
    parser.add_argument('--clients', type=int, nargs='+', default=[1,2,4])
    parser.add_argument('--methods', choices=METHODS, nargs='+', default=list(METHODS))
    parser.add_argument('--max-new-tokens', type=int, default=96)
    parser.add_argument('--fixed-tokens', action='store_true')
    parser.add_argument('--wait-ms', type=float, default=10)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        _, rows = verify(args.output)
        print(f'Verified {len(rows)} HTTP requests and identical unpadded inputs across methods')
        return
    import math
    kb = KnowledgeBase()
    if (args.output.exists() or args.trials < 1 or args.repetitions < 1
            or not 1 <= args.max_new_tokens <= 256 or not math.isfinite(args.wait_ms) or args.wait_ms < 0
            or not all(1 <= c <= len(kb.questions)*args.repetitions for c in args.clients)
            or len(set(args.clients)) != len(args.clients) or len(set(args.methods)) != len(args.methods)):
        parser.error('New output directory, unique settings, and positive valid workload dimensions required')
    files = ('qa_batch_benchmark.py','qa_batch.py','qa_load.py','qa_app.py','qa_benchmark.py',
             'qa_evidence.py','qa_fixtures.json','qa_ui.html','bench_utils.py')
    args.output.mkdir(parents=True)
    meta = dict(schema='qa-microbatch-v1',started_utc=datetime.now(timezone.utc).isoformat(),model=MODEL,revision=REVISION,
                arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
                source_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},
                packages={n:importlib.metadata.version(n) for n in ('torch','transformers','numpy','safetensors')},
                protocol='Closed-loop HTTP clients; barrier release; identical shuffled six-question workload for all methods/client counts per trial. Fresh model per method/trial; seeded method and group order. Eager BF16 throughout. Serial is original Engine; batch1 controls adapter overhead; batch2/4 coalesce compatible requests for up to wait_ms. Static batches, left padding, no answer cache. One warm group per context with six jobs and up to four clients, excluded from measured data; model load excluded. Source snapshots are exact bytes.',
                timing='First nonempty HTTP text and full done-event latency include queue and coalescing. Batch done events wait for longest member. Queue includes coalescing wait. Retrieval, tokenization, generation and memory metrics are shared batch-level measurements, not additive per request. Throughput includes full finite group duration, not production capacity. P95 descriptive only.',
                quality='Six existing regression questions, not independent evaluation. Token identity measured separately from keyword checks. Natural-length output can change with batch shape. Fixed-token controls intentionally disable EOS and must not be used to score answer quality.',
                groups=[],loads=[],warmup_requests=0)
    snapshot_sources(args.output,meta['source_sha256'],ROOT)
    write_json(args.output/'metadata.json',meta)
    all_rows, summaries = [], []
    for trial in range(args.trials):
        methods = list(args.methods)
        random.Random(4100+trial).shuffle(methods)
        cases = kb.questions*args.repetitions
        random.Random(10400+trial).shuffle(cases)
        for method in methods:
            print(f'Load trial={trial} method={method}',flush=True)
            engine = (Engine('cuda_eager_bf16',local_files_only=True,threads=4) if method == 'serial'
                      else BatchEngine(max_batch=int(method[-1]),wait_ms=args.wait_ms,local_files_only=True,threads=4))
            meta['environment'] = environment()
            meta['loads'].append(dict(trial=trial,method=method,seconds=engine.load_seconds))
            server = make_server(engine)
            thread = threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            def payload(case,context):
                return dict(question=case['question'],context=context,max_new_tokens=args.max_new_tokens,
                            fixed_tokens=args.fixed_tokens)
            try:
                for context in ('short','long'):
                    warm, _ = run_clients(url,[payload(c,context) for c in kb.questions],min(4,len(kb.questions)))
                    meta['warmup_requests'] += len(warm)
                    if any(r['status'] != 'ok' for r in warm):
                        write_json(args.output/f'failed-warmup-{trial}-{method}-{context}.json',warm)
                        raise RuntimeError('Warmup failed; failure data saved')
                groups = [(c,n) for c in ('short','long') for n in args.clients]
                random.Random(6100+trial).shuffle(groups)
                for context, clients in groups:
                    group = dict(trial=trial,variant=method,context=context,clients=clients,jobs=len(cases))
                    meta['groups'].append(group)
                    write_json(args.output/'metadata.json',meta)
                    rows,duration = run_clients(url,[payload(c,context) for c in cases],clients)
                    for row in rows:
                        case = cases[row['job_index']]
                        row['model_variant'] = row.get('variant')
                        row.update(group,question_id=case['id'],question=case['question'])
                        if row['status'] == 'ok':
                            row.update(check_answer(case,row['answer']))
                        with (args.output/'requests.jsonl').open('a',encoding='utf-8') as stream:
                            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                    all_rows.extend(rows)
                    summary = dict(group,**summarize_load(rows,duration))
                    summaries.append(summary)
                    print(json.dumps(summary),flush=True)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
                engine.close()
    validate_rows(all_rows,meta['groups'])
    meta.update(completed_utc=datetime.now(timezone.utc).isoformat(),requests=len(all_rows))
    write_json(args.output/'metadata.json',meta)
    verify(args.output)
    write_csv(args.output/'groups.csv',summaries)
    print(f'Complete: {len(all_rows)} measured HTTP requests; {meta["warmup_requests"]} excluded warmups',flush=True)


if __name__ == '__main__':
    main()
