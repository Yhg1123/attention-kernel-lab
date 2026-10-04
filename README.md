# Attention Kernel Lab | 注意力算子性能实验

An evidence based comparison of causal attention implementations on 4 GB and 8 GB laptop GPUs. This project measures **latency, temporary PyTorch memory, numerical error, and backend availability** together. It also includes a constraint based selector that chooses only among configurations actually measured on this machine.

这是一个可复现的注意力算子实验，不是自研 CUDA Kernel。项目比较 PyTorch eager 实现、`scaled_dot_product_attention` 自动选择、Math、Flash、Memory Efficient 和 cuDNN 后端，并记录每种输入规模下的性能、误差和支持情况。

## 完整中文问答应用（2026-10-01）

2026-10-04：[864 次完整 HTTP 小批量实验](results/2026-10-04-qa-microbatch/INTERPRETATION.md)。4 人并发时，batch4 的短/长资料吞吐量为原服务的 **1.41× / 2.21×**，完整回答中位数 **2.10 → 1.46 秒 / 3.45 → 1.59 秒**；单人没有同等收益，18 次回答发生变化，已有幻觉仍未解决。[运行批量实验](QA_BATCHING.md)

2026-10-03：[1/2/4 客户端、432 次并发请求](results/2026-10-03-qa-load/INTERPRETATION.md)补齐排队数据。eager BF16 短资料从 1 人到 4 人，完整回答中位数从 0.73 秒增至 2.37 秒，吞吐量约 1.46–1.52 请求/秒；当前单推理线程主要让请求排队。

2026-10-03：[10 轮 / 280 次请求复测](results/2026-10-03-qa-repeat-128/INTERPRETATION.md)，固定输出扩大到 128 token；短/长资料的配对加速比分别为 1.002× / 0.977×，重采样区间均跨过 1，仍未证明 SDPA 能稳定加速完整问答。

2026-10-02：[扩展质量验收](QA_QUALITY.md)完成 32 道题、128 次 HTTP 请求，修正了“答反却通过”的关键词检查漏洞，保留所有原始结果和事后复核。加强提示词没有解决事实错误，不能当成可靠性改进部署。

新增无需 AI API 的本地文档问答演示：网页提问、BM25 检索、固定版本 Qwen2.5-1.5B 模型、KV cache 生成和流式回答。测试从 HTTP 请求开始计时，记录首段文字、整段回答、显存和完整答案，并用固定输出长度排除回答长短的干扰。

[启动演示与测试方法](QA_TESTING.md) · [正式应用测试报告](results/2026-10-01-qa-http-worker/README.md) · [失败配置及预检记录](results/2026-10-01-qa-preflight/README.md)

三轮共完成 168 次请求。短资料自然回答的中位数：CPU FP32 **10.512 秒**，GPU BF16 eager **0.768 秒**；这是设备和精度同时变化的收益。只更换 GPU 注意力实现没有得到明显、稳定的提速；固定 64 token 时，SDPA 与 eager 的中位数差约 0.8–3.5%。短资料六题通过，长资料的无答案题仍编造价格。[面向实际使用的结论](results/2026-10-01-qa-http-worker/FINDINGS.md)

## 应用化扩展（2026-10-01）

新增 prefill / 单 token KV-cache decode 的多形状、三种随机种子 profile，逐请求同步墙钟计时、P95、原始样本和约束策略导出，并提供带环境/源码/形状检查的 `MeasuredAttention` 调用接口。

本机 batch=4、长度 2048、FP16 的 prefill 中，cuDNN 相对 eager 的三轮中位数比值为 **16.21×**，操作峰值增量 **264 → 4.001 MiB**；对应单 token decode 的收益约 **1.18×**。两类工作负载需要分开选型。

[应用方式与代码示例](APPLICATIONS.md) · [完整负载实验](results/2026-10-01-workloads/README.md)

## 核心问题

1. 在小显存 GPU 上，融合注意力后端能否同时降低延迟和临时显存？
2. FP16 相对 FP32 参考输出的误差是多少？
3. 后端支持是否随数据类型变化？性能最快的选项是否随序列长度变化？

## 实验设计

| 项目 | 设置 |
| --- | --- |
| 输入 | `Q,K,V`，形状 `[batch=1, heads=4, sequence, head_dim=64]` |
| 序列长度 | 128、256、512、1024 |
| 任务 | 推理，causal mask，dropout=0 |
| 精度 | CUDA: FP32、FP16；CPU: FP32 |
| 基线 | `QKᵀ / √d → causal mask → softmax → V`，PyTorch eager |
| 参考输出 | 同一组原始随机输入的 FP32 eager 输出；随机种子 2026 |
| 计时 | 预热 50 次，每个配置计时 100 次；CUDA Event / CPU 墙钟时间，取中位数 |
| 显存 | 输入已分配后，PyTorch allocator 的峰值增量，包括输出和临时张量 |
| 数值 | 最大绝对误差、相对 L2 误差，FP16 包含输入转换造成的误差 |

`sdpa_auto` 的具体内部后端由 PyTorch 决定，本实验不把它猜测为 Flash。强制选择某后端失败时，CSV 中记录 `unsupported`，不补造结果。速度比仅在**相同形状与数据类型**下相对 eager 基线计算。

## 原始 RTX 3050 实测摘要

环境：AMD Ryzen 5 5600H、NVIDIA RTX 3050 Laptop GPU 4 GB、驱动 546.30、Windows 11、Python 3.12.6、PyTorch 2.5.1+cu121。以下结果来自 `results/results.csv`，是这台机器上的一次基准运行。

| 长度 | 精度 | eager 延迟 | 最快可用后端 | 延迟 | 对 eager 加速 | 相对 L2 误差 | 峰值增量 |
| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: |
| 128 | FP16 | 0.272 ms | Auto | 0.050 ms | 5.43× | 0.000397 | 0.062 MiB |
| 256 | FP16 | 0.262 ms | Auto | 0.059 ms | 4.41× | 0.000397 | 0.125 MiB |
| 512 | FP16 | 0.263 ms | Auto | 0.057 ms | 4.59× | 0.000418 | 0.250 MiB |
| 1024 | FP16 | 0.606 ms | cuDNN | 0.093 ms | 6.51× | 0.000427 | 0.501 MiB |
| 1024 | FP32 | 1.194 ms | Efficient | 0.422 ms | 2.83× | 0.000000691 | 1.000 MiB |

在长度 1024、FP16 配置下，eager 的峰值增量为 18 MiB，cuDNN 为约 0.5 MiB。这个指标只覆盖 PyTorch allocator 的本次操作峰值增量，不等于进程显存或整个模型显存。Flash 后端在本机所有测试形状下都返回 `No available kernel`；cuDNN 在 FP16 可用、FP32 不可用。

## RTX 5070 Laptop 复测（2026-10-01）

新增环境：Ryzen 9 8945HX、RTX 5070 Laptop 8 GB、驱动 582.05、Python 3.12.6、PyTorch 2.10.0+cu128。每个配置仍预热 50 次、计时 100 次，独立运行三轮。原始 3050 文件保留不变。

三轮均完成 48 个配置（36 可用、12 不支持），正确性检查通过。Flash 在当前 Windows 构建中仍不可用；cuDNN 仅 FP16 可用。首轮长度 1024 FP16 的 cuDNN 为 0.0683 ms，相对同精度 eager 加速 2.33×，峰值增量由 18 MiB 降至 0.501 MiB。三轮该形状最快后端有所变化，应结合完整重复记录解读。

| 长度 | 精度 | eager ms | 首轮最快 | ms | 对同精度 eager 加速 | 相对 L2 误差 | 峰值增量 MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 128 | float16 | 0.1536 | sdpa_auto | 0.0413 | 3.72× | 0.000404 | 0.062 |
| 128 | float32 | 0.1622 | sdpa_auto | 0.0273 | 5.94× | 4.22e-07 | 0.125 |
| 256 | float16 | 0.1577 | sdpa_auto | 0.0256 | 6.16× | 0.000395 | 0.125 |
| 256 | float32 | 0.1551 | sdpa_auto | 0.0311 | 4.99× | 4.76e-07 | 0.25 |
| 512 | float16 | 0.3839 | sdpa_efficient | 0.0541 | 7.10× | 0.000413 | 0.25 |
| 512 | float32 | 0.3403 | sdpa_auto | 0.0580 | 5.87× | 5e-07 | 0.5 |
| 1024 | float16 | 0.1594 | sdpa_cudnn | 0.0683 | 2.33× | 0.000418 | 0.501 |
| 1024 | float32 | 0.3441 | sdpa_efficient | 0.1808 | 1.90× | 5.73e-07 | 1.0 |

上表为首轮数据。硬件、驱动和软件版本同时改变，不能把跨机器差异当作纯硬件升级收益。后端排名及短操作延迟有波动，详见 [完整复测报告、三轮范围与复现命令](results/2026-10-01-rtx5070-laptop/README.md)。原 `requirements.txt` 对应旧环境；RTX 50 系列使用 `requirements-cu128.txt`，选择器读取新结果时传 `--results results/2026-10-01-rtx5070-laptop/results.csv`。

## 可复现运行（原 RTX 3050 环境）

建议使用 Python 3.12。GPU 版依赖 CUDA 12.1 wheel；没有 NVIDIA GPU 时可安装 CPU wheel 并运行 CPU 配置。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe benchmark.py
.\.venv\Scripts\python.exe recommend.py --max-relative-error 0.001
```

CPU-only 示例：

```bash
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
python benchmark.py --device cpu --lengths 128 256
```

`benchmark.py --help` 可调整长度、计时次数和输出目录。`recommend.py` 可用 `--max-relative-error` 和 `--max-extra-mib` 施加约束，仅在已有 CSV 的精确输入配置中选最快后端；它不是对未测试设备或形状的预测模型。

## 仓库结构

```text
benchmark.py        # 正确性对比、计时、显存、环境元数据
recommend.py        # 误差/显存约束下的实测后端选择
tests/              # 因果掩码与 SDPA 对照测试
results/results.csv # 原始逐配置结果，包括不支持的后端
results/metadata.json
.github/workflows/   # CPU 正确性与小规模运行检查
```

## 解读与局限

- 这是算子级推理实验，没有训练模型，也不代表端到端 LLM 吞吐或生成质量。
- 每个配置使用一次随机输入；不同输入值、驱动、PyTorch 版本、温度和功耗状态可能改变结果。
- GPU 延迟基于 CUDA Event；CPU 结果使用墙钟时间，二者不直接计算加速比。
- `peak_extra_mib` 不统计 CUDA context、缓存分配器保留量或外部进程显存。
- 自动后端内部选择可能随版本改变，强制后端的可用性也可能改变。

## 简历可用表述

> 构建 PyTorch 因果注意力算子基准，覆盖 4 种序列长度、FP16/FP32、6 种实现模式，记录延迟、PyTorch 峰值显存增量与相对 L2 误差；在 RTX 3050 Laptop GPU 上，长度 1024 的 FP16 cuDNN 路径较 eager 基线加速 6.51 倍，并实现基于误差/显存约束的实测后端选择器。

## 参考

- [PyTorch scaled dot product attention documentation](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention)
- [PyTorch SDPA backend selection](https://docs.pytorch.org/docs/stable/generated/torch.nn.attention.sdpa_kernel.html)
- [PyTorch benchmark guidance](https://docs.pytorch.org/docs/stable/benchmark_utils.html)

License: MIT. No API keys, private data, or downloaded datasets are used.
