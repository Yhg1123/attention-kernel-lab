# Prefill / KV-cache decode 的应用负载实验

本次环境为 Ryzen 9 8945HX、RTX 5070 Laptop 8 GB、Windows 11、驱动 582.05、Python 3.12.6、PyTorch 2.10.0+cu128，CPU 固定 4 线程、TF32 关闭。配置、源码哈希和依赖版本保存在 [metadata.json](metadata.json)。

与原 `benchmark.py` 的 CUDA Event 计时不同，新实验使用逐请求同步墙钟计时，包含 Python/主机提交开销；因此不能将新旧绝对延迟直接当作同一指标。每轮候选顺序随机化，所有原始计时在 [samples.jsonl](samples.jsonl)，逐轮结果在 [results.csv](results.csv)，汇总在 [summary.csv](summary.csv)。汇总延迟是三轮中位数的中位数，P95 是三轮各自 P95 的最大值，误差/资源取最坏观测值；不是统计置信区间。

短操作仍存在噪声；随机顺序和重复测量降低了固定顺序带来的风险，但未控制系统调度、温度、频率和所有后台负载。样本 P95 不能当作生产 SLA 保证。显存指标是 PyTorch allocator 在已分配输入/模型等张量以上的单次操作峰值增量，包含输出/临时张量，不是整机或模型总显存；CPU 显存指标留空。

## 实验范围

整段输入（prefill）和已有缓存上的单 token 解码（decode），batch=1/4、heads=4、head_dim=64、KV 长度 256/1024/2048、FP32/FP16、6 种后端。3 个随机种子，每配置预热 10 次、测量 30 次：共 144 个配置、432 条逐轮记录。其中 108 个配置三轮均可用，36 个三轮均不支持，无 OOM；每轮同形状的候选使用相同 FP32 原始输入，低精度误差包含输入转换。

只计算已有 Q/K/V 上的 attention，不包含 QKV 投影、位置编码、KV 缓存写入、MLP 或完整生成服务。`items_per_second` 计数的是 query tokens，不是完整模型生成速度。

## 结果与应用判断

以下为 batch=4、heads=4、head_dim=64、FP16 的三轮汇总：

| 模式 | KV 长度 | eager ms | 汇总最快后端 | 后端 ms | 中位数比值 | 峰值增量 MiB |
| --- | --- | --- | --- | --- | --- | --- |
| prefill | 256 | 0.1450 | sdpa_auto | 0.0352 | 4.12× | 4.562 → 0.500 |
| prefill | 1024 | 1.1166 | sdpa_cudnn | 0.1482 | 7.53× | 67.000 → 2.001 |
| prefill | 2048 | 5.2624 | sdpa_cudnn | 0.3246 | 16.21× | 264.000 → 4.001 |
| decode | 256 | 0.0807 | sdpa_auto | 0.0428 | 1.89× | 0.018 → 0.002 |
| decode | 1024 | 0.0822 | sdpa_auto | 0.0676 | 1.21× | 0.064 → 0.002 |
| decode | 2048 | 0.0821 | sdpa_cudnn | 0.0696 | 1.18× | 0.127 → 0.020 |

1. 较大 prefill 负载中，后端选择的收益很大：长度 2048 的 cuDNN 延迟从 5.2624 ms 降到 0.3246 ms，中位数比值为 16.21×；操作峰值增量从 264 MiB 降到约 4.001 MiB。这能支持长提示词处理时的算子后端选型，但不代表完整模型同倍数加速。
2. Decode 与 prefill 应分开测量。同样 KV 长度 2048，batch=4 单 token 解码的最快配置相对 eager 仅约 1.18×。不能用 prefill 的十几倍收益推断逐 token 生成收益。
3. 最快后端随负载变化，Auto 不是所有配置的最快选项。Flash 在当前 Windows wheel 的所有测量中不可用，cuDNN 仅 FP16 可用；这是环境结果，不是 GPU 硬件能力的普遍结论。
4. `policy-1mib.json` 在误差 ≤0.001、额外显存 ≤1 MiB 的示例约束下，为 24 个工作负载中的 19 个找到候选，其余明确标为 `no_match`。没有把超预算配置静默丢掉。

## 解码掩码与可调用接口

解码的 Q 只有最新一个 token，K/V 已包含历史及当前 token，且没有 padding/future token。这时所有 key 都可见，使用 `is_causal=False`。直接使用 `is_causal=True` 会采用左上对齐，错误地只看第一个 key。[PyTorch SDPA 语义](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html)

`MeasuredAttention` 可以读取本次策略，检查设备/软件/线程配置、实现源码和精确输入形状，再调用测过的后端。未知形状、不可行约束、非连续输入和需要梯度的输入会明确报错。这里只支持 square prefill 与单 token decode，不支持有 padding 的缓存、chunked decode、GQA 或训练。

## 复现与检查

```powershell
python profile_workloads.py --output results/my-workloads
python select_profile.py --run results/my-workloads --output results/my-workloads/policy.json --max-relative-error 0.001 --max-extra-mib 1
python -m unittest discover -s tests -v
```

原始实验文件保持不变。新测量脚本、策略导出、调用示例详见 [APPLICATIONS.md](../../APPLICATIONS.md)。本地 16 项测试通过，涵盖解码可见性、与完整 prefill 最后位置的一致性、因果性、无解/NaN/不完整轮次筛选和环境/源码保护；另已在 GPU 上执行导出的策略并与 FP32 reference 对照。
