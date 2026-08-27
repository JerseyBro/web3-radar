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

## GitHub Actions
- `scan.yml` 每 4 小时采集一次（scan != push，多数扫描不推 Lark）
- `weekly.yml` 周五 08:20/08:35 Asia/Shanghai 推周报（cron 已转 UTC）
- 支持 `workflow_dispatch` 参数 `radar` / `mode`

## 成本模型
分类模型 gpt-5.6-luna，报告模型 gpt-5.6-terra。不可用时 fallback 到 gpt-4o-mini。每次请求记录 tokens/cost，预算内按得分排序截断输入事件。

## 增加新 Wallet
在 `config/sources.yaml` 的 `competitor.wallets` 加一项，包含 official_website / blog / github / app_store_name / google_play_id。然后运行 resolver 更新 `storage/state/resolved_sources.json`。

## 增加新 Source
在 `config/sources.yaml` industry 中加 RSS 或 GitHub 项，指定 `type` 与 `credibility`。

## Troubleshooting
- 采集失败不阻断其他源（单源失败隔离）
- App Store 未解析标记 unresolved，不误绑同名 App
- Lark dry-run 查看 payload 不真发

## V1 不做
Dashboard / Redis / Kafka / Postgres / VectorDB / 付费 X API 等，见 AGENTS.md。
