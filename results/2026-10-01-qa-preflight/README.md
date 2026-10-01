# Qwen 问答预检：保留失败配置

这是在正式应用测试之前进行的开发预检，只有**一道独立价格问题**、短长两种资料，各配置仅一轮。它能发现明显不可用的方案，不能用于宣布正式加速比例或通用正确率。正式三轮结果单独存放。

问题：青禾云专业版每月多少钱，有多少存储空间？文档答案：每月 **99 元、200GB**。

| 预检配置 | 观察 | 处理 |
|---|---|---|
| CPU FP32 eager | 短长资料均回答 99 元、200GB | 进入正式测试作为 CPU 参考 |
| GPU FP16 eager | 短长资料均反复生成 `!`，达到 64 token 上限 | 不作为有效基线；应用增加无效 logits 检查 |
| GPU FP16 SDPA | 短长资料均正确 | 正式 GPU 比较统一采用 BF16，使 eager 基线也能正确回答 |
| CPU 全 Linear 动态 INT8 | 短资料转成编程求助，长资料转成无关选择题 | 拒绝部署，不把较短计时算成有效加速 |
| CPU 仅 MLP 动态 INT8 | 回答无关的翻译题、团队概念 | 拒绝部署 |
| CPU 仅 MLP、逐通道权重 INT8 | 回答编程代码或其他无关内容 | 拒绝部署 |
| GPU BF16 eager / SDPA / cuDNN | 均正确回答该价格题 | 进入正式多题测试 |

原始首轮在本目录的 `requests.jsonl`、`summary.csv`、`metadata.json`；相应源码快照位于 `source/`，按 metadata 的哈希保存。第二、三次开发预检分别在 `bf16-and-mlp/` 和 `cudnn-and-channel-quant/`。预检间代码有增加校验与配置等变化，不能把不同预检的计时拼成正式排行榜。后两次记录包含源码哈希，最终脚本仍支持这些配置，但其最终源码并不等于开发中的每个中间版本。

第一轮固定输出 32 token、自然回答上限 64 token；正式测试采用固定 64 token、自然回答上限 96 token。固定输出为速度控制，EOS 被刻意禁止到达指定长度前，因此在正确答案后可能继续生成无关内容；它不计入答案质量评估。

这些结果仅说明：当前模型、PyTorch/oneDNN 配置和动态量化方法没有通过这道应用验收题。它们不证明所有 INT8、GPTQ/AWQ 等量化方法或所有模型都不可用。之前 DistilBERT 分类任务的 INT8 结果仍有效，也不能代替这里的生成式问答验收。

复核示例（最终版本会对 FP16 eager 的无效 logits 报错，而不是继续输出 `!`）：

```powershell
python qa_benchmark.py --output results/my-int8-check --trials 1 --question-ids price --max-new-tokens 64 --fixed-tokens 32 --variants cpu_eager_int8 cpu_eager_int8_mlp cpu_eager_int8_mlp_per_channel --local-files-only
```
