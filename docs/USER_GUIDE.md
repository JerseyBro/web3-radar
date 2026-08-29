# User Guide

> 适合谁：已按 [QUICK_START](QUICK_START.md) 完成安装与首次验证，现在想知道“到底怎么用”。
> 看完能做什么：理解两条 Radar 的能力边界、手动/自动运行方式、报告在哪里、怎么判断一次运行是否成功。

---

## 两条 Radar

### Industry Intelligence

关注 **Web3 行业**本身：Narrative、Money Flow、TVL、Chain Activity、Wallet 基础设施、DeFi、AA/CA、MPC/TEE/Passkey、稳定币、资本流向、产品与技术趋势。

核心问题：*发生了什么 → 为什么重要 → 钱和用户往哪走 → 对 Wallet 意味着什么 → 有什么 Opportunity。*

真实能力边界（以 `config/sources.yaml` + `prompts/industry.md` + `radars/industry.py` 为准）：

- Official Primary：Ethereum Blog、Ethereum EIPs、Solana Blog、Base Blog、WalletConnect Blog
- DeFi Data：DeFiLlama Chains、CoinGecko Trending
- Established Media：CoinDesk、Blockworks、The Block、Decrypt

> 不要期待已接入 X / Nansen / Arkham —— 这些在 v0.1 明确未接入（见 README Known Limitations）。

### Competitor Intelligence

监控 **10 款 Wallet** 的公开变化，只报战略/技术/交易能力变化，过滤 Bug fixes / Performance improvements：

| Wallet | App Store | Google Play | Blog / Website | GitHub |
|--------|-----------|-------------|----------------|--------|
| Bitget Wallet | `Bitget Wallet` | `com.bitkeep.wallet` | ✓ | ✓ |
| OKX Wallet | `OKX: Buy Bitcoin BTC & Crypto` | `com.okinc.okex.gp` | ✓ | ✓ |
| UniversalX | `UniversalX` | `app.universalx.mobile` | ✓ | — |
| TokenPocket | `TokenPocket - Crypto Wallet` | `vip.mytokenpocket` | ✓ | ✓ |
| Solflare | … | `com.solflare.mobile` | ✓ | ✓ |
| Zerion | … | `io.zerion.android` | ✓ | ✓ |
| Rabby Wallet | … | `com.debank.rabby` | ✓ | ✓ |
| UXUY | … | `com.uxuy.wallet` | ✓ | — |
| Exodus | … | `exodusmovement.exodus` | ✓ | — |
| Phantom | … | … | ✓ | ✓ |

> 完整 ID 见 `config/sources.yaml` → `competitor.wallets`。部分钱包（TokenPocket / Exodus / Phantom 等）Google Play 解析受限，标记为 `unresolved` 是正常的不误绑策略，不是故障。

真实采集能力：App Store（iTunes Search + 域名验证）、Google Play（包名可达性）、GitHub（组织/仓库猜测）、官网/Blog（RSS/Web）。以 `python -m radar resolve` 后的 `storage/state/resolved_sources.json` 为准。

---

## 手动运行

> 全部以 `python -m radar --help` 为准。核心命令只有以下几种。

### 只跑 Industry

```bash
# 预览（不外发，只落盘 reports/）
python -m radar industry --weekly --output file

# 真发 Lark + 落盘
./scripts/with-secrets.sh python -m radar industry --weekly --output lark,file --push
```

### 只跑 Competitor

```bash
python -m radar competitor --weekly --output file
./scripts/with-secrets.sh python -m radar competitor --weekly --output lark,file --push
```

### 全量 Scan（两条一起跑）

```bash
python -m radar scan --no-ai                              # 无 AI，验证链路
./scripts/with-secrets.sh python -m radar scan --output file --push
```

### 常用变体

```bash
# Dry-run：永不外发、永不写 radar-state
python -m radar industry --weekly --dry-run
python -m radar scan --dry-run

# No-AI：不调 OpenAI，保留确定性 Pipeline
python -m radar scan --no-ai

# 指定 Radar
python -m radar scan --radar industry --no-ai
python -m radar scan --radar competitor --no-ai

# 强制重发（绕过幂等）
./scripts/with-secrets.sh python -m radar industry --weekly --output lark,file --push --force-push

# 指定输出
python -m radar industry --weekly --output file            # 仅文件
python -m radar industry --weekly --output lark --push     # 仅 Lark
python -m radar industry --weekly --output local-http --push  # 仅本地 HTTP
python -m radar industry --weekly --output lark,file --push   # 同时
```

### 本地 HTTP 自测

```bash
# 终端 A：启动接收器
python -m radar receiver --host 127.0.0.1 --port 8787
# 终端 B：发送测试
python -m radar output-test --target local-http --radar industry --push
# 观察：终端 A 收到 canonical envelope；storage/local-receiver/ 有 jsonl
```

---

## 自动运行

GitHub Actions 两条 Workflow（见 [GITHUB_ACTIONS](GITHUB_ACTIONS.md)）：

| Workflow | 文件 | Schedule | 时区换算 |
|----------|------|----------|----------|
| Radar Scan | `scan.yml` | `0 */4 * * *`（每 4 小时） | UTC |
| Weekly Reports | `weekly.yml` | `20 0 * * 5` / `35 0 * * 5` | UTC = Asia/Shanghai 周五 08:20 / 08:35 |

- 调度运行自动 `--push`（真发 Lark）
- 手动 `workflow_dispatch` 默认 `push=false`（安全）

入口：仓库 → **Actions** → 选择 workflow → **Run workflow**。

---

## Reports 在哪里

```
reports/YYYY-WW-industry.md     # Industry 周报 Markdown
reports/YYYY-WW-industry.json   # Industry 周报 JSON（含事件数组）
reports/YYYY-WW-competitor.md
reports/YYYY-WW-competitor.json
```

GitHub Actions 也会上传为 Artifact（保留 30 天；Scan 为 14 天）。

---

## State 在哪里

| 位置 | 内容 | 说明 |
|------|------|------|
| 本地 `storage/state/*.json` | seen / cost / deliveries / resolved / clusters | 运行时读写 |
| 远端 `radar-state` 分支 | 同上 | `scan` / `weekly` 每次运行自动 `pull → 运行 → push` |
| `storage/events/*.jsonl` | 原始采集事件 | 保留 6 个月自动 rotate |
| `storage/local-receiver/*.jsonl` | 本地 HTTP 接收记录 | 仅本地测试 |

> runner 本地状态不可靠，必须依赖 `radar-state` 分支。删除本地 `storage/state/*.json` 后下次运行自动从远端恢复。

---

## 怎么判断一次运行是否成功

**本地：**

- 日志行：`[industry weekly] sources=12 failed=2 ... ai_calls=5 ai_cost=$0.12 ...`
- `python -m radar doctor` → **READY**
- `reports/` 有新 md + json
- 无 `--push` 时日志含 `PREVIEW: payload built but NOT sent`

**GitHub Actions：**

- Actions 页面 Job 全部绿色
- Artifact 可下载
- `radar-state` 分支有新 commit

**Lark：**

- 群收到 Interactive Card（`📡 Web3 Industry Intelligence` / `👛 Web3 Wallet Competitor Intelligence`）
- 未收到时先检查是否传了 `--push` 且 `push.weekly_enabled=true`（见 `config/settings.yaml`）

---

## 怎么阅读报告

真实结构以 `prompts/industry.md` / `prompts/competitor.md` 为准。合成（含 AI）时的章节：

**Industry（8 节）：** 本周核心判断 → Top Signals → Money Flow → Narrative Radar → Technology Radar → Wallet Opportunities → Risks → Watch Next Week

> 重点看：**Top Signals / Why It Matters / Technology Radar / Wallet Opportunities / Watch Next Week**

**Competitor（6 节）：** 本周核心判断 → Top Competitor Moves → Competitor Direction → Technology Changes → Opportunities For Us → Watchlist

> 重点看：**What Changed / Why It Matters / Strategic Signal / Technical Signal / Opportunities For Us**

无 AI（或 fallback）时为简化版：标题 + `共 N 个信号事件` + Top 15 事件列表（title / score / tier / Source URL）。

每个结论保留 Source URL，可追溯。

---

## Cost Guard

- `config/models.yaml`：`monthly_ai_budget_usd: 5` / `max_ai_calls_per_run: 20` / `max_weekly_input_events: 80`
- 也可用环境变量 `MONTHLY_AI_BUDGET_USD` / `MAX_AI_CALLS_PER_RUN` 覆盖
- 超预算后：停止非必要 AI，保留确定性候选，日志 WARNING，pipeline 不崩
- 月度自动 rollover（`YYYY-MM` 变化时清零）
- 查看：`storage/state/cost.json` 或日志 `monthly=$X.XX`

---

## 常用命令速查

| 我想做什么 | 命令 |
|---|---|
| 查看所有命令 | `python -m radar --help` |
| 健康检查 | `python -m radar doctor` |
| 无 AI 验证链路 | `python -m radar scan --no-ai` |
| Industry 预览 | `python -m radar industry --weekly --output file` |
| Industry 真发 | `./scripts/with-secrets.sh python -m radar industry --weekly --output lark,file --push` |
| Competitor 真发 | `./scripts/with-secrets.sh python -m radar competitor --weekly --output lark,file --push` |
| 全量 Scan | `./scripts/with-secrets.sh python -m radar scan --output file --push` |
| AI 连通性 | `./scripts/with-secrets.sh python -m radar ai-test` |
| AI synthesis | `./scripts/with-secrets.sh python -m radar ai-test --model synthesis` |
| Lark 烟雾测试 | `./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push` |
| 本地 HTTP 自测 | `python -m radar receiver` + `python -m radar output-test --target local-http --radar industry --push` |
| 解析 Wallet Source | `python -m radar resolve` |
| Secret 健康检查 | `./scripts/secrets-doctor.sh` |
| 生产就绪检查 | `./scripts/production-check.sh` |
| 一键引导 | `./scripts/bootstrap.sh` |
