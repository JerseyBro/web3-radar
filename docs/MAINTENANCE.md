# Maintenance

开发维护手册。

## 目录

- `collectors/` 采集（RSS / Web / GitHub / AppStore / GooglePlay / DeFiLlama / CoinGecko）
- `pipeline/` 标准化 / 去重 / 聚类 / 评分 / AI 分析 / 成本守卫
- `radars/` 两条 Radar 编排
- `prompts/` 报告模板
- `outputs/` 输出适配器（base / router / lark / local_http / file）
- `storage/` 状态与 git_state
- `config/` 配置（sources / scoring / models / settings）
- `tests/` 测试

## 如何加 Source

编辑 `config/sources.yaml`：
- industry：加 RSS / GitHub 项，指定 `type` 与 `credibility`
- competitor：在 `wallets` 加一项（official_website / blog / github / app_store_name / google_play_id），
  然后 `python -m radar resolve` 刷新 `resolved_sources.json`

## 如何加 Wallet

见上，加入 `competitor.wallets`。Resolver 会解析 App Store / Google Play ID；
无法可靠匹配则标记 `unresolved`，不误绑同名 App。

## 如何修改评分

`config/scoring.yaml`：调整 industry / competitor 权重与阈值。

## 如何修改 Prompt

`prompts/industry.md` / `prompts/competitor.md`。不要弱化要求的结构（Money Flow / Narrative / Technology / Wallet Opportunities 等）。

## 如何修改模型

`config/models.yaml`：
```yaml
classifier: {primary: gpt-5.6-luna, fallback: null}
synthesis:  {primary: gpt-5.6-terra, fallback: gpt-5.6-luna}
```
fallback 时必须打印 `MODEL_FALLBACK`（from/to/reason），禁止静默切 gpt-4o-mini。

## 如何修改 Schedule

`.github/workflows/weekly.yml` 的 cron（UTC）。Asia/Shanghai 周五 08:20 = `20 0 * * 5`。

## 如何修改 Budget

`config/models.yaml` 的 `monthly_ai_budget_usd` / `max_ai_calls_per_run`，或环境变量 `MONTHLY_AI_BUDGET_USD` / `MAX_AI_CALLS_PER_RUN`。

## 如何修改 Lark

`outputs/lark.py`；错误类型见 `DeliveryError`；签名见 `_sign`（Feishu HMAC-SHA256）。

## 如何修改 State Schema

所有 state 文件带 `schema_version`。新增/修改字段时递增版本并在 `_load` 中兼容旧结构（缺失/损坏自动初始化）。

## 修改后需要跑哪些测试

```bash
python run_tests.py
python -m radar doctor
```

## Commit 前检查

- 不提交 `.env` / 真实 Secret
- `run_tests.py` FAILED=0
- 不扩大 v0.1 Scope
