"""Closed-loop concurrent HTTP clients against the existing single-worker QA service."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
from queue import Queue, Empty
import random
import statistics
import threading
import time

from qa_app import Engine, KnowledgeBase, MODEL, REVISION, ROOT, check_answer, make_server
from qa_benchmark import request_qa, p95
from qa_evidence import snapshot_sources, source_directory


def run_clients(url, payloads, clients):
    """Each client submits its next request only after the previous response completes."""
    if type(clients) is not int or not 1 <= clients <= len(payloads):
        raise ValueError('clients must be 1..number of jobs; workload must be nonempty')
    pending = Queue()
    for index in range(clients, len(payloads)):
        pending.put(index)
    start = []
    barrier = threading.Barrier(clients + 1, action=lambda: start.append(time.perf_counter()), timeout=30)

    def client(client_id):
        rows = []
        index = client_id
        barrier.wait()
        while True:
            began = time.perf_counter()
            try:
                row = request_qa(url, payloads[index])
                row.pop('event', None)
                row['status'] = 'ok'
            except Exception as exc:
                row = dict(status='error', error=f'{type(exc).__name__}: {exc}')
            row.update(job_index=index, client_id=client_id,
                       client_start_offset_ms=(began-start[0])*1000,
                       client_end_offset_ms=(time.perf_counter()-start[0])*1000)
            rows.append(row)
            try:
                index = pending.get_nowait()
            except Empty:
                break
        return rows

    with ThreadPoolExecutor(max_workers=clients) as pool:
        futures = [pool.submit(client, i) for i in range(clients)]
        barrier.wait()
        rows = [row for future in futures for row in future.result()]
    return sorted(rows, key=lambda row: row['job_index']), max(row['client_end_offset_ms'] for row in rows)


def summarize_load(rows, duration_ms):
    if not rows or not math.isfinite(duration_ms) or duration_ms <= 0:
        raise ValueError('Nonempty workload and positive duration required')
    good = [r for r in rows if r['status'] == 'ok']
    result = dict(attempted=len(rows), completed=len(good), errors=len(rows)-len(good),
                  duration_ms=duration_ms, completed_requests_per_second=len(good)*1000/duration_ms)
    for metric in ('client_first_text_ms', 'client_total_ms', 'queue_ms', 'generation_ms'):
        values = [r[metric] for r in good if r.get(metric) is not None]
        result[metric+'_median'] = statistics.median(values) if values else None
        result[metric+'_p95'] = p95(values) if values else None
    if good and all('output_tokens' in r for r in good):
        result['generated_tokens_per_second'] = sum(r['output_tokens'] for r in good)*1000/duration_ms
    return result


def validate_rows(rows, groups):
    dimensions = ('trial', 'variant', 'context', 'clients')
    expected = {tuple(g[k] for k in dimensions)+(i,) for g in groups for i in range(g['jobs'])}
    observed = [tuple(r[k] for k in dimensions)+(r['job_index'],) for r in rows]
    if len(expected) != sum(g['jobs'] for g in groups) or len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError('Missing, duplicate or unexpected load request/group')
    for row in rows:
        if row['status'] not in ('ok', 'error') or not 0 <= row['client_id'] < row['clients']:
            raise ValueError('Invalid request status or client ID')
        start, end = row['client_start_offset_ms'], row['client_end_offset_ms']
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError('Invalid client interval')
        if row['status'] == 'error':
            if not row.get('error'):
                raise ValueError('Missing failure reason')
            continue
        first, total, queue = (row[k] for k in ('client_first_text_ms','client_total_ms','queue_ms'))
        if not all(math.isfinite(x) for x in (first,total,queue)) or not 0 < first <= total or not 0 <= queue <= total:
            raise ValueError('Invalid request timings')
        if row['output_tokens'] != len(row['output_token_ids']):
            raise ValueError('Output token count mismatch')
    return True


def verify(run):
    meta = json.loads((run/'metadata.json').read_text(encoding='utf-8'))
    if meta.get('schema') != 'qa-load-v1' or not meta.get('completed_utc'):
        raise ValueError('Incomplete load experiment')
    source = source_directory(run, meta['source_sha256'], ROOT)
    fixture = json.loads((source/'qa_fixtures.json').read_text(encoding='utf-8'))
    args = meta['arguments']
    planned = [dict(trial=t,variant=v,context=c,clients=n,jobs=len(fixture['questions'])*args['repetitions'])
               for t in range(args['trials']) for v in args['variants'] for c in ('short','long') for n in args['clients']]
    rows = [json.loads(line) for line in (run/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    validate_rows(rows, planned)
    if sorted(meta['groups'],key=lambda g:(g['trial'],g['variant'],g['context'],g['clients'])) != planned:
        # Compare mappings independent of execution order and CLI variant order.
        key=lambda g:(g['trial'],g['variant'],g['context'],g['clients'])
        if sorted(meta['groups'],key=key) != sorted(planned,key=key):
            raise ValueError('Measured groups differ from the declared experiment')
    if len(rows) != meta['requests']:
        raise ValueError('Request count mismatch')
    inputs, outputs = {}, {}
    for row in rows:
        if row['status'] != 'ok':
            continue
        key = row['trial'], row['variant'], row['context'], row['job_index']
        prompt = row['question_id'], row['question'], row['input_sha256']
        if key in inputs and inputs[key] != prompt:
            raise ValueError('Unequal workload or input across client counts')
        inputs[key] = prompt
        outputs.setdefault(key, set()).add(tuple(row['output_token_ids']))
    return meta, rows, sum(len(values)>1 for values in outputs.values())


def main():
    from bench_utils import environment, write_json, write_csv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--clients', nargs='+', type=int, default=[1,2,4])
    parser.add_argument('--repetitions', type=int, default=2)
    parser.add_argument('--variants', nargs='+', choices=['cuda_eager_bf16','cuda_sdpa_bf16'],
                        default=['cuda_eager_bf16','cuda_sdpa_bf16'])
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        _, rows, changed = verify(args.output)
        print(f'Verified {len(rows)} requests; {changed} workload items changed output across client counts')
        return
    kb = KnowledgeBase()
    if args.output.exists() or args.trials < 1 or args.repetitions < 1 or not all(1 <= c <= len(kb.questions)*args.repetitions for c in args.clients):
        parser.error('New output directory and positive trials/repetitions/client counts fitting workload required')
    if len(set(args.clients)) != len(args.clients) or len(set(args.variants)) != len(args.variants):
        parser.error('Duplicate clients/variants are not allowed')
    files = ('qa_load.py','qa_app.py','qa_benchmark.py','qa_evidence.py','qa_fixtures.json','qa_ui.html','bench_utils.py')
    args.output.mkdir(parents=True)
    meta = dict(schema='qa-load-v1', started_utc=datetime.now(timezone.utc).isoformat(),model=MODEL,revision=REVISION,
                arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
                source_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},
                packages={n:importlib.metadata.version(n) for n in ('torch','transformers','numpy','safetensors')},
                protocol='Closed-loop clients, one outstanding HTTP request per client; first requests barrier-released. Identical shuffled 6-question workload repeated twice by default across client counts. Single persistent inference worker, no batching, no answer cache. Fresh model per variant/trial; warm each question/context once before measured groups. Group order shuffled per trial, variant order shuffled independently. Model load and warmup excluded. Entire group ends before next starts.',
                timing='First nonempty HTTP text; full done-event latency; server queue time; group duration from barrier release to last client return. Throughput=successful requests/full group seconds, including failed request time. Closed-loop finite workload: not an open-loop arrival-rate or production capacity test. P95 is nearest rank, descriptive only.',
                quality='Existing six regression questions, no new independent examples. Keyword checks are preliminary, inspect saved answers. Compare token IDs across client counts. No quality improvement claim.',
                groups=[],loads=[])
    snapshot_sources(args.output,meta['source_sha256'],ROOT)
    write_json(args.output/'metadata.json',meta)
    all_rows, summaries = [], []
    for trial in range(args.trials):
        variants=list(args.variants)
        random.Random(3100+trial).shuffle(variants)
        cases=kb.questions*args.repetitions
        random.Random(7100+trial).shuffle(cases)
        for variant in variants:
            print(f'Load trial={trial} {variant}',flush=True)
            engine=Engine(variant,local_files_only=True,threads=4)
            meta['environment']=environment()
            meta['loads'].append(dict(trial=trial,variant=variant,seconds=engine.load_seconds))
            server=make_server(engine)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                for case in kb.questions:
                    for context in ('short','long'):
                        request_qa(url,dict(question=case['question'],context=context,max_new_tokens=96))
                groups=[(context,c) for context in ('short','long') for c in args.clients]
                random.Random(9100+trial).shuffle(groups)
                for context,clients in groups:
                    group=dict(trial=trial,variant=variant,context=context,clients=clients,jobs=len(cases))
                    meta['groups'].append(group)
                    write_json(args.output/'metadata.json',meta)
                    rows,duration=run_clients(url,[dict(question=c['question'],context=context,max_new_tokens=96) for c in cases],clients)
                    for row in rows:
                        case=cases[row['job_index']]
                        row.update(group,question_id=case['id'],question=case['question'])
                        if row['status']=='ok':
                            row.update(check_answer(case,row['answer']))
                        with (args.output/'requests.jsonl').open('a',encoding='utf-8') as stream:
                            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
                    all_rows.extend(rows)
                    summary=dict(group,**summarize_load(rows,duration))
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
    print(f'Complete: {len(all_rows)} requests',flush=True)


if __name__=='__main__':
    main()
