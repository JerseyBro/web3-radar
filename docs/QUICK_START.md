# Web3 Intelligence Radar v0.1 Quick Start

> 适合谁：第一次打开这个仓库的人。
> 看完能做什么：30 分钟内完成安装、配置、本地验证与第一次手动运行。

---

## Prerequisites

| 依赖 | 要求 | 检查命令 |
|------|------|----------|
| macOS | 任意近期版本 | `sw_vers` |
| Git | 任意 | `git --version` |
| Python | **3.12**（`pyproject.toml` 要求 `>=3.12`） | `python3 --version` |
| GitHub CLI | 任意 | `gh --version` |
| OpenAI API Key | Project API Key | — |
| Lark Bot Webhook | 飞书群自定义机器人 | — |

> Python 必须 3.12。`3.11` 会在 `pip install -e .` 时直接报错。

检查：

```bash
python3 --version   # 需 3.12.x
git --version
gh --version
```

---

## Step 1 — Clone / Enter

```bash
git clone https://github.com/JerseyBro/web3-radar.git
cd web3-intelligence-radar
```

> 本地目录名 `web3-intelligence-radar` 与远端 `web3-radar` 不同，以 `git remote -v` 为准。

创建虚拟环境并安装：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

验证：

```bash
python -m radar --help
```

应显示 `scan, industry, competitor, resolve, output-test, receiver, doctor, ai-test`。

---

## Step 2 — GitHub Auth

```bash
gh auth status
```

- 未登录：

```bash
gh auth login
```

- 已登录但 workflow scope 缺失（`push` 时报 `refusing to allow ... without 'workflow' scope`）：

```bash
gh auth refresh -s repo,workflow
```

验证：

```bash
./scripts/github-auth-check.sh
```

预期：

```
gh CLI                     PASS
Authenticated              PASS
Repository Access          PASS
Contents Write             PASS
Workflow Permission        PASS
```

| 状态 | 含义 |
|------|------|
| PASS | 通过 |
| MISSING | 缺项（workflow scope 缺失时此处为 MISSING，并在下方提示 `gh auth refresh`） |
| BLOCKED | 未认证或 gh 未安装 |

---

## Step 3 — Secret 配置

```bash
./scripts/secrets-set-keychain.sh
```

按菜单选择并输入（输入时隐藏显示）：

| 序号 | 含义 | Keychain Service | GitHub Secret | 必填 |
|------|------|------------------|---------------|------|
| 1 | OpenAI API Key | `web3-radar-openai` | `OPENAI_API_KEY` | **是** |
| 2 | Lark Industry Webhook | `web3-radar-lark-industry` | `LARK_WEBHOOK_INDUSTRY` | **是** |
| 3 | Lark Competitor Webhook | `web3-radar-lark-competitor` | `LARK_WEBHOOK_COMPETITOR` | **是** |
| 4 | Industry Signing Secret | `web3-radar-lark-signing-industry` | `LARK_SIGNING_SECRET_INDUSTRY` | 否 |
| 5 | Competitor Signing Secret | `web3-radar-lark-signing-competitor` | `LARK_SIGNING_SECRET_COMPETITOR` | 否 |
| 6 | Local HTTP Token | `web3-radar-local-http-token` | `LOCAL_WEBHOOK_TOKEN` | 否 |

> **V0.1 允许 Industry + Competitor 共用同一个 Lark Webhook。** 先创建一个测试 Bot，把同一个 URL 分别写入 2 和 3。

V0.1 默认可不配置 Signing Secret，普通 Webhook 直接可用。

---

## Step 4 — Bootstrap（一键引导）

```bash
./scripts/bootstrap.sh
```

它按顺序执行：

1. macOS / security CLI 检查
2. gh CLI / GitHub Auth / Repository / Workflow Permission
3. Keychain Secret 存在性
4. GitHub Secrets 存在性
5. 如本地 Secret 完整，询问是否同步到 GitHub
6. Radar Doctor
7. Production Readiness

默认 **NO AI CALL / NO LARK PUSH**。

预期：

- 全部就绪 → `READY_FOR_E2E`
- 缺配置 → `BLOCKED_BY_CONFIGURATION`（不是代码 FAIL，按提示补 Secret 即可）

非交互检查：

```bash
./scripts/bootstrap.sh --non-interactive
```

---

## Step 5 — Production Check

```bash
./scripts/production-check.sh
```

目标：**READY_FOR_E2E**。

若仍为 `BLOCKED_BY_CONFIGURATION`，下方会列出具体 Blocker（如 `WORKFLOW_PERMISSION_MISSING`、`OPENAI_API_KEY_MISSING`），逐项解决后再试。

> 不到 READY_FOR_E2E 前先不要跑 Weekly E2E。

---

## Step 6 — 一键验收

```bash
./scripts/acceptance.sh
./scripts/acceptance.sh --e2e
```

可选：`--no-ai`、`--no-push`。

---

## Step 7 — OpenAI Smoke

```bash
./scripts/with-secrets.sh python -m radar ai-test
./scripts/with-secrets.sh python -m radar ai-test --model synthesis
```

| 命令 | 调用的模型 | 取自 |
|------|-----------|------|
| `ai-test`（默认 classifier） | `gpt-5.6-luna` | `config/models.yaml` → `classifier.primary` |
| `ai-test --model synthesis` | `gpt-5.6-terra`（fallback `gpt-5.6-luna`） | `config/models.yaml` → `synthesis` |

预期：两条均输出结构化结果并通过校验；无 `OPENAI_API_KEY` 时显示 `BLOCKED_BY_CONFIGURATION`。

---

## Step 8 — Lark Smoke

Industry：

```bash
./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push
```

Competitor：

```bash
./scripts/with-secrets.sh python -m radar output-test --target lark --radar competitor --push
```

> `--push` 意味着**真的发送**一条极小测试卡到群。无 `--push` 时为 dry-run（构建 payload 但不外发）。

---

## Step 9 — 手动跑 Radar

> 所有命令以 `python -m radar --help` 为准。本节命令均已验证。

**只想手动跑一次 Industry：**

```bash
./scripts/with-secrets.sh python -m radar industry --weekly --output file --push
# 或同时发 Lark：
./scripts/with-secrets.sh python -m radar industry --weekly --output lark,file --push
```

**只想手动跑一次 Competitor：**

```bash
./scripts/with-secrets.sh python -m radar competitor --weekly --output file --push
./scripts/with-secrets.sh python -m radar competitor --weekly --output lark,file --push
```

**预览（不外发）：**

```bash
python -m radar industry --weekly --output lark
# 输出：[industry] PREVIEW: payload built but NOT sent (use --push to deliver).
```

**Dry-run（永不外发，不写 radar-state）：**

```bash
python -m radar industry --weekly --dry-run
python -m radar scan --dry-run
```

**No-AI（不调 OpenAI，验证采集→报告链路）：**

```bash
python -m radar scan --no-ai
python -m radar industry --weekly --no-ai
```

**全量 scan（两条 Radar 一次跑完）：**

```bash
./scripts/with-secrets.sh python -m radar scan --output file --push
```

**强制重发（绕过幂等）：**

```bash
./scripts/with-secrets.sh python -m radar industry --weekly --output lark,file --push --force-push
```

**查看 Resolver 结果：**

```bash
python -m radar resolve
```

---

## Step 9 — GitHub Actions

仓库 → **Actions** 页面。

| Workflow | 文件 | Schedule | 时区说明 |
|----------|------|----------|----------|
| Radar Scan | `scan.yml` | `0 */4 * * *`（每 4 小时） | UTC |
| Weekly Reports | `weekly.yml` | `20 0 * * 5` / `35 0 * * 5` | UTC = Asia/Shanghai 周五 08:20 / 08:35 |

建议验证顺序：

1. **Scan #1** — Actions → Radar Scan → Run workflow → `radar=all, mode=scan, push=false` — 观察是否创建/更新 `radar-state` 分支。
2. **Scan #2** — 再 Run 一次，验证 State 能恢复（seen/cost 不丢失）。
3. **Industry Weekly** — Weekly Reports → Run workflow → `radar=industry, mode=weekly, push=false`（先 dry）。
4. **Competitor Weekly** — 同上 `radar=competitor`。
5. **真实 Weekly** — `push=true` 后观察 Lark。

所有运行上传 Artifact（`reports/*.md` + `reports/*.json`，保留 30 天；Scan 为 14 天）。

---

## Step 10 — Success Checklist

```
[ ] gh auth status        → 已登录
[ ] github-auth-check.sh  → Workflow Permission PASS
[ ] OPENAI_API_KEY        → CONFIGURED
[ ] LARK_WEBHOOK_INDUSTRY → CONFIGURED
[ ] LARK_WEBHOOK_COMPETITOR → CONFIGURED
[ ] ./scripts/bootstrap.sh          → READY / READY_FOR_E2E
[ ] ./scripts/production-check.sh   → READY_FOR_E2E
[ ] ai-test (classifier)            → PASS
[ ] ai-test --model synthesis       → PASS
[ ] output-test lark industry --push   → PASS（群收到卡）
[ ] output-test lark competitor --push → PASS（群收到卡）
[ ] GitHub Scan #1                  → PASS（radar-state 已创建）
[ ] GitHub Scan #2                  → PASS（State 恢复）
[ ] Industry E2E --weekly --push   → PASS
[ ] Competitor E2E --weekly --push → PASS
```

全部勾选 → **Web3 Radar v0.1 is operational.**

下一步：按 [docs/V0.1_TRIAL_RUN.md](V0.1_TRIAL_RUN.md) 开始试运行记录。
