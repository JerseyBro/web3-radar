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

选 1. OpenAI → 输入 API Key
选 2. Lark Industry → 输入 Webhook URL
选 3. Lark Competitor → 输入 Webhook URL（V0.1 允许与 Industry 共用同一个）

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
./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push
```

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

两者共享 Mac Keychain。通用脚本只依赖 Bash + macOS security + gh CLI。

- Codex: 可能支持 OpenAI Platform secure provisioning
- OpenCode: 需手动通过 `secrets-set-keychain.sh` 添加
- 通用脚本只判断：CONFIGURED / MISSING
