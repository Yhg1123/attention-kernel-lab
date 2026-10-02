# 完整回答及事后逐条复核

由本次编程助手对照虚构文档复核；不是独立人工盲评。评分规则见 README。原始模型输出未改动。

## password_length / long / baseline

青禾云登录密码最少需要多少个字符？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## password_length / long / strict

青禾云登录密码最少需要多少个字符？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## uptime_sla / long / strict

青禾云承诺的全年服务可用性百分比是多少？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## uptime_sla / long / baseline

青禾云承诺的全年服务可用性百分比是多少？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## cross_price_backup / short / baseline

青禾云基础版月费和自动备份保留天数分别是多少？

青禾云基础版每月费用为39元，自动备份保留14天。

复核：grounded_correct。答案所需事实与文档一致。

## cross_price_backup / short / strict

青禾云基础版月费和自动备份保留天数分别是多少？

青禾云基础版的月费是39元，自动备份保留14天。

复核：grounded_correct。答案所需事实与文档一致。

## enterprise_storage / short / strict

青禾云企业定制版包含多少GB存储空间？

青禾云企业定制版包含200GB团队存储空间。

复核：unsupported_claim。将其他套餐的价格或容量错误归给企业定制版；文档没有该版本数值。

## enterprise_storage / short / baseline

青禾云企业定制版包含多少GB存储空间？

青禾云企业定制版包含200GB团队存储空间。

复核：unsupported_claim。将其他套餐的价格或容量错误归给企业定制版；文档没有该版本数值。

## refund_allowed / short / baseline

青禾云首次购买后2天，从未创建项目，符合全额退款条件吗？

不符合。因为只有在支付成功后的7天内且没有创建任何项目才能申请全额退款。

复核：wrong_fact。首次购买2天且从未建项目满足两个条件，答案却说不符合。原关键词检查误判。

## refund_allowed / short / strict

青禾云首次购买后2天，从未创建项目，符合全额退款条件吗？

不符合。因为退款规则要求首次购买青禾云套餐后，在支付成功后的7天内且没有创建任何项目，才能申请全额退款。

复核：wrong_fact。首次购买2天且从未建项目满足两个条件，答案却说不符合。原关键词检查误判。

## deleted_project / long / strict

青禾云首次购买2天，创建项目后又删除，能申请首次购买全额退款吗？

不可以。根据青禾云退款规则，首次购买青禾云套餐后，在支付成功后的7天内且没有创建任何项目，才能申请全额退款。

复核：grounded_correct。答案所需事实与文档一致。

## deleted_project / long / baseline

青禾云首次购买2天，创建项目后又删除，能申请首次购买全额退款吗？

不可以，因为创建项目后又删除了项目，不符合首次购买退款的条件。

复核：grounded_correct。答案所需事实与文档一致。

## emptied_bin / long / baseline

青禾云管理员手工清空回收站后，还能从回收站恢复这些文件吗？

不可以，管理员手工清空回收站后，文件不能再从回收站恢复。

复核：grounded_correct。答案所需事实与文档一致。

## emptied_bin / long / strict

青禾云管理员手工清空回收站后，还能从回收站恢复这些文件吗？

不可以，管理员手工清空回收站后，文件不能再从回收站恢复。

复核：grounded_correct。答案所需事实与文档一致。

## plan_change / long / strict

青禾云更改套餐后何时生效？当前账期用哪个套餐？

青禾云套餐变更将在下一个账期生效。当前账期继续执行原套餐。

复核：grounded_correct。答案所需事实与文档一致。

## plan_change / long / baseline

青禾云更改套餐后何时生效？当前账期用哪个套餐？

套餐变更将在下一个账期生效，当前账期继续执行原套餐。

复核：grounded_correct。答案所需事实与文档一致。

## storage_count / long / baseline

青禾云回收站里的文件也计入团队容量吗？

不计入。

复核：wrong_fact。文档明确回收站文件计入容量，答案却说不计入。原关键词检查误判。

## storage_count / long / strict

青禾云回收站里的文件也计入团队容量吗？

不计入。

复核：wrong_fact。文档明确回收站文件计入容量，答案却说不计入。原关键词检查误判。

## export_zip / long / strict

青禾云导出任务生成的压缩包使用什么压缩算法？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## export_zip / long / baseline

青禾云导出任务生成的压缩包使用什么压缩算法？

文档未提供关于青禾云导出任务生成的压缩包使用哪种压缩算法的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## export_formats / long / baseline

青禾云支持哪两种数据导出格式？

青禾云支持CSV和JSON两种数据导出格式。

复核：grounded_correct。答案所需事实与文档一致。

## export_formats / long / strict

青禾云支持哪两种数据导出格式？

青禾云支持CSV和JSON两种数据导出格式。

复核：grounded_correct。答案所需事实与文档一致。

## api_limit / short / strict

青禾云API每分钟最多允许多少次请求？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## api_limit / short / baseline

青禾云API每分钟最多允许多少次请求？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## refund_arrival / short / baseline

青禾云退款审核通过后，保证几个工作日到账？

退款退回原支付渠道，到账时间以支付渠道通知为准。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## refund_arrival / short / strict

青禾云退款审核通过后，保证几个工作日到账？

退款退回原支付渠道，到账时间以支付渠道通知为准。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## cross_support_export / long / strict

青禾云人工客服工作日服务时间是什么？导出链接有效期多长？

青禾云人工客服的工作日服务时间为09:00至18:00。导出链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## cross_support_export / long / baseline

青禾云人工客服工作日服务时间是什么？导出链接有效期多长？

青禾云人工客服的工作时间为工作日的09:00至18:00。导出链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## invite_hours / short / baseline

青禾云成员邀请链接发出后具体几小时过期？

邀请链接只能由目标邮箱的持有人使用，过期邀请需要由管理员重新发送。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## invite_hours / short / strict

青禾云成员邀请链接发出后具体几小时过期？

邀请链接只能由目标邮箱的持有人使用，过期邀请需要由管理员重新发送。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## emptied_bin / short / strict

青禾云管理员手工清空回收站后，还能从回收站恢复这些文件吗？

不可以。管理员手工清空回收站后，文件不能再从回收站恢复。

复核：grounded_correct。答案所需事实与文档一致。

## emptied_bin / short / baseline

青禾云管理员手工清空回收站后，还能从回收站恢复这些文件吗？

不能。管理员手工清空回收站后，文件不能再从回收站恢复。

复核：grounded_correct。答案所需事实与文档一致。

## api_limit / long / baseline

青禾云API每分钟最多允许多少次请求？

文档未提供关于青禾云API每分钟最多允许多少次请求的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## api_limit / long / strict

青禾云API每分钟最多允许多少次请求？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## base_capacity / long / strict

青禾云基础版提供多少存储空间和成员席位？

青禾云基础版提供20GB团队存储空间和3个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## base_capacity / long / baseline

青禾云基础版提供多少存储空间和成员席位？

青禾云基础版每月费用为39元，包含20GB团队存储空间和3个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## enterprise_storage / long / baseline

青禾云企业定制版包含多少GB存储空间？

青禾云企业定制版包含200GB团队存储空间。

复核：unsupported_claim。将其他套餐的价格或容量错误归给企业定制版；文档没有该版本数值。

## enterprise_storage / long / strict

青禾云企业定制版包含多少GB存储空间？

青禾云企业定制版包含200GB团队存储空间。

复核：unsupported_claim。将其他套餐的价格或容量错误归给企业定制版；文档没有该版本数值。

## invite_hours / long / strict

青禾云成员邀请链接发出后具体几小时过期？

邀请链接只能由目标邮箱的持有人使用，过期邀请需要由管理员重新发送。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## invite_hours / long / baseline

青禾云成员邀请链接发出后具体几小时过期？

邀请链接只能由目标邮箱的持有人使用，过期邀请需要由管理员重新发送。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## backup_time / short / baseline

青禾云每天几点执行自动备份？

青禾云每天凌晨02:00执行一次自动备份。

复核：grounded_correct。答案所需事实与文档一致。

## backup_time / short / strict

青禾云每天几点执行自动备份？

青禾云每天凌晨02:00执行一次自动备份。

复核：grounded_correct。答案所需事实与文档一致。

## backup_region / short / strict

青禾云自动备份存储在哪个城市的数据中心？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## backup_region / short / baseline

青禾云自动备份存储在哪个城市的数据中心？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## cross_support_export / short / baseline

青禾云人工客服工作日服务时间是什么？导出链接有效期多长？

青禾云人工客服的工作日服务时间为09:00至18:00。导出链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## cross_support_export / short / strict

青禾云人工客服工作日服务时间是什么？导出链接有效期多长？

青禾云人工客服的工作日服务时间为09:00至18:00。导出链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## export_formats / short / strict

青禾云支持哪两种数据导出格式？

青禾云支持CSV和JSON两种数据导出格式。

复核：grounded_correct。答案所需事实与文档一致。

## export_formats / short / baseline

青禾云支持哪两种数据导出格式？

青禾云支持CSV和JSON两种数据导出格式。

复核：grounded_correct。答案所需事实与文档一致。

## export_zip / short / baseline

青禾云导出任务生成的压缩包使用什么压缩算法？

文档未提供关于青禾云导出任务生成的压缩包使用哪种压缩算法的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## export_zip / short / strict

青禾云导出任务生成的压缩包使用什么压缩算法？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## pro_members / long / strict

青禾云专业版包含多少个成员席位？

青禾云专业版包含20个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## pro_members / long / baseline

青禾云专业版包含多少个成员席位？

青禾云专业版包含20个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## password_length / short / baseline

青禾云登录密码最少需要多少个字符？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## password_length / short / strict

青禾云登录密码最少需要多少个字符？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## invoice_tax / long / strict

青禾云开具增值税发票的税率是多少？

文档未提供关于青禾云开具增值税发票税率的具体信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## invoice_tax / long / baseline

青禾云开具增值税发票的税率是多少？

文档未提供相关信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## pro_members / short / baseline

青禾云专业版包含多少个成员席位？

青禾云专业版包含20个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## pro_members / short / strict

青禾云专业版包含多少个成员席位？

青禾云专业版包含20个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## expired_export / short / strict

青禾云导出文件的下载链接过期了怎么办？

如果青禾云导出文件的下载链接过期了，用户需要重新生成新的下载链接。

复核：grounded_correct。答案所需事实与文档一致。

## expired_export / short / baseline

青禾云导出文件的下载链接过期了怎么办？

如果青禾云导出文件的下载链接过期了，您需要重新生成新的下载链接。

复核：grounded_correct。答案所需事实与文档一致。

## member_files / short / baseline

青禾云移除离职成员后，此人以前创建的团队文件会自动删除吗？

不会。

复核：grounded_correct。答案所需事实与文档一致。

## member_files / short / strict

青禾云移除离职成员后，此人以前创建的团队文件会自动删除吗？

否。移除成员不会自动删除该成员此前创建的团队文件，文件仍按照项目权限管理。

复核：grounded_correct。答案所需事实与文档一致。

## plan_change / short / strict

青禾云更改套餐后何时生效？当前账期用哪个套餐？

青禾云套餐变更将在下一个账期生效。当前账期仍然使用原来的套餐。

复核：grounded_correct。答案所需事实与文档一致。

## plan_change / short / baseline

青禾云更改套餐后何时生效？当前账期用哪个套餐？

套餐变更将在下一个账期生效，当前账期继续执行原套餐。

复核：grounded_correct。答案所需事实与文档一致。

## member_files / long / baseline

青禾云移除离职成员后，此人以前创建的团队文件会自动删除吗？

否，移除成员不会自动删除该成员此前创建的团队文件，文件仍按照项目权限管理。

复核：grounded_correct。答案所需事实与文档一致。

## member_files / long / strict

青禾云移除离职成员后，此人以前创建的团队文件会自动删除吗？

否，移除离职成员不会自动删除该成员此前创建的团队文件。这些文件仍然按照项目权限管理，并且文件在回收站保留30天，超过30天后会自动清理。

复核：unsupported_claim。移除成员不删除文件，但额外把这些文件关联到回收站30天清理；文档没有这个因果关系。

## invoice_tax / short / strict

青禾云开具增值税发票的税率是多少？

文档未提供关于青禾云开具增值税发票税率的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## invoice_tax / short / baseline

青禾云开具增值税发票的税率是多少？

文档未提供关于青禾云开具增值税发票税率的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## base_capacity / short / baseline

青禾云基础版提供多少存储空间和成员席位？

青禾云基础版提供20GB团队存储空间和3个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## base_capacity / short / strict

青禾云基础版提供多少存储空间和成员席位？

青禾云基础版提供20GB团队存储空间和3个成员席位。

复核：grounded_correct。答案所需事实与文档一致。

## refund_arrival / long / strict

青禾云退款审核通过后，保证几个工作日到账？

退款退回原支付渠道，到账时间以支付渠道通知为准。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## refund_arrival / long / baseline

青禾云退款审核通过后，保证几个工作日到账？

退款退回原支付渠道，到账时间以支付渠道通知为准。

复核：grounded_nonanswer。复述了相关文档，但未给出所问的具体时长，也未明确说该信息缺失；没有捏造数值。

## support_phone / short / baseline

青禾云人工客服的电话号码是什么？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## support_phone / short / strict

青禾云人工客服的电话号码是什么？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## expired_export / long / strict

青禾云导出文件的下载链接过期了怎么办？

如果青禾云导出文件的下载链接过期了，你需要重新生成新的下载链接。具体步骤如下：

1. 确认你的导出任务已经完成了。
2. 登录青禾云控制台。
3. 在“导出”选项卡下找到你想要更新的导出任务。
4. 选择“刷新”按钮来获取新的下载链接。
5. 使用新的下载链接下载文件即可。

复核：unsupported_claim。重新生成链接是正确方向，但编造了导出选项卡和刷新按钮操作。

## expired_export / long / baseline

青禾云导出文件的下载链接过期了怎么办？

如果青禾云导出文件的下载链接过期了，您应该立即重新生成新的下载链接。

复核：grounded_correct。答案所需事实与文档一致。

## storage_count / short / baseline

青禾云回收站里的文件也计入团队容量吗？

不计入。

复核：wrong_fact。文档明确回收站文件计入容量，答案却说不计入。原关键词检查误判。

## storage_count / short / strict

青禾云回收站里的文件也计入团队容量吗？

不计入。

复核：wrong_fact。文档明确回收站文件计入容量，答案却说不计入。原关键词检查误判。

## support_phone / long / strict

青禾云人工客服的电话号码是什么？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## support_phone / long / baseline

青禾云人工客服的电话号码是什么？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## backup_time / long / baseline

青禾云每天几点执行自动备份？

青禾云每天凌晨02:00执行一次自动备份。

复核：grounded_correct。答案所需事实与文档一致。

## backup_time / long / strict

青禾云每天几点执行自动备份？

青禾云每天凌晨02:00执行自动备份。

复核：grounded_correct。答案所需事实与文档一致。

## export_split / short / strict

青禾云导出60000条记录应如何处理？

如果需要导出超过50000条记录，应该按日期或项目分批进行导出。每一批次的导出数量不应超过50000条。这样可以确保所有数据都能成功导出，并且每个批次的操作都有详细的记录。

复核：unsupported_claim。分批方法正确，但“确保所有数据都能成功导出”是文档没有给出的保证。

## export_split / short / baseline

青禾云导出60000条记录应如何处理？

超过50000条记录需要按日期或项目分批导出。

复核：grounded_correct。答案所需事实与文档一致。

## cross_price_backup / long / baseline

青禾云基础版月费和自动备份保留天数分别是多少？

青禾云基础版的月费为39元，自动备份保留14天。

复核：grounded_correct。答案所需事实与文档一致。

## cross_price_backup / long / strict

青禾云基础版月费和自动备份保留天数分别是多少？

青禾云基础版的月费是39元，自动备份保留14天。

复核：grounded_correct。答案所需事实与文档一致。

## export_split / long / strict

青禾云导出60000条记录应如何处理？

如果需要导出超过50000条记录，应该按日期或项目分批进行导出。

复核：grounded_correct。答案所需事实与文档一致。

## export_split / long / baseline

青禾云导出60000条记录应如何处理？

超过50000条记录需要按日期或项目分批导出。

复核：grounded_correct。答案所需事实与文档一致。

## uptime_sla / short / baseline

青禾云承诺的全年服务可用性百分比是多少？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## uptime_sla / short / strict

青禾云承诺的全年服务可用性百分比是多少？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## refund_allowed / long / strict

青禾云首次购买后2天，从未创建项目，符合全额退款条件吗？

是的，根据青禾云退款规则，如果首次购买青禾云套餐后，在支付成功后的7天内且没有创建任何项目，可以申请全额退款。这个条件必须同时满足。

复核：grounded_correct。答案所需事实与文档一致。

## refund_allowed / long / baseline

青禾云首次购买后2天，从未创建项目，符合全额退款条件吗？

符合。

复核：grounded_correct。答案所需事实与文档一致。

## backup_region / long / baseline

青禾云自动备份存储在哪个城市的数据中心？

文档未提供关于自动备份数据中心位置的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## backup_region / long / strict

青禾云自动备份存储在哪个城市的数据中心？

文档未提供关于青禾云自动备份存储在哪个城市数据中心的具体信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## deleted_project / short / strict

青禾云首次购买2天，创建项目后又删除，能申请首次购买全额退款吗？

不可以。因为退款规则要求首次购买后在支付成功后的7天内且没有创建任何项目才能申请全额退款。在这个情况下，虽然有创建项目，但不符合退款条件。

复核：grounded_correct。答案所需事实与文档一致。

## deleted_project / short / baseline

青禾云首次购买2天，创建项目后又删除，能申请首次购买全额退款吗？

不能，因为退款规则要求首次购买后支付成功后的7天内且没有创建任何项目才能申请全额退款。

复核：grounded_correct。答案所需事实与文档一致。
