# 从算子实验到推理后端选型

这个仓库可用于回答：**在目标机器和精确输入形状上，哪个注意力后端满足误差、额外显存和延迟要求？** 最新证据在 [负载实验报告](results/2026-10-01-workloads/README.md)。历史 `benchmark.py` 及 3050/5070 复测文件仍保留。

## 使用方式

先激活独立 Python 环境，RTX 50 系列使用 `python -m pip install -r requirements-cu128.txt`。

```powershell
python profile_workloads.py --lengths 256 1024 2048 --batch-sizes 1 4 --modes prefill decode --dtypes float32 float16 --trials 3 --output results/my-workloads
python select_profile.py --run results/my-workloads --output policy.json --max-relative-error 0.001 --max-extra-mib 1
```

可进一步传 `--max-p95-ms`、`--max-spread-ratio`（最大/最小轮次中位数），筛掉尾延迟或波动不符合要求的候选。选择器只接受完成的 schema-v2 记录，要求全部轮次成功；默认至少 3 轮。无可行候选时，JSON 保留工作负载及拒绝原因。原始 `recommend.py` 仍可读取历史 CSV，但它是单轮选择器。

## 在已有 Q/K/V 的推理代码中调用

```python
import torch
from measured_attention import MeasuredAttention

torch.set_num_threads(4)  # 与采样环境一致
torch.backends.cuda.matmul.allow_tf32 = False
selected = MeasuredAttention("policy.json")
with torch.inference_mode():
    q = torch.randn(1, 4, 1, 64, device="cuda", dtype=torch.float16)
    k = torch.randn(1, 4, 1024, 64, device="cuda", dtype=torch.float16)
    v = torch.randn_like(k)
    output = selected(q, k, v, mode="decode")
```

模型中的实际 K/V 应是已有的有效缓存，包括当前 token；示例随机张量只展示接口。策略检查在加载时执行，之后应维持相同线程、精度与设备设置。换环境或形状要重新测量；历史策略不能保证新输入值的误差和尾延迟。内存上限只约束额外 allocator 峰值，不约束模型及缓存总大小。

输出包含原始样本、逐轮 CSV、汇总 CSV、版本/源码哈希、每个形状的可行选项和拒绝理由。新实验改变了计时方法，勿把它与旧 CUDA Event 数字直接计算升级倍数。
