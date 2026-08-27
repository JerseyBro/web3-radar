# Operations

运维手册。

## 日常

GitHub Actions 自动运行，日常无需干预。

## 每周检查

- Workflow 状态（Actions 页面是否绿色）
- Lark 是否收到 Industry / Competitor 卡片
- `reports/` 是否生成 md + json
- Source failure 比例（`[radar] sources_failed=`）
- `storage/state/cost.json` 月累计费用是否接近预算

## 每月检查

- AI 月成本（`cost.json` monthly_cost_usd）
- Source failure ratio
- `storage/events/` / `storage/state/` 增长（自动 rotate，见下方）
- `radar-state` 分支健康（有 commits）
- GitHub Actions 用量（避免超限）

> 状态文件每月自动清理：`storage/events/` 保留最近 6 个月 jsonl。

## 手动重跑

Actions → 选择 workflow → `Run workflow`，参数：
- `radar`: industry | competitor | all
- `mode`: scan | weekly | dry-run
- `push`: 默认 false（安全）

## State 恢复

删除本地 `storage/state/*.json` 后，下次运行自动从 `radar-state` 分支拉取恢复。

## Lark 故障

1. `python -m radar output-test --target lark --radar industry --push` 看返回错误类型
2. 检查 webhook / signing secret / 群机器人权限
3. 临时不传 `--push` 仍可生成报告文件（File Output 永远落盘）

## OpenAI 故障

- 费用超限：Cost Guard 自动停止 AI，pipeline 不崩，保留确定性候选
- Key 失效：`ai-test` 会报 API 错误；修复密钥

## GitHub Actions 故障

- `contents: write` 被拒 → 仓库 Settings → Actions → 工作流权限改为 Read and write
- `radar-state` 冲突 → workflow 有 `concurrency` 串行 + 冲突 retry
