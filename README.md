# Web3 Intelligence Radar

> 可追溯的 Web3 产品与技术情报，面向独立开发者的人工决策。

把公开来源经过采集 → 标准化 → 去重 → 评分 → 可选 AI 分类 → 来源关联报告 → 飞书/文件，整理为“观察到什么、可能有什么影响、下一步如何验证”。报告提供研究线索，不构成投资建议。

当前工作分支在迭代 v0.2 独立开发者阅读体验；`pyproject.toml` 仍是未发布的 v0.1.0。真实模型/飞书/定时运行尚待配置后的端到端验收。

## What It Does

- **Industry** — 官方博客、EIP、媒体、DeFiLlama、CoinGecko 等公开信号；把产品/技术变化变成可验证的开发者候选。当前来源不能证明资金流向或商业机会。
- **Competitor** — 监控现有 10 款 Wallet 的公开产品变化；这是当前覆盖边界，不代表完整 Web3 产品版图。

## Current Status

用户已授权启动 v0.2 改造。当前仍需要真实 API、飞书和至少一周试运行数据来评估信号质量。剩余工作见 [v0.2 Backlog](docs/V0.2_BACKLOG.md)。

## First Time Here?

```bash
git clone git@github.com:JerseyBro/web3-radar.git
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
./scripts/with-secrets.sh python -m radar ai-test   # 当前 LLM Provider 连通性
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
AI Classifier（可选；模型建议需人工核查）
  ↓
确定性 Report (Markdown + JSON；AI 长文合成默认关闭)
  ↓
File → Lark 简报 / Local HTTP
```

跨 Run 状态保存在专用 git 分支 `radar-state`（seen / 有界候选缓存 / critical alerts / cost / deliveries / resolved）。周报将当次采集与窗口内已缓存候选合并。

## 核心原则

- High Signal / Low Noise
- Low Cost（月 AI 预算 ≤ $5）
- Traceable（区分原始证据、分析假设和待验证动作，保留 Source URL）
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

**v0.1.0**（未 Tag；v0.2 代码正在独立分支迭代）

## Known Limitations

- Google Play 部分钱包 unresolved（解析受限，不误绑）
- 部分 competitor source 覆盖不完整（依赖 App Store / 已知 GitHub / Blog / 官网）
- X API 未接入
- 当前仅跟踪公开内容和少量聚合指标；没有链上资金归因、用户需求或收入验证数据
- 飞书完整报告入口在 GitHub Actions 中指向运行页，需有仓库权限并下载 Artifact；本地运行直接读取 `reports/`
- 真实 LLM / Lark 调用需配置当前 `roles.*` 引用的 Provider 密钥后由 GitHub Actions 或本机执行
