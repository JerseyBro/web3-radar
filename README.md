# Web3 Intelligence Radar

> High-signal, low-noise Web3 intelligence radar for industry trends and wallet competitor monitoring.

面向 Web3 Wallet 团队的低成本 AI 情报雷达。把公开 Web3 数据经过采集 → 标准化 → 去重 → 聚类 → 评分 → AI 分析 → 情报报告 → Lark / 本地 HTTP，转化为真正可用的团队情报。

当前版本：**v0.1.0（Minimum Usable Release）**。

## What It Does

- **Industry Intelligence** — 行业动态、Narrative、Money Flow、TVL、Wallet 基础设施、DeFi、AA/CA 等。回答：发生了什么、为什么重要、对 Wallet 意味着什么。
- **Competitor Intelligence** — 10 款 Wallet（Bitget / OKX / UniversalX / TokenPocket / Solflare / Zerion / Rabby / UXUY / Exodus / Phantom）的 App Store / Blog / GitHub 变化，过滤 bug fixes，只报战略/技术/交易能力变化。

## Current Status

**v0.1 Development Freeze** — 功能已冻结，当前处于生产配置与验证阶段。

```
Configuration  →  Smoke Test  →  Production E2E  →  Trial Run  →  v0.1.0 Release
     ↑ you are here
```

详见 [docs/V0.1_DEVELOPMENT_FREEZE.md](docs/V0.1_DEVELOPMENT_FREEZE.md) 与 [docs/V0.2_BACKLOG.md](docs/V0.2_BACKLOG.md)。

## First Time Here?

```bash
git clone https://github.com/JerseyBro/web3-radar.git
cd web3-radar
```

然后阅读 **[docs/QUICK_START.md](docs/QUICK_START.md)** — 30 分钟完成安装、配置、本地验证与第一次手动运行。

## Common Commands

```bash
./scripts/acceptance.sh                            # 一键验收（Basic）
./scripts/acceptance.sh --e2e                      # 一键验收（含 Production E2E）
./scripts/bootstrap.sh                              # 一键引导（NO AI CALL / NO LARK PUSH）
./scripts/secrets-doctor.sh                         # 健康检查
./scripts/production-check.sh                       # 生产就绪检查

python -m radar doctor                              # 环境与配置诊断
python -m radar scan --no-ai                        # 无 AI 采集链路验证
python -m radar industry --weekly                   # Industry 周报（预览，不外发）
python -m radar industry --weekly --push            # Industry 周报（真发 Lark）
python -m radar competitor --weekly --push          # Competitor 周报（真发 Lark）
./scripts/with-secrets.sh python -m radar ai-test   # OpenAI 连通性
```

> `--push` 才真发 Lark；不传 `--push` 为预览（PREVIEW）。

## 一键验收

```bash
./scripts/acceptance.sh
./scripts/acceptance.sh --e2e
```

可选：`--no-ai`、`--no-push`。

## Architecture

```
Collectors
  ↓
Normalize → Filter → Dedupe → Cluster → Score
  ↓
AI (Classifier / Synthesis, structured output)
  ↓
Report (Markdown + JSON)
  ↓
Lark / Local HTTP / File
```

跨 Run 状态保存在专用 git 分支 `radar-state`（seen / clusters / cost / deliveries / resolved）。

## 核心原则

- High Signal / Low Noise
- Low Cost（月 AI 预算 ≤ $5）
- Traceable（每个结论保留 Source URL）
- Maintainable（配置化、单源失败隔离、无重型框架）

## Documentation

| 你现在想做什么 | 去哪里 |
|---|---|
| 第一次使用，跑起来 | [QUICK_START](docs/QUICK_START.md) |
| 已安装，日常怎么用 | [USER_GUIDE](docs/USER_GUIDE.md) |
| 系统出问题 | [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) |
| 日常巡检 / Actions 状态 | [OPERATIONS](docs/OPERATIONS.md) |
| 改 Source / Wallet / Model / Prompt | [MAINTENANCE](docs/MAINTENANCE.md) |
| 配 Secret / 换 Key | [SECRET_BOOTSTRAP](docs/SECRET_BOOTSTRAP.md) |
| Lark 机器人怎么建 | [LARK_SETUP](docs/LARK_SETUP.md) |
| 数据源有哪些 | [SOURCES](docs/SOURCES.md) |
| AI 花了多少钱 | [COST_CONTROL](docs/COST_CONTROL.md) |
| GitHub Actions 怎么跑 | [GITHUB_ACTIONS](docs/GITHUB_ACTIONS.md) |
| 怎么发版 | [RELEASE](docs/RELEASE.md) |
| 安全与 Secret 规范 | [SECURITY](docs/SECURITY.md) |
| 冻结了什么 / 什么能改 | [V0.1_DEVELOPMENT_FREEZE](docs/V0.1_DEVELOPMENT_FREEZE.md) |
| v0.2 候选 | [V0.2_BACKLOG](docs/V0.2_BACKLOG.md) |
| 试运行记录 | [V0.1_TRIAL_RUN](docs/V0.1_TRIAL_RUN.md) |
| 并行运行（首周） | [PARALLEL_RUN](docs/PARALLEL_RUN.md) |
| 发版检查清单 | [V0.1_RELEASE_CHECKLIST](docs/V0.1_RELEASE_CHECKLIST.md) |

## 当前版本

**v0.1.0**（未 Tag，待 Production E2E 通过）

## Known Limitations

- Google Play 部分钱包 unresolved（解析受限，不误绑）
- 部分 competitor source 覆盖不完整（依赖 App Store / 已知 GitHub / Blog / 官网）
- X API 未接入
- 真实 OpenAI / Lark 调用需配置密钥后由 GitHub Actions 或本机执行
