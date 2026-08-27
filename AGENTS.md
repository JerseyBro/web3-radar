# AGENTS.md - Unified for Codex / OpenCode / Claude Code / Cursor

## 原则
- 简洁实用主义，V1 不过度工程化
- 先理解后修改，尽量小改动，配置优先
- 不要引入微服务/Redis/Kafka/PG/VectorDB
- 能用确定性逻辑的不调大模型
- 单源失败不阻断全局
- 所有结论保留 Source URL
- Secret 只从环境变量读取

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

## 提交
- 小步提交，说明变更与验证结果
