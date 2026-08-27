# Cost Control

AI 成本控制手册。

## 什么产生费用

- OpenAI API 调用（Classifier / Synthesis）

## 什么不产生 AI Token

- Collector、Normalize、Filter、Dedupe、Cluster、本地 Score
- 这些是确定性逻辑，优先于 AI

## 模型

- `classifier.primary: gpt-5.6-luna` → 分类 / 打分 / 摘要
- `synthesis.primary: gpt-5.6-terra` → 周报合成（fallback `gpt-5.6-luna`）
- Deep model 默认关闭

## 预算

- `MONTHLY_AI_BUDGET_USD=5`
- `MAX_AI_CALLS_PER_RUN=20`

## Cost State

- `storage/state/cost.json` 保存月度累计费用、调用次数、token 数
- 跨 Run 累加（持久化在 `radar-state` 分支）

## Month Rollover

- 进入新月份（`YYYY-MM` 变化）自动清零重新开始，不破坏 seen / deliveries / clusters

## 预算超限后发生什么

- 停止非必要 AI 请求
- Candidate 保留（确定性 pipeline 继续）
- 日志打印明确 WARNING
- pipeline 不崩溃

## 如何提高预算

- 改 `config/models.yaml` 的 `monthly_ai_budget_usd`
- 或环境变量 `MONTHLY_AI_BUDGET_USD`

## 如何降低成本

- 提高确定性评分权重占比
- 限制 `max_weekly_input_events`（默认 80）
- 仅对 score ≥ 40 的候选调用 AI
