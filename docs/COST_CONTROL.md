# Cost Control

AI 成本控制手册。

## 什么产生费用

- LLM Provider API 调用（Classifier；Synthesis 需显式开启）

## 什么不产生 AI Token

- Collector、Normalize、Filter、Dedupe、Cluster、本地 Score
- 这些是确定性逻辑，优先于 AI

## 模型

- `roles.classifier.primary: deepseek/deepseek-flash` → 分类 / 打分 / 摘要
- `roles.synthesis.primary: deepseek/deepseek-flash` → 可选周报长文合成；OpenAI GPT-6 Luna 可作为显式配置的 fallback
- `config/settings.yaml` 默认 `report.synthesis_enabled: false`，使用确定性、可追溯报告
- DeepSeek Flash 分类调用显式关闭默认思考模式

## 预算

- `MONTHLY_AI_BUDGET_USD=5`
- `MAX_AI_CALLS_PER_RUN=20`
- 当前默认价格：DeepSeek Flash 峰时非缓存 $0.30 输入 / $1.20 输出，OpenAI GPT-6 Luna $0.10 输入 / $0.50 输出（均按每百万 token）。价格会变化，改模型前核对官方文档。

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
- 当前角色的主模型或 fallback 若无价格，跳过该角色的正式 AI 调用；不能把未知费用计作 0 来放行
- 这是应用内 token 估算预算，服务商真实账单与重试费用可能有差异；如需硬上限，应在服务商账户另设限额

## 如何提高预算

- 改 `config/models.yaml` 的 `monthly_ai_budget_usd`
- 或环境变量 `MONTHLY_AI_BUDGET_USD`

## 如何降低成本

- 提高确定性评分权重占比
- 限制 `max_weekly_input_events`（默认 80）
- 仅对 score ≥ 40 的候选调用 AI

官方价格：[DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) / [OpenAI GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)。
