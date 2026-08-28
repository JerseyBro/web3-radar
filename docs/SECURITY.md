# Security

## Secret Storage

- **Local**: macOS Keychain
- **Production**: GitHub Actions Secrets (Repository scope)

## Least Privilege

V0.1 只使用 Repository Secret，不自动改 Organization Secret。

## Logging

禁止输出 Secret 明文。状态只输出：PASS / MISSING / OPTIONAL / CONFIGURED / SYNCED / FAIL / BLOCKED_BY_CONFIGURATION / BLOCKED_BY_CREDENTIAL_SCOPE。

## Rotation

1. `secrets-set-keychain.sh` 覆盖新 Key
2. `secrets-sync-github.sh` 同步 GitHub
3. `production-check.sh` 验证

## Incident Response

如果 Secret 泄漏：

1. Revoke old secret (OpenAI Platform / Lark Admin)
2. Create new secret
3. Update Mac Keychain: `secrets-set-keychain.sh`
4. Sync GitHub: `secrets-sync-github.sh`
5. Inspect Git history: `git log --oneline -10`
6. Rerun secret scan: `git grep` for secret patterns
