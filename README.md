# Web3 Intelligence Radar

面向 Web3 Wallet 团队的低成本 AI 情报雷达。把公开 Web3 数据经过
采集 → 标准化 → 去重 → 聚类 → 评分 → AI 分析 → 情报报告 → Lark / 本地 HTTP，
转化为真正可用的团队情报。

当前版本：**v0.1.0（Minimum Usable Release）**。

## 两条 Radar

- **Industry Intelligence**：行业动态、Narrative、Money Flow、TVL、Wallet、DeFi、AA 等。
- **Competitor Intelligence**：10 款 Wallet 的 App Store / Blog / GitHub 变化，过滤 bug fixes，只报战略/技术/交易能力变化。

## 核心原则

- High Signal / Low Noise
- Low Cost（月 AI 预算 ≤ $5）
- Traceable（每个结论保留 Source URL）
- Maintainable（配置化、单源失败隔离、无重型框架）

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

## Quick Start

→ [docs/QUICK_START.md](docs/QUICK_START.md)（5–10 分钟第一次运行）

## Documentation

- [Quick Start](docs/QUICK_START.md)
- [User Guide](docs/USER_GUIDE.md)
- [Operations](docs/OPERATIONS.md)
- [Maintenance](docs/MAINTENANCE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Sources](docs/SOURCES.md)
- [Cost Control](docs/COST_CONTROL.md)
- [Lark Setup](docs/LARK_SETUP.md)
- [GitHub Actions](docs/GITHUB_ACTIONS.md)
- [Release](docs/RELEASE.md)
- [Parallel Run](docs/PARALLEL_RUN.md)
- [v0.1 Release Checklist](docs/V0.1_RELEASE_CHECKLIST.md)

## Production Bootstrap

```bash
./scripts/bootstrap.sh              # 一键引导
./scripts/with-secrets.sh <command>  # 从 Keychain 注入 Secret 执行
./scripts/production-check.sh        # 生产就绪检查
```

详细：[docs/SECRET_BOOTSTRAP.md](docs/SECRET_BOOTSTRAP.md)

## 当前版本

**v0.1.0**

## Known Limitations

- Google Play 部分钱包 unresolved（解析受限）
- 部分 competitor source 不完整（依赖 App Store / 已知 GitHub）
- X API 未接入
- 真实 OpenAI / Lark 调用需在配置密钥后由 GitHub Actions 或本机执行
