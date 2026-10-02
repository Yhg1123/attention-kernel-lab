# 完整回答及事后逐条复核

由本次编程助手对照虚构文档复核；不是独立人工盲评。评分规则见 README。原始模型输出未改动。

## retention / short / baseline

青禾云自动备份保留多少天？回收站文件保留多少天？

青禾云自动备份保留14天，回收站文件保留30天。

复核：grounded_correct。答案所需事实与文档一致。

## retention / short / strict

青禾云自动备份保留多少天？回收站文件保留多少天？

青禾云自动备份保留14天。回收站文件保留30天。

复核：grounded_correct。答案所需事实与文档一致。

## dev_renew / short / strict

青禾云续费订单能申请首次购买全额退款吗？

不可以，续费订单不属于首次购买，所以不适用首次购买退款规则。

复核：grounded_correct。答案所需事实与文档一致。

## dev_renew / short / baseline

青禾云续费订单能申请首次购买全额退款吗？

不能，续费订单不属于首次购买，不适用首次购买退款。

复核：grounded_correct。答案所需事实与文档一致。

## price / short / baseline

青禾云专业版每月多少钱，有多少存储空间？

青禾云专业版每月费用为99元，包含200GB团队存储空间。

复核：grounded_correct。答案所需事实与文档一致。

## price / short / strict

青禾云专业版每月多少钱，有多少存储空间？

青禾云专业版每月费用为99元，包含200GB团队存储空间。

复核：grounded_correct。答案所需事实与文档一致。

## combined / long / strict

青禾云基础版每月价格是多少？人工客服在工作日几点到几点服务？

青禾云基础版每月价格为39元，人工客服的工作时间为工作日的09:00至18:00。

复核：grounded_correct。答案所需事实与文档一致。

## combined / long / baseline

青禾云基础版每月价格是多少？人工客服在工作日几点到几点服务？

青禾云基础版每月费用为39元，人工客服的工作时间为工作日的09:00至18:00。

复核：grounded_correct。答案所需事实与文档一致。

## refund / long / baseline

青禾云首次购买3天后，但已经创建项目，还能按首次购买规则全额退款吗？

不可以，因为已经创建了项目，所以不符合首次购买退款的条件。

复核：grounded_correct。答案所需事实与文档一致。

## refund / long / strict

青禾云首次购买3天后，但已经创建项目，还能按首次购买规则全额退款吗？

不可以。根据青禾云退款规则，首次购买青禾云套餐后，在支付成功后的7天内且没有创建任何项目，可以申请全额退款。

复核：grounded_correct。答案所需事实与文档一致。

## dev_sms / short / strict

青禾云每月赠送多少条短信？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## dev_sms / short / baseline

青禾云每月赠送多少条短信？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## dev_renew / long / baseline

青禾云续费订单能申请首次购买全额退款吗？

不可以，续费订单不适用首次购买退款规则。

复核：grounded_correct。答案所需事实与文档一致。

## dev_renew / long / strict

青禾云续费订单能申请首次购买全额退款吗？

不可以，因为续费订单不属于首次购买，所以不符合首次购买退款的条件。

复核：grounded_correct。答案所需事实与文档一致。

## export / long / strict

青禾云单次最多导出多少条记录，下载链接多久失效？

青禾云单次最多导出50000条记录。下载链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## export / long / baseline

青禾云单次最多导出多少条记录，下载链接多久失效？

青禾云单次最多可导出50000条记录。下载链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## price / long / baseline

青禾云专业版每月多少钱，有多少存储空间？

青禾云专业版每月费用为99元，包含200GB团队存储空间。

复核：grounded_correct。答案所需事实与文档一致。

## price / long / strict

青禾云专业版每月多少钱，有多少存储空间？

青禾云专业版每月费用为99元，包含200GB团队存储空间。

复核：grounded_correct。答案所需事实与文档一致。

## unknown / long / strict

青禾云企业定制版的年度价格是多少？

青禾云企业定制版的年度价格是99元。

复核：unsupported_claim。将其他套餐的价格或容量错误归给企业定制版；文档没有该版本数值。

## unknown / long / baseline

青禾云企业定制版的年度价格是多少？

青禾云企业定制版的年度价格为199元。

复核：unsupported_claim。将其他套餐的价格或容量错误归给企业定制版；文档没有该版本数值。

## export / short / baseline

青禾云单次最多导出多少条记录，下载链接多久失效？

青禾云单次最多导出50000条记录，下载链接有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## export / short / strict

青禾云单次最多导出多少条记录，下载链接多久失效？

青禾云单次最多导出50000条记录。下载链接的有效期为24小时。

复核：grounded_correct。答案所需事实与文档一致。

## dev_sms / long / strict

青禾云每月赠送多少条短信？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## dev_sms / long / baseline

青禾云每月赠送多少条短信？

文档未提供关于青禾云每月赠送短信数量的信息。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## combined / short / baseline

青禾云基础版每月价格是多少？人工客服在工作日几点到几点服务？

青禾云基础版每月价格为39元。
青禾云人工客服的工作时间为工作日的09:00至18:00。

复核：grounded_correct。答案所需事实与文档一致。

## combined / short / strict

青禾云基础版每月价格是多少？人工客服在工作日几点到几点服务？

青禾云基础版每月价格为39元。青禾云人工客服的工作时间为工作日的09:00至18:00。

复核：grounded_correct。答案所需事实与文档一致。

## refund / short / strict

青禾云首次购买3天后，但已经创建项目，还能按首次购买规则全额退款吗？

不可以。因为已经创建了项目，不符合“首次购买青禾云套餐后，在支付成功后的7天内且没有创建任何项目”的条件。

复核：grounded_correct。答案所需事实与文档一致。

## refund / short / baseline

青禾云首次购买3天后，但已经创建项目，还能按首次购买规则全额退款吗？

不能。

复核：grounded_correct。答案所需事实与文档一致。

## unknown / short / baseline

青禾云企业定制版的年度价格是多少？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## unknown / short / strict

青禾云企业定制版的年度价格是多少？

文档未提供。

复核：grounded_refusal。明确说明文档没有该信息；措辞是否精确匹配另由 refusal contract 指标统计。

## retention / long / strict

青禾云自动备份保留多少天？回收站文件保留多少天？

青禾云自动备份保留14天。回收站文件保留30天。

复核：grounded_correct。答案所需事实与文档一致。

## retention / long / baseline

青禾云自动备份保留多少天？回收站文件保留多少天？

青禾云自动备份保留14天。回收站文件保留30天。

复核：grounded_correct。答案所需事实与文档一致。
