# 开发集：8 道题 / 32 次请求

测试方案和全文结论见 [QA_QUALITY.md](../../QA_QUALITY.md)。6 道历史题加 2 道开发题，baseline/strict × short/long，各测一次。提示词在运行前固定；发现失败后仍保留该候选进行预留验证，没有把开发结果混入预留指标。

`requests.jsonl` 为原始响应，`summary.csv` 为当时自动关键词及精确拒答统计；`answer_review.json`、`answers_reviewed.md`、`review_summary.csv` 为另存的事后助手复核。旧字段 `unsupported_answer(s)` 仅表示未满足精确拒答格式，不能直接解释为幻觉。

`source/` 保存实际运行的源码、文档和题目，逐文件哈希见 metadata。两种提示词均短资料 8/8、长资料 7/8 通过全文复核，长资料失败为企业定制版年费编造。
