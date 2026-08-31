# Operations

> 适合谁：系统已在运行，需要知道“平时怎么管、怎么判断正常、Actions 怎么用”。
> 看完能做什么：完成每周/每月巡检、判断一次运行是否健康、处理常见运行问题。

---

## 正常运行长什么样

**单次 Weekly 运行的健康日志：**

```
[industry weekly] sources=12 failed=2 raw=140 dup=8 noise=60 candidates=12 ai_calls=5 ai_cost=$0.12 monthly=$1.20 critical=0
```

健康标准：

- `sources` 有数，`failed` < 50%（单源失败隔离，不影响其他源）
- `candidates` 非 0（有周报候选）
- `ai_calls` ≤ `max_ai_calls_per_run`（默认 20）
- `monthly` 远低于预算（默认 $5）
- 无 `WARN: MONTHLY BUDGET EXCEEDED`
- `reports/YYYY-WW-*.md` + `.json` 已生成
- 有 `--push` 时 Lark 群收到卡片；无 `--push` 时日志含 `PREVIEW`

**State 健康：** `storage/state/cost.json` 月度累计正常增长；远端 `radar-state` 分支有新 commit。

---

## 每周检查（5 分钟）

| 检查项 | 怎么看 |
|--------|--------|
| Workflow 状态 | Actions 页面是否全绿 |
| Lark 是否收到卡片 | 群内 `📡` / `👛` 卡片 |
| 报告是否生成 | `reports/` 有新 md + json；Actions Artifact 可下载 |
| Source 失败比例 | 日志 `sources_failed` 是否异常增高 |
| AI 费用 | 日志 `monthly=$X.XX` 或 `storage/state/cost.json` |
| Lark 投递 | 无 `DeliveryError`；幂等生效 |

---

## 每月检查（15 分钟）

| 检查项 | 怎么看 |
|--------|--------|
| AI 月成本 | `cost.json` → `monthly_cost_usd`（是否有 rollover） |
| Source Health | 连续多周 `failed` 的源 → 考虑更新 URL（见 [MAINTENANCE](MAINTENANCE.md)） |
| storage 增长 | `storage/events/` 保留 6 个月自动 rotate；`storage/state/` 极小 |
| radar-state 分支 | `git log origin/radar-state --oneline -5` 有 commits |
| Actions 用量 | 仓库 Settings → Actions 用量（避免超限） |
| Secret 健康 | `./scripts/secrets-doctor.sh` |
| 依赖 | `pip list --outdated`（见下方维护） |

---

## 手动重跑

**一键验收：**

```bash
./scripts/acceptance.sh
./scripts/acceptance.sh --e2e
```

可选：`--no-ai`、`--no-push`。

**GitHub Actions：** 仓库 → Actions → 选择 `Radar Scan` 或 `Weekly Reports` → **Run workflow**

参数：

| 参数 | 选项 | 说明 |
|------|------|------|
| `radar` | `industry` / `competitor` / `all` | 默认 `all` |
| `mode` | `scan` / `weekly` / `dry-run` | `dry-run` 永不外发、不写 state |
| `push` | `true` / `false` | 默认 `false`（安全）；调度运行时自动 `true` |
| `output` | `file,lark,local-http` | 仅 Weekly 有此参数，默认 `lark` |

> 调度（schedule）运行时 `push` 自动为 `true`；手动 `workflow_dispatch` 需显式 `push=true` 才真发 Lark。

**本地重跑：**

```bash
./scripts/with-secrets.sh python -m radar industry --weekly --output file --push
./scripts/with-secrets.sh python -m radar competitor --weekly --output file --push
./scripts/with-secrets.sh python -m radar scan --output file --push
```

---

## GitHub Actions 要点

**Scheduled vs Manual：**

- Scheduled：按 cron 自动触发，已验证配置后自动 `--push`
- Manual（workflow_dispatch）：默认 `push=false`，需显式开启

**Workflow 文件：** `.github/workflows/scan.yml`（每 4 小时 `0 */4 * * *`）/ `weekly.yml`（周五 `20 0 * * 5` / `35 0 * * 5` UTC）

**cron 时区：** GitHub cron 用 UTC，Asia/Shanghai = UTC+8 → 周五 08:20 = UTC 周五 00:20。

**权限：** `permissions: contents: write` 必须，否则 `radar-state` 无法 push（见 [TROUBLESHOOTING](TROUBLESHOOTING.md)）。

**concurrency：** `group: web3-radar-state, cancel-in-progress: false` — 所有写 state 的 Job 串行，冲突自动 retry，禁止 force push。

**timeout：** `timeout-minutes: 30` — 防止 Collector 异常长期占用。

**artifact：** Weekly 保留 30 天（`reports/*-industry.*` / `*-competitor.*`），Scan 保留 14 天（`reports/*.json`）。

**失败后先看哪里：** Actions 日志 → 失败 Step 的输出；常见为缺 Secret 或 `contents: write` 未开。

---

## State 说明

| 位置 | 内容 | 持久化 |
|------|------|--------|
| 本地 `storage/state/*.json` | seen / cost / deliveries / resolved / clusters | 临时 |
| 远端 `radar-state` 分支 | 同上 | 权威 |

每次运行：`pull radar-state → 运行 → 原子更新 → commit → push radar-state`。

本地 state 可随时重建：

```bash
rm storage/state/*.json   # 清空本地
# 下次运行自动从 radar-state 拉取恢复
```

> `storage/events/*.jsonl` 保留最近 6 个月；`storage/local-receiver/*.jsonl` 仅本地测试。

---

## Lark 故障

```bash
./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push
```

看返回错误类型 → [TROUBLESHOOTING](TROUBLESHOOTING.md) 对应章节。临时不传 `--push` 仍可生成报告文件（File Output 永远落盘）。

---

## OpenAI 故障

- 费用超限：Cost Guard 自动停止 AI，pipeline 不崩，保留确定性候选。
- Key 失效：`ai-test` 报 API 错误；修复后 `./scripts/secrets-set-keychain.sh` + `secrets-sync-github.sh`。

---

## 日志速查

- `sources=12 failed=2` — 采集覆盖与失败
- `raw=140 dup=8 noise=60 candidates=12` — Pipeline 各阶段数量
- `ai_calls=5 ai_cost=$0.12 monthly=$1.20` — AI 成本
- `WARN: MONTHLY BUDGET EXCEEDED` — 预算超限
- `MODEL_FALLBACK from=... to=... reason=...` — 模型降级
- `PREVIEW: payload built but NOT sent` — 未传 `--push`
