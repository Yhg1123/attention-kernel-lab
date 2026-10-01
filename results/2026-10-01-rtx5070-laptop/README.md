# 2026-10-01 · RTX 5070 Laptop 复现实验

## 环境与方法

- CPU：AMD Ryzen 9 8945HX，16 核 / 32 线程；系统内存约 32 GB。
- GPU：NVIDIA GeForce RTX 5070 Laptop GPU，驱动报告 8151 MiB，计算能力 12.0；驱动 582.05，Windows 11（26200）。
- Python 3.12.6；PyTorch 2.10.0+cu128；CUDA runtime 12.8；cuDNN 9.10.2。
- 测试开始时接通电源，Windows 平衡电源方案；未修改系统电源设置或锁定 GPU 时钟。开始/结束的 GPU 状态见 [environment.json](environment.json)，不是持续监控或恒定功耗保证。
- 沿用原实验的输入规模、随机种子 2026、预热 50 次、每配置计时 100 次。三个独立进程依次运行，两个仓库的基准不并发。
- 第一轮是本目录 [results.csv](results.csv)，后两轮在 [repeat-02/results.csv](repeat-02/results.csv)、[repeat-03/results.csv](repeat-03/results.csv)。表格标明首轮或三轮汇总，不挑选最好的一轮。
- [summary.csv](summary.csv) 的 `median_of_medians_ms` 是三轮各自中位数的中位数；不是把 300 个样本合并后的中位数。原脚本不导出单次计时样本。

原 RTX 3050 数据仍在 [../results.csv](../results.csv)，对应 PyTorch 2.5.1+cu121。这里的硬件、驱动、PyTorch、CUDA 版本同时变化，跨机器差异不能解释为纯硬件提升。PyTorch 从 2.7 开始提供 Blackwell / CUDA 12.8 支持，安装版本参考 [官方发行说明](https://pytorch.org/blog/pytorch-2-7/) 和 [官方历史版本页](https://pytorch.org/get-started/previous-versions/)。

## 首轮结果

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

每轮 48 个配置：36 个可用，12 个不支持。三轮支持情况一致：Flash 在所有 8 个形状/精度配置均不可用；cuDNN 在 FP16 可用、FP32 不可用。这里是当前 Windows wheel / 环境的结果，不能推广为 RTX 5070 硬件不支持 Flash。Auto 内部后端未做归因。

长度 1024、FP16 的首轮 eager 峰值增量为 18 MiB，cuDNN 为 0.501 MiB；该指标只覆盖 PyTorch allocator 的输出和临时张量，不是进程或模型总显存。

## 三轮变化

| 长度 | 精度 | 第 1 / 2 / 3 轮最快后端 | 各轮最快延迟范围 ms | 各轮对 eager 加速范围 |
| --- | --- | --- | --- | --- |
| 128 | float16 | sdpa_auto / sdpa_auto / sdpa_auto | 0.0413–0.0594 | 3.72–8.52× |
| 128 | float32 | sdpa_auto / sdpa_auto / sdpa_auto | 0.0273–0.0439 | 5.40–6.15× |
| 256 | float16 | sdpa_auto / sdpa_auto / sdpa_auto | 0.0254–0.0400 | 5.72–6.16× |
| 256 | float32 | sdpa_auto / sdpa_auto / sdpa_auto | 0.0311–0.0466 | 3.31–4.99× |
| 512 | float16 | sdpa_efficient / sdpa_auto / sdpa_auto | 0.0280–0.0541 | 5.49–7.10× |
| 512 | float32 | sdpa_auto / sdpa_auto / sdpa_auto | 0.0576–0.0580 | 2.57–5.87× |
| 1024 | float16 | sdpa_cudnn / sdpa_efficient / sdpa_efficient | 0.0683–0.0884 | 1.77–2.37× |
| 1024 | float32 | sdpa_efficient / sdpa_efficient / sdpa_efficient | 0.1787–0.1845 | 1.88–1.95× |

短算子的计时存在明显波动，尤其长度 512 FP16、1024 FP16 的最快后端发生变化。原有固定顺序、逐调用 CUDA Event 计时还会受到主机提交、WDDM 调度与动态频率影响，因此不应把首轮的后端排名或加速倍数视作稳定保证。

## 与原机器并列查看

同为 FP16 `sdpa_auto`，以下均为各环境的首轮测量；没有据此计算纯显卡升级倍数。

| 长度 | 3050 / torch 2.5.1 延迟 ms | 5070 / torch 2.10.0 延迟 ms |
| --- | --- | --- |
| 128 | 0.0502 | 0.0413 |
| 256 | 0.0594 | 0.0256 |
| 512 | 0.0573 | 0.0662 |
| 1024 | 0.1004 | 0.0905 |

## 验证

- 原有 2 项单元测试通过；CPU smoke 的 3 个配置运行成功。
- 三轮各 48 行，配置网格完整，无重复；可用行的时间、误差、显存指标有限且非负，加速比按相同长度/精度复核。
- FP32 相对 L2 误差小于 1e-5，FP16 小于 0.002；不支持行没有伪造计时值。
- `benchmark.py`、`recommend.py` 和数值/计时方法未修改。

## 复现命令

在仓库根目录运行，使用 Python 3.12.6。`requirements.txt` 保留原机器的版本；本次使用独立的 `requirements-cu128.txt`。如果需要复刻全部 Python 依赖，使用本目录 [requirements-lock.txt](requirements-lock.txt)。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-cu128.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$output = 'results/local-rtx5070'
.\.venv\Scripts\python.exe benchmark.py --device cuda --output $output
.\.venv\Scripts\python.exe benchmark.py --device cuda --output "$output/repeat-02"
.\.venv\Scripts\python.exe benchmark.py --device cuda --output "$output/repeat-03"
.\.venv\Scripts\python.exe recommend.py --results "$output/results.csv" --max-relative-error 0.001
```

命令和 UTC 时间戳见 [execution.json](execution.json)；硬件、软件和运行源码 SHA-256 见 [environment.json](environment.json)；每轮 `metadata.json`、`benchmark.log`、`validation.log` 保留实际设置、输出和检查结果。首轮选择器输出在 [recommendations.csv](recommendations.csv)。历史 `results/results.csv` 保持不变，选择器默认仍读取历史数据，查看本次结果必须显式传入 `--results`。
