"""Recompute microbatch summaries and paired output differences from raw requests."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from bench_utils import write_csv, write_json
from qa_batch_benchmark import verify
from qa_evidence import snapshot_sources, source_directory
from qa_load import summarize_load


def lf_sha256(path):
    """Git normalizes text evidence; hash the explicitly canonical LF form."""
    return hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def analyze(run):
    meta, rows = verify(run)
    fixed = meta['arguments']['fixed_tokens']
    grouped = {}
    for row in rows:
        grouped.setdefault((row['context'],row['clients'],row['variant']),[]).append(row)
    baselines = {(r['trial'],r['context'],r['clients'],r['job_index']):r
                 for r in rows if r['variant'] == 'serial' and r['status'] == 'ok'}
    summaries, changes = [], []
    for (context,clients,method), values in sorted(grouped.items()):
        by_trial = {}
        for row in values:
            by_trial.setdefault(row['trial'],[]).append(row)
        duration = sum(max(r['client_end_offset_ms'] for r in part) for part in by_trial.values())
        summary = dict(context=context,clients=clients,method=method,**summarize_load(values,duration))
        good = [r for r in values if r['status'] == 'ok']
        matched, changed, changed_text = 0, 0, 0
        for row in good:
            reference = baselines.get((row['trial'],context,clients,row['job_index']))
            if reference is None:
                continue
            matched += 1
            changed_text += reference['answer'] != row['answer']
            if reference['output_token_ids'] != row['output_token_ids']:
                changed += 1
                changes.append(dict(trial=row['trial'],context=context,clients=clients,method=method,
                                    job_index=row['job_index'],question_id=row['question_id'],
                                    actual_batch_size=row.get('actual_batch_size',1),
                                    reference_answer=reference['answer'],answer=row['answer'],
                                    reference_tokens=reference['output_tokens'],output_tokens=row['output_tokens'],
                                    reference_keyword_pass=None if fixed else reference['fact_check_pass'],
                                    keyword_pass=None if fixed else row['fact_check_pass']))
        ratios = []
        for trial, part in sorted(by_trial.items()):
            reference = [r for r in rows if r['trial'] == trial and r['context'] == context
                         and r['clients'] == clients and r['variant'] == 'serial']
            if reference and all(r['status'] == 'ok' for r in part+reference):
                ratios.append(max(r['client_end_offset_ms'] for r in reference) /
                              max(r['client_end_offset_ms'] for r in part))
        summary.update(matched_serial_outputs=matched,changed_output_tokens=changed,changed_answer_text=changed_text,
                       keyword_passes=None if fixed else sum(r['fact_check_pass'] for r in good),
                       output_tokens_median=statistics.median(r['output_tokens'] for r in good) if good else None,
                       peak_allocated_mib=max((r['peak_allocated_mib'] for r in good),default=None),
                       observed_batch_sizes=dict(Counter(r.get('actual_batch_size',1) for r in good)),
                       paired_throughput_ratios=ratios,
                       post_eos_wait_ms_median=statistics.median(r.get('post_eos_wait_ms',0) for r in good) if good else None)
        summaries.append(summary)
    root = Path(__file__).resolve().parent
    files = ('analyze_qa_batch.py','qa_batch_benchmark.py','qa_batch.py','qa_load.py','qa_app.py',
             'qa_benchmark.py','qa_evidence.py','bench_utils.py')
    hashes = {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}
    digest = hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:16]
    archive = run/'analysis-sources'/digest
    if archive.exists():
        source_directory(archive,hashes,root)
    else:
        archive.mkdir(parents=True)
        snapshot_sources(archive,hashes,root)
    result = dict(schema='qa-microbatch-analysis-v1',source_run=str(run),requests=len(rows),
                  input_lf_sha256={n:lf_sha256(run/n) for n in ('metadata.json','requests.jsonl')},
                  analysis_source_sha256=hashes,analysis_source_directory=archive.relative_to(run).as_posix(),
                  aggregation='Pooled request latency median/nearest-rank P95 across all trials. Throughput=sum completed/sum full group durations. Ratios pair full group duration to serial in the same trial/context/client count; three ratios are descriptive, not a confidence interval. Keyword pass counts do not establish semantic correctness.',
                  fixed_tokens=fixed,summaries=summaries)
    write_json(run/'analysis.json',result)
    write_csv(run/'comparison.csv',summaries)
    write_json(run/'answer_changes.json',changes)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args = parser.parse_args()
    result = analyze(args.run)
    print(f"Recomputed {len(result['summaries'])} summaries from {result['requests']} requests")


if __name__ == '__main__':
    main()
