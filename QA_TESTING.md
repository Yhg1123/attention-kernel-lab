# 本地文档问答：完整请求测试

新增 [32 道题 / 128 次 HTTP 请求的扩展质量验收](QA_QUALITY.md)：保留开发集、预留集、否定词误判、完整回答和逐条复核。加强提示词未通过改进验收，仍为实验选项。

本应用把前面的算子实验放进实际问答流程：浏览器/HTTP 请求 → 本地文档检索 → 提示词分词 → 模型生成与 KV cache → 解码 → 流式返回。无需 AI API、访问密钥或付费服务。

已完成的三轮结果：[用户等待时间与实际结论](results/2026-10-01-qa-http-worker/FINDINGS.md) · [完整统计表](results/2026-10-01-qa-http-worker/README.md)。

## 启动演示

先安装适合设备的 PyTorch。RTX 5070 使用 `requirements-cu128.txt`；在同一 Python 环境安装 `pip install -r requirements-qa.txt`。

```powershell
python qa_app.py --variant cuda_sdpa_bf16 --port 8765
```

浏览器打开 `http://127.0.0.1:8765`。首次运行自动下载公开模型，之后可加 `--local-files-only` 完全离线运行。模型固定为 [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/tree/989aa7980e4cf806f80c7fef2b1adb7bc71aa306)，revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`，Apache-2.0。不执行远程模型代码。模型权重留在本机 Hugging Face 缓存，不上传仓库。

本机共享环境可使用 `..\.venv\Scripts\python.exe` 替代上述 `python`。

## 四种配置与公平比较

| 配置 | 用途 | 与对应基线的差别 |
|---|---|---|
| `cuda_eager_bf16` | 注意力实验的应用基线 | GPU、BF16、普通 eager 注意力 |
| `cuda_sdpa_bf16` | 注意力候选 | 同一模型、精度和输入，换成 Transformers/PyTorch SDPA 自动分派 |
| `cuda_cudnn_bf16` | 强制后端候选 | 同一模型和 BF16，在生成期间只允许 cuDNN SDPA |
| `cpu_eager_fp32` | 线性量化实验的应用基线 | CPU、FP32、eager 注意力 |

SDPA 的内部实现由 PyTorch 选择，不能把名称直接解释为 Flash。Qwen 使用 GQA，本应用不套用之前仅测过特定 Q/K/V 形状的 `MeasuredAttention` 策略。CPU 与 GPU 的速度差也不能归因于某一个算子。

还可以显式选择 `cuda_eager_fp16`、`cuda_sdpa_fp16`、`cpu_eager_int8`、`cpu_eager_int8_mlp`、`cpu_eager_int8_mlp_per_channel`。后三者分别量化所有 Linear、只量化 MLP Linear、对 MLP 使用逐输出通道权重量化；未量化的层保持 FP32。初步验收发现 FP16 eager 输出异常、这三种 INT8 配置均在简单价格题上严重跑题，因此没有进入默认正式配置。失败记录保留在[预检证据](results/2026-10-01-qa-preflight/README.md)中。任何出现无效 logits 的配置都会终止该请求并返回错误，不继续输出假答案。最小输出长度对 EOS 的 `-inf` 屏蔽属于正常生成逻辑，不会被误判为模型故障。

应用一次加载一种配置，避免在笔记本上同时保留多份模型。HTTP 线程把请求提交给固定推理线程，推理线程在请求之间持续存在；这允许后端复用线程相关的初始化和形状缓存。每轮随机排列配置顺序，每个配置完成全部问题；同轮的问题顺序在不同配置中一致。三轮重新加载配置、预热短长资料各一次（各生成 16 token）。冷启动耗时单独记录，未算进已启动服务的请求延迟。此前没见过的序列长度仍可能触发后端初始化，这部分真实请求开销保留在计时中。

## 正式测试

```powershell
python qa_benchmark.py --output results/my-qa-run --trials 3 --local-files-only
```

输出目录必须为空，以防覆盖既有实验。默认 6 道题 × 2 种资料长度 × 4 种配置 × 3 轮 = **144 次自然回答请求**，另加 **24 次固定 64 token 请求**。每个配置每轮有 2 次单独预热。

- 短资料：BM25 检索前两篇完整文档；长资料：全部六篇，检索前两篇放在开头。无答案注入或提示词裁剪。自动校验同一比较的提示词 token ID 哈希一致。
- 自然回答：贪心解码、KV cache、最多 96 个新 token，正常 EOS 结束。保留完整答案、token ID 和截断标记。
- 输出 token 数含自然停止时的 EOS，不等于页面上的中文字数。
- 固定长度：强制输出 64 token，控制“答案变短”对总时间的影响。这些输出只评估速度，不计入回答正确性。
- 每次 HTTP 请求从头检索与生成，无回答缓存、无预填充缓存、无对话历史。batch=1，一个顺序请求客户端。

`requests.jsonl` 保存每一次测量；`summary.csv` 保存按配置/资料长度/生成模式汇总的中位数与最近秩 P95；`paired_comparisons.csv` 保存同轮同题的比值与输出一致性。`metadata.json` 保存模型版本、环境、代码/文档哈希、执行顺序、加载耗时。没有 `completed_utc` 的运行属于未完成结果，不能作为完整基准。

每次新运行还会在 `source/` 保存实际采样的源码和文档快照，旧数据不会因为应用升级而失去校验能力。使用 `python summarize_qa.py --run results/2026-10-01-qa-http-worker --verify-only` 可以只校验历史数据，不重写报告。存在快照时必须完整通过哈希检查，不能靠当前代码掩盖缺失或损坏的归档；校验过程不执行历史源码。

## 指标解释与边界

**客户端首段文字时间**从发送 HTTP 请求开始，到收到第一段非空文字为止；它比纯 GPU 首 token 更接近用户等待，但不含浏览器绘制。**总耗时**到收到最终 done 事件，包括 HTTP、检索、分词、数据搬运、生成、解码和流式发送。服务器同时记录首 token、检索和生成时间，以辅助定位瓶颈。HTTP 使用本机回环地址，不包含公网网络延迟。

显存是 PyTorch allocator 的峰值，包括模型的 `peak_allocated_mib` 和相对请求前的增量；它不等于任务管理器或整机总显存。CPU 没有对应显存数值，留空，不记为零。

每一步生成都检查 logits 中的 NaN、正无穷和整行不可选状态；基线和候选都包含这一检查及其同步开销。

题目和文档是原创虚构产品资料，包含事实题、条件判断、跨文档检索和无答案题。关键词检查只能发现部分错误，不能替代语义评估；因此保留完整回答供人工核对。六道题重复三轮仍只有六道独立题，不能称为“144 道题正确率”。自然回答因输出内容/长度不同而产生的速度差需要结合固定长度结果解读。

这是可运行的单用户应用验收和性能实验，不是生产 SLA、并发压测、标准大模型能力评测或任意业务数据的准确率保证。要应用到实际业务，需要换成该业务文档、问题分布、模型和部署框架重新测量。
