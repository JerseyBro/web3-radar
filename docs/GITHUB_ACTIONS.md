# GitHub Actions

自动任务手册。

## scan.yml — Radar Scan

- 调度：每 4 小时（`0 */4 * * *`）
- 作用：采集 + 评分 + 跨 Run State 更新（**scan != push**，多数扫描不推 Lark）
- 支持 `workflow_dispatch`：`radar` / `mode`(scan|dry-run) / `push`(默认 false)

## weekly.yml — Weekly Reports

- Industry：Asia/Shanghai 周五 08:20（UTC `20 0 * * 5`）
- Competitor：Asia/Shanghai 周五 08:35（UTC `35 0 * * 5`）
- 调度运行自动 `--push`
- `workflow_dispatch`：`radar` / `mode`(weekly|dry-run) / `output` / `push`(默认 false)

## schedule 与 UTC

GitHub cron 使用 UTC。Asia/Shanghai = UTC+8，所以周五 08:20 = UTC 周五 00:20。

## workflow_dispatch 参数

- `radar`: industry | competitor | all
- `mode`: scan | weekly | dry-run
- `output`: file,lark,local-http（逗号分隔）
- `push`: 默认 false（安全，不默认发群）

## radar-state

- 每次运行：`pull radar-state → 运行 → 原子更新 → commit → push radar-state`
- 分支保存 seen / clusters / cost / deliveries / resolved

## 权限

```yaml
permissions:
  contents: write
```
必需，否则 state 无法 push。

## concurrency

```yaml
concurrency:
  group: web3-radar-state
  cancel-in-progress: false
```
串行执行，避免两个 workflow 同时改 state；冲突自动 retry，禁止 force push。

## timeout

关键 Job `timeout-minutes: 30`，防止 Collector 异常长期占用。

## artifact

每次运行上传 Markdown + JSON 报告（保留 30 天），不含 `.env` / Secret。
