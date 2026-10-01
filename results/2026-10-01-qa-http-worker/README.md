# 本机中文文档问答：完整 HTTP 应用测试

固定推理线程；Qwen2.5-1.5B-Instruct；CPU 4 线程；3 轮；168 次正式请求。模型加载和预热不计入请求延迟。

[先看面向实际使用的结论](FINDINGS.md) · [回答原文复核](answer_review.json) · [实际后端检查](backend_inspection.json)

## 自然回答：用户等待时间

下表为各问题混合后的请求中位数；同一栏使用相同题目。输出长度可能不同，需结合固定长度对照。短资料为检索到的两篇，长资料为全部六篇。

| 配置 | 资料 | 首段文字 ms | 总耗时 ms | 总耗时 P95 ms | 输入 token | 输出 token | 每题三轮均通过关键词检查 |
|---|---|---:|---:|---:|---|---|---|
| cpu_eager_fp32 | long | 13004.4 | 19826.9 | 22216.2 | 979–991 | 15–32 | 5/6 |
| cpu_eager_fp32 | short | 5117.1 | 10511.8 | 14657.4 | 370–403 | 5–35 | 6/6 |
| cuda_cudnn_bf16 | long | 395.5 | 1273.7 | 9566.5 | 979–991 | 15–32 | 5/6 |
| cuda_cudnn_bf16 | short | 341.3 | 2563.6 | 7220.8 | 370–403 | 5–35 | 6/6 |
| cuda_eager_bf16 | long | 133.8 | 947.8 | 1405.4 | 979–991 | 16–32 | 5/6 |
| cuda_eager_bf16 | short | 50.5 | 768.0 | 1690.1 | 370–403 | 3–35 | 6/6 |
| cuda_sdpa_bf16 | long | 163.9 | 1019.7 | 1499.5 | 979–991 | 15–32 | 5/6 |
| cuda_sdpa_bf16 | short | 58.8 | 845.6 | 1346.0 | 370–403 | 5–35 | 6/6 |

## 固定输出长度控制

每次强制 64 token，只有价格题，每种资料长度 3 次。样本少，P95 接近最大值；生成内容不纳入答案质量评估。

| 配置 | 资料 | 首段文字 ms | 完成 ms | 完成 P95 ms |
|---|---|---:|---:|---:|
| cpu_eager_fp32 | long | 13080.5 | 31693.2 | 31944.4 |
| cpu_eager_fp32 | short | 5341.9 | 22492.5 | 22534.8 |
| cuda_cudnn_bf16 | long | 89.9 | 9851.8 | 9904.1 |
| cuda_cudnn_bf16 | short | 62.5 | 15081.4 | 16503.8 |
| cuda_eager_bf16 | long | 129.9 | 2613.9 | 2664.8 |
| cuda_eager_bf16 | short | 57.9 | 2470.6 | 2518.1 |
| cuda_sdpa_bf16 | long | 157.6 | 2594.2 | 2814.4 |
| cuda_sdpa_bf16 | short | 57.9 | 2383.7 | 2670.5 |

## 显存

PyTorch allocator 峰值，不能等同于整机显存。下表为自然回答中最坏一次；CPU 未测显存，留空。

| 配置 | 资料 | 含模型峰值 MiB | 请求峰值增量 MiB |
|---|---|---:|---:|
| cuda_cudnn_bf16 | long | 3044.71 | 90.29 |
| cuda_cudnn_bf16 | short | 2993.30 | 38.89 |
| cuda_eager_bf16 | long | 3113.84 | 159.42 |
| cuda_eager_bf16 | short | 2997.33 | 42.92 |
| cuda_sdpa_bf16 | long | 3124.10 | 169.68 |
| cuda_sdpa_bf16 | short | 3000.88 | 46.47 |

## 原始证据与复现

- [逐次请求](requests.jsonl)：完整回答、token ID、计时、显存与关键词检查。
- [回答原文](answers.md)：按配置与问题整理，方便人工核对。
- [汇总](summary.csv)、[配对比较](paired_comparisons.csv)、[配对汇总](paired_summary.csv)。
- [环境、模型版本、执行顺序、加载耗时与源码哈希](metadata.json)。
- [应用运行方式、计时边界与验收局限](../../QA_TESTING.md)。
- [预检失败方案](../2026-10-01-qa-preflight/README.md)：FP16 eager 与三种动态 INT8 方案。

```powershell
python qa_benchmark.py --output results/my-qa-run --trials 3 --local-files-only
python summarize_qa.py --run results/my-qa-run
```

本次只有六道独立题，短长资料各测一次并重复三轮；不能称为 144 道独立题。结果不含公网延迟或浏览器绘制，也没有验证多人并发或生产 SLA。自然回答质量需结合原文人工核对；错误回答不能因为较快而算作可部署优化。

测量在 Windows 笔记本桌面环境进行，未锁定 GPU 时钟或隔离全部后台负载。三轮数据属于本机描述统计，不是严格的跨硬件排名或置信区间。CPU FP32 与 GPU BF16 的差别同时包含设备和精度变化；不能把它们的总速度差归因于注意力优化。
