"""Paired speed ratios with trial-cluster bootstrap for repeated application runs."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
from qa_benchmark import paired_comparisons
from summarize_qa import validate


def paired_statistics(pairs):
    if not pairs:
        raise ValueError('No pairs')
    trials=sorted({p['trial'] for p in pairs})
    logmeans=[statistics.mean(math.log(p['total_speedup']) for p in pairs if p['trial']==trial) for trial in trials]
    rng=random.Random(20261003)
    boot=sorted(math.exp(statistics.mean(rng.choices(logmeans,k=len(logmeans)))) for _ in range(10000))
    ratios=[p['total_speedup'] for p in pairs]
    return dict(pairs=len(pairs),trials=len(trials),geometric_mean_speedup=math.exp(statistics.mean(logmeans)),
                median_paired_speedup=statistics.median(ratios),min_paired_speedup=min(ratios),max_paired_speedup=max(ratios),
                bootstrap_trial_95_low=boot[249],bootstrap_trial_95_high=boot[9749],
                candidate_faster_pairs=sum(x>1 for x in ratios),
                identical_outputs=sum(p['same_output_tokens'] for p in pairs))


def main():
    from bench_utils import write_csv,write_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    meta,rows=validate(args.run)
    pairs=paired_comparisons(rows)
    summaries=[]
    for baseline,candidate,context,mode in sorted({(p['baseline'],p['candidate'],p['context'],p['mode']) for p in pairs}):
        chosen=[p for p in pairs if (p['baseline'],p['candidate'],p['context'],p['mode'])==(baseline,candidate,context,mode)]
        summaries.append(dict(baseline=baseline,candidate=candidate,context=context,mode=mode,**paired_statistics(chosen)))
    write_csv(args.run/'paired_uncertainty.csv',summaries)
    natural=[r for r in rows if r['mode']=='natural']
    inventory=[]
    for variant,context,case in sorted({(r['variant'],r['context'],r['question_id']) for r in natural}):
        chosen=[r for r in natural if (r['variant'],r['context'],r['question_id'])==(variant,context,case)]
        inventory.append(dict(variant=variant,context=context,question_id=case,requests=len(chosen),
                              unique_token_sequences=len({tuple(r['output_token_ids']) for r in chosen}),
                              all_fact_checks_pass=all(r['fact_check_pass'] for r in chosen)))
    write_csv(args.run/'answer_stability.csv',inventory)
    write_json(args.run/'analysis_metadata.json',dict(
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        request_sha256=hashlib.sha256((args.run/'requests.jsonl').read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        request_hash_newlines='LF',bootstrap='10000 draws, seed 20261003, resample entire trial log-mean paired ratios, percentile 2.5/97.5%. Ratio >1 favors candidate. Conditional on this one machine/day/workload; small trial count and uncontrolled clock/background activity limit interpretation. Natural outputs can differ, so only fixed-token rows control output count.',
        completed_requests=len(rows),distinct_questions=len({r['question_id'] for r in natural}),
        source_run_completed=meta['completed_utc']))
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':
    main()
