# 小批量文档问答实验

上轮测到 4 个并发用户主要在单推理线程前排队。本实验保持相同 Qwen2.5-1.5B 权重、检索器、提示词和 eager BF16 精度，将等待中的兼容请求合成最多 2 或 4 条，一次调用 `generate`。

这是独立实验入口。原 `qa_app.py` 默认行为保持现状。

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
python qa_batch.py --local-files-only --max-batch 4 --wait-ms 10 --port 8766
```

模型须先按 [原应用说明](QA_TESTING.md) 下载。新入口固定使用本机已验证的 GPU eager BF16。当前只支持 1–4 条静态合批，支持不同长度的左填充输入；最大生成长度、固定长度开关、回答策略必须一致才合批。等待窗口至多 10 ms（可调整），实际排队可能更长。批量大小 1 不等待凑批，用于检查新入口本身的开销。

每条请求独立流式解码，记录包含 EOS 的 token 序列，过滤该行结束后的填充，并对照模型实际返回的 token。所有请求的 `done` 保守地等到整批生成结束才发送，因此短答案会等待同批的长答案；这不是 continuous batching。`post_eos_wait_ms` 记录这部分等待。显存、检索、分词和生成时间是共享的整批测量，不能按行求和。

## 完整 HTTP 对照

```powershell
python qa_batch_benchmark.py --output results/my-microbatch --trials 3 --clients 1 2 4
python qa_batch_benchmark.py --output results/my-microbatch-fixed --trials 3 --clients 4 --fixed-tokens --max-new-tokens 64
python qa_batch_benchmark.py --output results/my-microbatch --verify-only
python analyze_qa_batch.py --run results/my-microbatch
```

原串行服务、batch1、batch2、batch4 共四种方法；每轮随机化方法和负载组顺序；每组对相同顺序的 12 次请求测量，使用原来的六道回归题。每个方法/轮次重新加载模型，先排除 12 次预热请求。每个客户端等待上一条完成后再发下一条，计时从 HTTP 客户端开始，覆盖检索、排队、分词、生成、解码和流式传输。模型下载、加载、预热不计入延迟。

自然回答统计用户体验，但批量形状可能改变浮点计算及输出长度；固定 token 对照用于区分这项干扰，不用于回答质量打分。保留每条输入哈希、完整答案、输出 token、分组耗时、环境版本及测量源码快照。`--verify-only` 可以在没有 GPU/模型的环境下核验请求完整性、相同输入、固定输出长度和来源哈希。

六道回归题不能代表业务正确率；长资料缺失价格题原本存在幻觉。合批不能据此宣称更准确，也不能将有限闭环吞吐量当作生产服务容量。
