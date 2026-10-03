"""Verify concurrent QA evidence and report queue/latency/throughput separately."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from qa_load import verify,summarize_load


def main():
    from bench_utils import write_csv,write_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args()
    meta,rows,changed=verify(args.run)
    groups=[]
    for group in meta['groups']:
        selected=[r for r in rows if all(r[k]==group[k] for k in ('trial','variant','context','clients'))]
        duration=max(r['client_end_offset_ms'] for r in selected)
        groups.append(dict(group,**summarize_load(selected,duration)))
    write_csv(args.run/'groups.csv',groups)
    summary=[]
    for variant,context,clients in sorted({(r['variant'],r['context'],r['clients']) for r in rows}):
        selected=[r for r in rows if (r['variant'],r['context'],r['clients'])==(variant,context,clients)]
        measured=[g for g in groups if (g['variant'],g['context'],g['clients'])==(variant,context,clients)]
        result=dict(variant=variant,context=context,clients=clients,trials=len(measured),
                    **summarize_load(selected,sum(g['duration_ms'] for g in measured)))
        result['trial_throughput_min']=min(g['completed_requests_per_second'] for g in measured)
        result['trial_throughput_max']=max(g['completed_requests_per_second'] for g in measured)
        result['trial_total_median_min']=min(g['client_total_ms_median'] for g in measured if g['completed'])
        result['trial_total_median_max']=max(g['client_total_ms_median'] for g in measured if g['completed'])
        summary.append(result)
    write_csv(args.run/'load_summary.csv',summary)
    baseline={(r['trial'],r['variant'],r['context'],r['job_index']):r for r in rows if r['clients']==1 and r['status']=='ok'}
    pairs=[]
    for row in rows:
        key=row['trial'],row['variant'],row['context'],row['job_index']
        if row['clients']==1 or row['status']!='ok' or key not in baseline:
            continue
        base=baseline[key]
        if base['input_sha256']!=row['input_sha256']:
            raise ValueError('Load comparison has unequal prompt')
        pairs.append(dict(trial=row['trial'],variant=row['variant'],context=row['context'],
                          clients=row['clients'],job_index=row['job_index'],question_id=row['question_id'],
                          identical_output=base['output_token_ids']==row['output_token_ids'],
                          total_latency_multiplier=row['client_total_ms']/base['client_total_ms']))
    write_csv(args.run/'concurrency_pairs.csv',pairs)
    answers=[]
    for variant,context,question in sorted({(r['variant'],r['context'],r['question_id']) for r in rows if r['status']=='ok'}):
        chosen=[r for r in rows if r['status']=='ok' and (r['variant'],r['context'],r['question_id'])==(variant,context,question)]
        for answer in sorted({r['answer'] for r in chosen}):
            answers.append(dict(variant=variant,context=context,question_id=question,answer=answer,
                                occurrences=sum(r['answer']==answer for r in chosen)))
    write_json(args.run/'answer_inventory.json',answers)
    write_json(args.run/'verification.json',dict(completed_requests=sum(r['status']=='ok' for r in rows),
        attempted_requests=len(rows),errors=sum(r['status']=='error' for r in rows),
        expected_group_count=len(meta['groups']),paired_requests=len(pairs),changed_output_items=changed,
        analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        request_sha256_lf=hashlib.sha256((args.run/'requests.jsonl').read_bytes().replace(b'\r\n',b'\n')).hexdigest()))
    report=['# 本地问答并发测试：用户在等模型还是等队列？','',
            f"{len(rows)} 次测量请求，{len(meta['groups'])} 个独立测量组；每组 12 个请求（6 道原有回归题各两次），1/2/4 个闭环客户端，2 种 BF16 实现、短/长资料、各 3 轮。",'',
            '## 等待时间与吞吐量','',
            '每行 36 次请求，延迟是三轮请求合并后的中位数，P95 为 nearest-rank；吞吐量是全部成功请求 / 三轮测量组总秒数，包含失败请求花费的时间。原始每轮范围见 load_summary.csv；每行只有三轮，不能当作生产 SLA。','',
            '| 后端 | 资料 | 客户端 | 首段文字 ms | 完整回答 ms | 完整回答 P95 ms | 排队 ms | 请求/秒 | 错误 |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        report.append(f"| {r['variant']} | {r['context']} | {r['clients']} | {r['client_first_text_ms_median']:.1f} | {r['client_total_ms_median']:.1f} | {r['client_total_ms_p95']:.1f} | {r['queue_ms_median']:.1f} | {r['completed_requests_per_second']:.3f} | {r['errors']} |")
    report+=['','## 测试边界','',
        '- 同一服务持久单推理线程，HTTP 可并发接受请求，但模型逐个处理，没有动态批处理。多个客户端增加的是在途请求和队列，不代表多份模型同时计算。',
        '- 每个客户端收到完整响应后立即提交下一个问题；首次请求由 barrier 同时释放。有限 12 请求任务有启动与排空阶段，不是固定到达率的持续压力测试，也没有测到过载临界点。',
        '- 每个后端/轮次重新加载，先把每道题的短/长资料各预热一次；模型加载和预热不计入数据。每个测量组结束后才开始下一组，未与其他 GPU 实验同时运行。',
        '- 同一轮三种并发数使用相同问题列表、资料和输入 token；不同问题的服务时间并不相同，排队顺序与操作系统调度有关。无答案缓存。',
        f'- 跨并发数的 {len(pairs)} 对已完成请求逐一核验输入；发生 token 序列变化的 workload item 数为 {changed}。答案全文见 answer_inventory.json。',
        '- 本轮新增的是负载数据，独立题仍只有 6 道。关键词检查只作回归初筛；已知长资料企业版年费编造问题不能被正常完成或低延迟掩盖。',
        '- 网络为本机 loopback；不包含互联网、浏览器绘制、认证、实际文档上传或长期运行。Windows 笔记本时钟和后台进程未完全隔离。','',
        '## 复现','',
        '```powershell','python qa_load.py --output results/my-load --trials 3',
        'python qa_load.py --output results/my-load --verify-only','python summarize_qa_load.py --run results/my-load','```','',
        '已有缓存模型和 QA 依赖即可运行，输出目录必须不存在。metadata 记录版本、执行顺序、环境、源码哈希；source 保存实际执行版本。requests.jsonl 保留失败、完整答案、排队时间和每个客户端开始/结束偏移，groups.csv 保留每组吞吐量。']
    (args.run/'README.md').write_bytes(('\n'.join(report)+'\n').encode())
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
