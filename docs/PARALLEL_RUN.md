# Parallel Run

第一周并行运行手册。

## 背景

旧的 Lark App Update Bot 继续运行；新的 Radar 同时运行，对比效果。

## 运行

- Industry：Friday Asia/Shanghai 08:20
- Competitor：Friday Asia/Shanghai 08:35
- 首周：`push.critical_enabled=false`（只开 Weekly，不自动发 Critical）

## 记录指标

- 旧机器人消息数量
- 新 Radar 推送数量
- 重复率 / 噪声率 / 有效 Signal / 漏报 / 误报
- 阅读时间
- Opportunity 数量

## 首周开发冻结

只修：
- Crash
- Delivery Failure
- State Failure
- Cost Bug
- 严重 Parser Bug

不立即大改：
- Prompt 不完美
- 分数偏差
- Source 漏报
- 内容略长

记录到 `docs/V0.1_PARALLEL_RUN_NOTES.md`。

## Week 1 后

进入 `v0.2 Signal Quality`，重点：
- scoring
- Prompt
- noise
- source quality
