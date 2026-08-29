# Maintenance

> 适合谁：三个月后重新打开项目的开发者 / Agent。
> 看完能做什么：知道 Source / Wallet / Model / Prompt / State / Secret / Workflow / Cost 分别在哪里、怎么安全地改。

**v0.1 Development Freeze 生效中** — 见 [V0.1_DEVELOPMENT_FREEZE](V0.1_DEVELOPMENT_FREEZE.md)。非 P0/P1 不改业务代码；新 Source / 新 Wallet 默认进 [V0.2_BACKLOG](V0.2_BACKLOG.md)。

---

## 目录

| 维护对象 | 配置位置 | 说明 |
|----------|----------|------|
| Source | `config/sources.yaml` | Industry RSS / GitHub / DeFi；Competitor 钱包列表 |
| Wallet | `config/sources.yaml` → `competitor.wallets` | 10 钱包，App Store / Google Play / Blog / GitHub |
| 评分 | `config/scoring.yaml` | 权重与阈值 |
| 模型 | `config/models.yaml` | classifier / synthesis / pricing / budget |
| Prompt | `prompts/industry.md` / `prompts/competitor.md` | 周报模板 |
| State | `storage/state/*.json` + 远端 `radar-state` 分支 | `StateStore` + `git_state` |
| Lark | `outputs/lark.py` | Delivery / 签名 |
| Secret | `scripts/` + macOS Keychain + GitHub Secrets | 见 [SECRET_BOOTSTRAP](SECRET_BOOTSTRAP.md) |
| Workflow | `.github/workflows/scan.yml` / `weekly.yml` | Schedule / concurrency / artifacts |
| 成本 | `config/models.yaml` + `pipeline/cost_guard.py` + `storage/state/cost.json` | Budget / CostGuard |

---

## Source Maintenance

**配置：** `config/sources.yaml`

- Industry：加 RSS / GitHub / DeFiLlama / CoinGecko 项，指定 `type` 与 `credibility`
- Competitor：在 `competitor.wallets` 加一项（`official_website` / `blog` / `github` / `app_store_name` / `google_play_id`）

**新增/修改 Source 的安全流程：**

1. 验证 URL 可访问
2. 验证 Collector 能抓到内容
3. 验证 Normalize / Dedupe / Score 正确
4. `python -m radar scan --no-ai --dry-run` 本地验证
5. 再进入 Production

> **Freeze 约束：** 新 Source 默认进 `docs/V0.2_BACKLOG.md`，除非 P0/P1。

---

## Wallet Maintenance

**配置：** `config/sources.yaml` → `competitor.wallets`

当前 10 钱包：Bitget Wallet / OKX Wallet / UniversalX / TokenPocket / Solflare / Zerion / Rabby Wallet / UXUY / Exodus / Phantom。

**如何修：**

- App Store ID 不对 → 改 `app_store_name`，然后 `python -m radar resolve`
- Google Play ID 不对 → 改 `google_play_id`，再 `resolve`
- 官网/Blog 变了 → 改 `official_website` / `blog`
- GitHub 组织变了 → 改 `github`

Resolver 结果写入 `storage/state/resolved_sources.json`（位于 `radar-state` 分支），包含 `resolved` / `unresolved` 状态。

> 新增第 11 个 Wallet 属于 v0.2，本轮不做。

---

## Model Maintenance

**配置：** `config/models.yaml`

```yaml
classifier: {primary: gpt-5.6-luna, fallback: null}
synthesis:  {primary: gpt-5.6-terra, fallback: gpt-5.6-luna}
monthly_ai_budget_usd: 5
max_ai_calls_per_run: 20
max_weekly_input_events: 80
```

- `classifier.primary` 为 null 或缺失时，不做 AI 分类，保留确定性候选。
- `synthesis` fallback 时必须打印 `MODEL_FALLBACK from=... to=... reason=...`，禁止静默切 `gpt-4o-mini`。

**修改模型前必须：**

```bash
./scripts/with-secrets.sh python -m radar ai-test
./scripts/with-secrets.sh python -m radar ai-test --model synthesis
# 检查 Cost：storage/state/cost.json
# 检查结构化输出：报告 md 是否含预期章节
```

不要直接改模型名就上线。

---

## Prompt Maintenance

**位置：** `prompts/industry.md` / `prompts/competitor.md`

- Industry：8 节（核心判断 / Top Signals / Money Flow / Narrative / Technology / Opportunities / Risks / Watch Next）
- Competitor：6 节（核心判断 / Top Moves / Direction / Technology / Opportunities / Watchlist）

Prompt 修改属于行为变化。Freeze 期间非 P0/P1 不改。未来修改必须记录：Why / Before / After / Expected Impact / Trial Result。不要建立复杂 Prompt Versioning System。

无 AI 时为 fallback 报告（标题 + `共 N 个信号事件` + Top 15 列表）。

---

## Cost Maintenance

**预算位置：** `config/models.yaml` → `monthly_ai_budget_usd` / `max_ai_calls_per_run`，或环境变量 `MONTHLY_AI_BUDGET_USD` / `MAX_AI_CALLS_PER_RUN`

**状态文件：** `storage/state/cost.json`（`monthly_cost_usd` / `calls` / `tokens`，跨 Run 累加，持久化在 `radar-state`）

**Month Rollover：** 进入新月份（`YYYY-MM` 变化）自动清零，不破坏 seen / deliveries / clusters。

**超预算后：** 停止非必要 AI，保留候选，日志 WARNING，pipeline 不崩。

**如何调整：** 改 `config/models.yaml` 或环境变量；提高 `max_weekly_input_events` 会增加输入事件数；仅 `score ≥ 40` 的候选会进入 AI。

---

## State Maintenance

**Local State：** `storage/state/*.json` — 本地临时，runner 重建即丢。

**radar-state Branch：** 权威持久化，保存 seen / clusters / cost / deliveries / resolved。每次运行：`pull → 运行 → 原子更新 → commit → push`。

**为什么不能只依赖 runner 本地：** GitHub Actions runner 每次全新环境，本地 state 会丢失。必须靠 `radar-state` 分支跨 Run 共享。

**如何判断正常：** `git log origin/radar-state --oneline -5` 有 commits；`cost.json` 月度累计增长；二次运行 seen 不回退。

**如何备份：** `git fetch origin radar-state && git log origin/radar-state -p > /tmp/radar-state-backup.log`

**corrupt state：** `StateStore` 加载时对缺失/损坏文件自动 reinit，无需手动干预。

**如需 Reset：**

```bash
# 风险：会导致 dedupe / seen / cost / deliveries 历史状态变化，需人工确认
rm storage/state/*.json
# 或远端：git push origin --delete radar-state  # 下次运行重建
```

---

## Lark Maintenance

**代码：** `outputs/lark.py`；错误类型见 `DeliveryError`；签名见 `_sign`（Feishu HMAC-SHA256）。

**修改后：**

```bash
./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push
```

---

## Secret Maintenance

不重复 [SECRET_BOOTSTRAP](SECRET_BOOTSTRAP.md) 全文，只给操作入口：

| 操作 | 命令 |
|------|------|
| 换 Key | `./scripts/secrets-set-keychain.sh` → 覆盖 → `./scripts/secrets-sync-github.sh` → `./scripts/production-check.sh` |
| 删 Key | `./scripts/secrets-remove-keychain.sh` |
| 同步 GitHub | `./scripts/secrets-sync-github.sh` |
| 健康检查 | `./scripts/secrets-doctor.sh` |

> GitHub Secrets 是 write-only，不要尝试 reverse sync（GitHub → 本地）。

---

## GitHub Actions Maintenance

**文件：** `.github/workflows/scan.yml`（每 4 小时）/ `weekly.yml`（周五 08:20 / 08:35 Asia/Shanghai，UTC `20 0 * * 5` / `35 0 * * 5`）

**关键字段：** `permissions: contents: write` / `concurrency: group: web3-radar-state, cancel-in-progress: false` / `timeout-minutes: 30` / `artifacts`（Weekly 30 天，Scan 14 天）

修改 Schedule 时注意：GitHub cron 用 UTC，Asia/Shanghai = UTC+8。

---

## Dependency Maintenance

```bash
pip list --outdated
pip install -e .    # 按 pyproject.toml 重装
```

Python 3.12，不随意新增重型框架。不使用 Playwright / LangChain。

---

## Release Maintenance

见 [RELEASE](RELEASE.md)。版本唯一来源 `pyproject.toml` → `version`。

---

## v0.1 Freeze Policy

见 [V0.1_DEVELOPMENT_FREEZE](V0.1_DEVELOPMENT_FREEZE.md)。P0/P1 允许直接修复；P2/P3 → `V0.2_BACKLOG.md`；Smallest Safe Fix。

## 修改后必跑

```bash
python run_tests.py              # FAILED=0
python -m radar doctor           # READY / BLOCKED_BY_CONFIGURATION
```

- 不提交 `.env` / 真实 Secret
- 不扩大 v0.1 Scope
