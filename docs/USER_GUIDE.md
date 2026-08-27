# User Guide

正式使用手册。

## Industry Radar 是什么

监控 Web3 行业动态：Narrative、Money Flow、TVL、Wallet、DeFi、AA/CA、MPC/TEE/Passkey 等，
回答：发生了什么、为什么重要、钱和用户往哪走、对 Wallet 意味着什么、有什么 Opportunity。

## Competitor Radar 是什么

监控 10 款 Wallet（Bitget / OKX / UniversalX / TokenPocket / Solflare / Zerion / Rabby / UXUY / Exodus / Phantom）
的 App Store / Blog / GitHub 变化，过滤 bug fixes / performance improvements，只报战略/技术/交易能力变化。

## 每周什么时候运行

GitHub Actions 自动：
- Industry：Asia/Shanghai 周五 08:20（UTC `20 0 * * 5`）
- Competitor：Asia/Shanghai 周五 08:35（UTC `35 0 * * 5`）

调度运行自动 `--push`。

## Lark 会收到什么

Interactive Card：
- Industry：📡 Web3 Industry Intelligence（核心判断 / Top Signals / Money Flow / Narrative / Technology / Wallet Opportunities / Watch Next Week）
- Competitor：👛 Web3 Wallet Competitor Intelligence（核心判断 / Top Moves / Direction / Technology / Opportunities / Watchlist）

## 如何手动运行

```bash
python -m radar industry --weekly --output lark,file --push
python -m radar competitor --weekly --output lark,file --push
```

## 如何只跑 Industry / Competitor

```bash
python -m radar industry --weekly --output lark,file --push
python -m radar competitor --weekly --output lark,file --push
```

## 如何 Preview / Dry Run / No-AI

```bash
python -m radar industry --weekly --output lark          # 无 --push => PREVIEW，不发送
python -m radar industry --weekly --dry-run              # dry-run 永不外发
python -m radar scan --no-ai                             # 不调用 OpenAI
```

## 如何重发

默认同 `target+report_id` 幂等，不重复发送。需强制重发：

```bash
python -m radar industry --weekly --output lark,file --push --force-push
```

## 如何查看报告文件

```bash
reports/YYYY-WW-industry.md
reports/YYYY-WW-industry.json
reports/YYYY-WW-competitor.md
reports/YYYY-WW-competitor.json
```

GitHub Actions 也会上传为 Artifact（保留 30 天）。

## 如何查看 Source

`config/sources.yaml` 列出全部 Industry / Competitor 数据源与 credibility。

## 如何判断运行是否成功

- `python -m radar doctor` → READY
- GitHub Actions：Actions 页面每个 Job 绿色
- Lark 收到卡片
- `storage/state/cost.json` 有累计费用

## 如何查看 GitHub Actions

仓库 → Actions → 选择 `Radar Scan` 或 `Weekly Reports`。

## 如何关闭 Weekly

`config/settings.yaml` 设置 `push.weekly_enabled: false`（调度仍跑但不再外发）。

## 如何暂时关闭 Lark

不传 `--push`，或不配置 `LARK_WEBHOOK_*`。

## 未来如何开启 Critical

`config/settings.yaml` 把 `push.critical_enabled` 改为 `true`。V0.1 首周默认 `false`。
