# Web3 Intelligence Radar

面向 Web3 Wallet 团队的低成本 AI 情报雷达。公开数据 → 标准化 → 去重 → 聚类 → 评分 → AI 分析 → 情报报告 → 飞书。

## 为什么存在
过滤噪音，只推送高信号情报。月 AI 成本 ≤ $5，确定性逻辑优先，Source URL 可追溯。

## 两条 Radar
- **Industry**：Narrative / Money Flow / TVL / Wallet / DeFi / AA... 回答钱和用户往哪走，对 Wallet 意味着什么。
- **Competitor**：10 款 Wallet 的 App Store / GitHub / Blog 变化，过滤 bug fixes，只报战略/技术/交易能力变化。

## 架构
```
collectors (RSS/Web/GitHub/AppStore/DeFiLlama/CoinGecko)
  → normalize → filter(noise) → dedupe(exact+fuzzy) → cluster → score → analyze(AI) → report → Lark
Storage: storage/events/*.jsonl, storage/state/*.json, reports/*.md
```

## 安装
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 配置
```bash
cp .env.example .env
# 填 OPENAI_API_KEY, LARK_WEBHOOK_*
```

## 本地运行
```bash
python -m radar resolve               # 首次运行：解析 App Store / Google Play ID -> resolved_sources.json
python -m radar scan --dry-run
python -m radar industry --weekly --dry-run
python -m radar competitor --weekly --dry-run
python -m radar scan --no-ai          # 不调用 OpenAI，测试采集链路
```

## OpenAI 配置
`config/models.yaml` 配置模型与预算。`MONTHLY_AI_BUDGET_USD=5`，`MAX_AI_CALLS_PER_RUN=20`，超预算自动停止 AI 调用，pipeline 不崩。

## 飞书配置
`LARK_WEBHOOK_INDUSTRY` / `LARK_WEBHOOK_COMPETITOR`，可选 `LARK_SIGNING_SECRET_*`。

## Push 到 Lark（V1.1）
默认**关闭外部推送**，必须显式 `--push` 才真正发送；`--dry-run` 永远禁止外发。
```bash
python -m radar industry --weekly --output lark --push
python -m radar competitor --weekly --output lark --push
# Smoke Test（不发 Web3 数据，不发 OpenAI，仅极小测试卡）
python -m radar output-test --target lark --radar industry --push
```
- 支持 timeout / retry / exponential backoff / 签名 / 响应校验 / 错误分类（INVALID_WEBHOOK, SIGNATURE_ERROR, KEYWORD_REJECTED, IP_REJECTED, RATE_LIMIT, TIMEOUT, NETWORK_ERROR, INVALID_PAYLOAD, UNKNOWN）。
- HTTP 200 不等于成功，必须解析 Lark 返回的 `code` 字段。
- 幂等：同一 `target+report_id` 默认不重复发送，需 `--force-push` 才重发（防止 workflow retry 重复）。
- 错误分类 / webhook / secret **不进日志**。

## Push 到本地服务（Local HTTP，V1.1）
用于本地验证 Delivery，不绑定具体业务服务。
```bash
export LOCAL_WEBHOOK_URL="http://127.0.0.1:8787/api/radar"
export LOCAL_WEBHOOK_TOKEN="optional-bearer"
python -m radar receiver --host 127.0.0.1 --port 8787   # 轻量 Receiver（仅标准库）
python -m radar output-test --target local-http --radar industry --push
```
Receiver 支持 `GET /health` 与 `POST /api/radar`，收到数据存入 `storage/local-receiver/YYYY-MM-DD.jsonl`，控制台只打印 `timestamp/radar/event_type/title`，不打印敏感 header/token。

## GitHub Persistent State（V1.1）
GitHub Actions runner 是临时环境，**工作目录不会跨 Run 保留**。所有跨 Run 状态保存在专用分支 `radar-state`：
- 保存：`state/seen.json`（跨 Run 去重）、`clusters.json`、`cost.json`（月度预算累加）、`deliveries.json`（推送幂等）、`resolved_sources.json`。
- 每个 state 文件带 `schema_version`，缺失/损坏自动初始化，原子写入（`.tmp` + rename）。
- 流程：`checkout main → pull radar-state → 运行 pipeline → 原子更新 state → commit radar-state → push radar-state`。
- Workflow 加 `concurrency: group: web3-radar-state, cancel-in-progress: false`；push 冲突自动 retry，禁止 `--force`。
- 初始化：首次运行 `python -m radar scan`（无 `radar-state` 分支时自动创建），或手动 `git push -u origin radar-state`（从任意含 `storage/state/*.json` 的提交）。
- 恢复：删除本地 `storage/state/*.json` 后下次运行会自动从 `radar-state` 分支拉取。

## GitHub Actions
- `scan.yml` 每 4 小时采集一次（scan != push，多数扫描不推 Lark）
- `weekly.yml` 周五 08:20/08:35 Asia/Shanghai 推周报（cron 已转 UTC），调度运行自动 `--push`
- `workflow_dispatch`：`radar` / `mode`(weekly|dry-run) / `output` / `push`(默认 false)

## 成本模型
分类模型 `classifier.primary: gpt-5.6-luna`（`fallback: null`，无 AI 时保留确定性候选），报告模型 `synthesis.primary: gpt-5.6-terra`（`fallback: gpt-5.6-luna`）。任何 fallback 均打印 `MODEL_FALLBACK` 日志，**不静默切换**。月度预算 `MONTHLY_AI_BUDGET_USD=5` 存于 `cost.json`，跨 Run 累加，跨月自动 rollover；超预算停止 AI 但 pipeline 不崩。

## 增加新 Wallet
在 `config/sources.yaml` 的 `competitor.wallets` 加一项，包含 official_website / blog / github / app_store_name / google_play_id。然后运行 resolver 更新 `storage/state/resolved_sources.json`。

## 增加新 Source
在 `config/sources.yaml` industry 中加 RSS 或 GitHub 项，指定 `type` 与 `credibility`。

## Troubleshooting
- 采集失败不阻断其他源（单源失败隔离）
- App Store 未解析标记 unresolved，不误绑同名 App
- Lark dry-run 查看 payload 不真发
- state 跨 Run 异常：检查 `radar-state` 分支是否存在、GITHUB_TOKEN 是否有 `contents:write`

## Production Checklist
- [ ] 配置 GitHub Secrets：`OPENAI_API_KEY`、`LARK_WEBHOOK_INDUSTRY`、`LARK_WEBHOOK_COMPETITOR`（可选签名）
- [ ] 首次运行 `scan.yml` 以创建 `radar-state` 分支
- [ ] 运行 `python -m radar output-test --target lark --radar industry --push` 验证 Webhook/签名/卡片
- [ ] 确认 `config/settings.yaml` 中 `push.critical_enabled` 仍为 `false`（首周只开 Weekly）
- [ ] 确认 `weekly.yml` 调度自动 `--push`，`workflow_dispatch` 默认不推送
- [ ] 验证 Artifact 上传（报告 md/json），且不含 `.env`/secret

## V1.1 已知限制
- 真实 OpenAI 调用未在本机验证（无 key/网络），逻辑通过 fallback + 单元测试覆盖
- Google Play 解析在本环境被反爬/超时，标记 unresolved（生产 CI 可能可用）
- 竞品 GitHub 采用「组织+常见仓库名」猜测，部分 404（不阻断）
- `radar-state` 分支需首次 CI 运行后创建

## V1 不做
Dashboard / Redis / Kafka / Postgres / VectorDB / 付费 X API 等，见 AGENTS.md。
