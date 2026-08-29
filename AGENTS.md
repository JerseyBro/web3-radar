# AGENTS.md - Unified for Codex / OpenCode / Claude Code / Cursor

## Goal
Web3 Intelligence Radar（当前版本 **v0.1.0**，Minimum Usable Release）。

## 原则
- Simple > Fancy
- Low Cost（月 AI 预算 ≤ $5）
- Signal > Coverage
- Config First
- Deterministic Before AI
- Fail Gracefully（单源失败隔离）
- Traceable（保留 Source URL）
- Security First（Secret 只从环境变量 / GitHub Secrets 读取，禁止输出原文）

## Before Modify
先读：
- README
- 相关 docs/（QUICK_START / USER_GUIDE / OPERATIONS / MAINTENANCE / TROUBLESHOOTING / SOURCES / COST_CONTROL / LARK_SETUP / GITHUB_ACTIONS / RELEASE）
- config/
- tests/

## Do Not
- 不随便引入数据库（PG / Redis / VectorDB）
- 不引入消息队列 / 微服务
- 不引入 LangChain / CrewAI 等重型 Agent 框架
- 不绕过网站 paywall / login / robots 限制
- 不提交 Secret（.env / 真实 webhook / signing secret）
- 不扩大 v0.1 Scope（不加 Wallet / 不大规模加 Source / 不解决全部 Google Play / 不接 X API / 不做 Dashboard）

## 版本
唯一来源：`pyproject.toml` 的 `version`（0.1.0）。勿多文件手工维护。

## 提交前
- `python run_tests.py` FAILED=0
- `python -m radar doctor` READY / BLOCKED_BY_CONFIGURATION
- 不提交 Secret

## 项目结构
- collectors/ 采集
- pipeline/ 标准化/去重/聚类/评分/AI
- radars/ 两条雷达编排
- outputs/ 飞书推送
- storage/ 本地文件存储
- prompts/ 报告模板
- config/ 配置化阈值/模型/数据源

## 开发约束
- Python 3.12, 依赖见 pyproject.toml，不随意新增重型框架
- 不使用 Playwright / LangChain
- 不绕过付费墙/robots
- 测试后交付：pytest 覆盖 normalize/dedupe/score/cost_guard/lark 等

## 常见任务
- 加 Source: 改 config/sources.yaml
- 调权重: 改 config/scoring.yaml
- 调模型: 改 config/models.yaml
- Dry Run: python -m radar scan --dry-run --no-ai

## Secret Policy

Agent MAY:
- check secret presence
- use secrets for approved commands
- sync secrets to GitHub
- report CONFIGURED / MISSING

Agent MUST NOT:
- print secrets
- cat secret files
- echo secrets
- print all environment variables
- commit .env
- log webhook URLs
- store secrets in docs
- store secrets in reports
- store secrets in artifacts

Secret Source of Truth:
- macOS Keychain for local
- GitHub Secrets for Actions

## v0.1 Development Freeze

Web3 Intelligence Radar v0.1 and Jersey Secret Bootstrap v0.1 are feature-frozen.

Allowed:
- P0 critical fixes
- P1 blocking bug fixes
- tests required for those fixes
- minimal documentation corrections

Not allowed:
- new features
- speculative refactors
- architecture expansion
- new infrastructure
- new sources without production evidence
- unrelated cleanup

P2/P3:
→ docs/V0.2_BACKLOG.md

Rule:
Smallest Safe Fix.
Validation before expansion.
Do not enter v0.2 without explicit user approval.

## 提交
- 小步提交，说明变更与验证结果
