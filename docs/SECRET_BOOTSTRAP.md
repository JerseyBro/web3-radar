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

Codex 与 OpenCode 共享同一套 Mac Keychain，各自存一套 Secret。

## First Setup

### GitHub Auth

```bash
# 1. Login with repo + workflow scope
gh auth login

# 2. Verify
./scripts/github-auth-check.sh
```

### OpenAI

```bash
# Mac Keychain
./scripts/secrets-set-keychain.sh
# 选 1. OpenAI → 输入 API Key
```

### Lark

V0.1 允许 Industry 与 Competitor 共用同一个 Lark Bot。

创建一个 Web3 Radar 测试 Bot，复制 Webhook URL，运行 `secrets-set-keychain.sh` 设置 Industry + Competitor Webhook。

## Bootstrap

```bash
./scripts/bootstrap.sh
```

默认安全：NO AI CALL / NO LARK PUSH。

## Add / Replace Secret

```bash
./scripts/secrets-set-keychain.sh
```

## Secret Doctor

```bash
./scripts/secrets-doctor.sh
```

## GitHub Sync

```bash
./scripts/secrets-sync-github.sh
```

Keychain → stdin → `gh secret set`。不经过 echo。

## Run With Secrets

```bash
./scripts/with-secrets.sh python -m radar doctor
./scripts/with-secrets.sh python -m radar ai-test
./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push
```

## Production Check

```bash
./scripts/production-check.sh
```

## Rotation

1. `secrets-set-keychain.sh` 覆盖新 Key
2. `secrets-sync-github.sh` 同步 GitHub
3. `production-check.sh` 验证

## Removal

```bash
./scripts/secrets-remove-keychain.sh
```

## Codex / OpenCode

两者共享 Mac Keychain。Secret 不存各 Agent 自己的位置。

- Codex 可安全 provisioning OpenAI Key（如具备能力）。
- OpenCode 需手动通过 `secrets-set-keychain.sh` 添加。
- 通用脚本只判断：CONFIGURED / MISSING。
