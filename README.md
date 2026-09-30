# Attention Kernel Lab | 注意力算子性能实验

An evidence based comparison of causal attention implementations on a 4 GB laptop GPU. This project measures **latency, temporary PyTorch memory, numerical error, and backend availability** together. It also includes a constraint based selector that chooses only among configurations actually measured on this machine.

这是一个可复现的注意力算子实验，不是自研 CUDA Kernel。项目比较 PyTorch eager 实现、`scaled_dot_product_attention` 自动选择、Math、Flash、Memory Efficient 和 cuDNN 后端，并记录每种输入规模下的性能、误差和支持情况。

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

## 本机实测摘要

环境：AMD Ryzen 5 5600H、NVIDIA RTX 3050 Laptop GPU 4 GB、驱动 546.30、Windows 11、Python 3.12.6、PyTorch 2.5.1+cu121。以下结果来自 `results/results.csv`，是这台机器上的一次基准运行。

| 长度 | 精度 | eager 延迟 | 最快可用后端 | 延迟 | 对 eager 加速 | 相对 L2 误差 | 峰值增量 |
| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: |
| 128 | FP16 | 0.272 ms | Auto | 0.050 ms | 5.43× | 0.000397 | 0.062 MiB |
| 256 | FP16 | 0.262 ms | Auto | 0.059 ms | 4.41× | 0.000397 | 0.125 MiB |
| 512 | FP16 | 0.263 ms | Auto | 0.057 ms | 4.59× | 0.000418 | 0.250 MiB |
| 1024 | FP16 | 0.606 ms | cuDNN | 0.093 ms | 6.51× | 0.000427 | 0.501 MiB |
| 1024 | FP32 | 1.194 ms | Efficient | 0.422 ms | 2.83× | 0.000000691 | 1.000 MiB |

在长度 1024、FP16 配置下，eager 的峰值增量为 18 MiB，cuDNN 为约 0.5 MiB。这个指标只覆盖 PyTorch allocator 的本次操作峰值增量，不等于进程显存或整个模型显存。Flash 后端在本机所有测试形状下都返回 `No available kernel`；cuDNN 在 FP16 可用、FP32 不可用。

## 可复现运行

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
