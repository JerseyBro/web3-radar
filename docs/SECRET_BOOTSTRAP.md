# Jersey Secret Bootstrap

## Why

不再手工复制 Secret。一次授权，长期复用。

## Architecture

```
Mac Keychain (Source of Truth: Local)
    ↓
Bootstrap / secrets-sync-github.sh
    ↓
GitHub Actions Secrets (Source of Truth: Production)
    ↓
Radar CLI via with-secrets.sh
```

Codex 与 OpenCode 共享同一套 Mac Keychain。

## First-Time Setup (最短流程)

### Step 1: GitHub Auth

```bash
# 未登录 → 先登录
gh auth login

# 已登录但 workflow scope 不足 → 刷新
gh auth refresh -s repo,workflow

# 验证
./scripts/github-auth-check.sh
```

### Step 2: 配置 Secret

```bash
./scripts/secrets-set-keychain.sh
```

选 LLM Provider → 输入对应 API Key（只需配置 `config/models.yaml` 中 `roles.*` 实际引用的 Provider）：
- 默认 `roles` 使用 `openai`，则只需配 OpenAI。
- 如切到 `deepseek`，则需 `DEEPSEEK_API_KEY`，此时 `OPENAI_API_KEY` 变为 OPTIONAL/UNUSED。
- 如切到 `google`，则需 `GEMINI_API_KEY`，此时 `OPENAI_API_KEY` 变为 OPTIONAL/UNUSED。

选 Lark Industry / Competitor → 输入 Webhook URL（V0.1 允许与 Industry 共用同一个）

### Step 3: 引导

```bash
./scripts/bootstrap.sh
```

### Step 4: 生产就绪

```bash
./scripts/production-check.sh
```

### Step 5: Smoke Test

```bash
./scripts/with-secrets.sh python -m radar ai-test
./scripts/with-secrets.sh python -m radar ai-test --model synthesis
./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push
```

> Smoke 需 `--push` 才真发；`bootstrap.sh` / `production-check.sh` 本身永不发 Lark。

> 使用 Google Gemini 时：
> ```bash
> ./scripts/with-secrets.sh python -m radar ai-test --provider google
> ./scripts/with-secrets.sh python -m radar ai-test --model synthesis --provider google
> ```

以后日常通常只需：

```bash
./scripts/bootstrap.sh          # 检查 + 必要时同步
./scripts/production-check.sh   # 生产就绪
```

## Secret 映射表

| 用途 | Keychain Service | GitHub Secret | 必填 |
|------|------------------|---------------|------|
| OpenAI | `web3-radar-openai` | `OPENAI_API_KEY` | 动态* |
| DeepSeek | `web3-radar-deepseek` | `DEEPSEEK_API_KEY` | 动态* |
| Anthropic Claude | `web3-radar-anthropic` | `ANTHROPIC_API_KEY` | 动态* |
| Alibaba DashScope | `web3-radar-alibaba` | `DASHSCOPE_API_KEY` | 动态* |
| Tencent Hunyuan | `web3-radar-tencent` | `TENCENT_LLM_API_KEY` | 动态* |
| Volcengine Ark | `web3-radar-volcengine` | `VOLCENGINE_API_KEY` | 动态* |
| OpenCode Go | `web3-radar-opencode-go` | `OPENCODE_GO_API_KEY` | 动态* |
| Google Gemini | `web3-radar-google` | `GEMINI_API_KEY` | 动态* |
| Generic LLM | `web3-radar-generic-llm` | `CUSTOM_LLM_API_KEY` | 动态* |
| Industry Lark | `web3-radar-lark-industry` | `LARK_WEBHOOK_INDUSTRY` | 是 |
| Competitor Lark | `web3-radar-lark-competitor` | `LARK_WEBHOOK_COMPETITOR` | 是 |
| Industry Signing | `web3-radar-lark-signing-industry` | `LARK_SIGNING_SECRET_INDUSTRY` | 否 |
| Competitor Signing | `web3-radar-lark-signing-competitor` | `LARK_SIGNING_SECRET_COMPETITOR` | 否 |
| Local HTTP Token | `web3-radar-local-http-token` | `LOCAL_WEBHOOK_TOKEN` | 否 |

> \* LLM Keys 动态：仅 `config/models.yaml` 中 `roles.classifier` / `roles.synthesis`（含 fallback）实际引用的 Provider 为 REQUIRED，其余为 OPTIONAL/UNUSED。`doctor` / `production-check` 会据此校验。

> Keychain `account` 统一为 `$USER`；GitHub 同步走 `Keychain → stdin → gh secret set`（不经 `echo`）。

## Commands

| 命令 | 作用 |
|------|------|
| `bootstrap.sh` | 一键引导（默认安全：NO AI CALL / NO LARK PUSH） |
| `secrets-doctor.sh` | 健康检查 |
| `production-check.sh` | 生产就绪检查 |
| `secrets-set-keychain.sh` | 写入/替换 Keychain Secret |
| `secrets-remove-keychain.sh` | 删除 Keychain Secret |
| `secrets-sync-github.sh` | Keychain → GitHub Secrets |
| `with-secrets.sh <cmd>` | 从 Keychain 注入 Secret 执行命令 |
| `github-auth-check.sh` | GitHub 权限检查 |

## Status Model

| 状态 | 含义 |
|------|------|
| PASS | 检查通过 |
| MISSING | 必填项未配置 |
| OPTIONAL | 可选项未配置（不阻塞） |
| CONFIGURED | 已配置 |
| SYNCED | 已同步到 GitHub |
| READY / READY_FOR_E2E | 生产就绪 |
| BLOCKED_BY_CONFIGURATION | 缺少必要 Secret |
| BLOCKED_BY_CREDENTIAL_SCOPE | GitHub credential scope 不足 |
| ACTION_REQUIRED | 需要用户手动操作 |
| FAIL | 代码/运行时异常（非配置问题） |

## Rotation

1. `secrets-set-keychain.sh` 覆盖新 Key
2. `secrets-sync-github.sh` 同步 GitHub
3. `production-check.sh` 验证

## Removal

```bash
./scripts/secrets-remove-keychain.sh
```

## Lark Signing

V0.1 默认不配置 Signing Secret。Webhook 无需 Signing 即可工作。
Signing Missing 不阻塞。

## Codex / OpenCode

两者共享 Mac Keychain，不各自维护 Secret：

```
        Codex
          ↘
           Mac Keychain
          ↗
        OpenCode
```

> 不要 `.codex/.env` / `.opencode/.env` 各存一份。

通用脚本只依赖 Bash + macOS security + gh CLI。

Doctor 输出示例（OpenCode / 本地 Shell）：

```
OpenAI Secure Provisioning
--------------------------
Current Runtime              OpenCode
Secure Provisioning          UNAVAILABLE_IN_CURRENT_RUNTIME
Shared Keychain Support      PASS
```

- **Codex**: 可使用 OpenAI Platform secure provisioning（如 runtime 支持），Key 直接写入 Keychain，不经过聊天窗口
- **OpenCode**: 需手动通过 `secrets-set-keychain.sh` 添加
- **Shared runtime**: 两个 Agent 事后复用同一套 macOS Keychain，不各存一套 Secret
- 通用脚本只判断：CONFIGURED / MISSING
