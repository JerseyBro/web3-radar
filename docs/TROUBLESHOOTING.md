# Troubleshooting

> 适合谁：遇到报错或行为不符合预期时。
> 怎么用：按症状在目录中定位 → 复制 Check/Fix 命令。

每个问题结构：**现象 → 可能原因 → 检查 → 修复**。状态名与真实代码一致。

---

## 目录

1. [gh 未安装](#1-gh-未安装)
2. [GitHub 未登录](#2-github-未登录)
3. [Workflow Permission MISSING](#3-workflow-permission-missing)
4. [Repository Access Denied](#4-repository-access-denied)
5. [OPENAI_API_KEY 缺失](#5-openai_api_key-缺失)
6. [OpenAI 认证失败](#6-openai-认证失败)
7. [模型不可用](#7-模型不可用)
8. [Budget Exceeded](#8-budget-exceeded)
9. [Lark Webhook 缺失](#9-lark-webhook-缺失)
10. [Lark Webhook 无效](#10-lark-webhook-无效)
11. [Lark 关键词拦截](#11-lark-关键词拦截)
12. [Lark 签名错误](#12-lark-签名错误)
13. [Lark 限流](#13-lark-限流)
14. [Lark 超时](#14-lark-超时)
15. [Collector 失败](#15-collector-失败)
16. [App Store 解析失败](#16-app-store-解析失败)
17. [Google Play Unresolved](#17-google-play-unresolved)
18. [State 分支缺失](#18-state-分支缺失)
19. [State Push 冲突](#19-state-push-冲突)
20. [State 损坏](#20-state-损坏)
21. [GitHub Actions 超时](#21-github-actions-超时)
22. [报告为空](#22-报告为空)
23. [重复推送](#23-重复推送)
24. [AI Fallback](#24-ai-fallback)
25. [with-secrets 缺 Keychain 条目](#25-with-secrets-缺-keychain-条目)
26. [acceptance.sh 中断](#26-acceptancesh-中断)

---

## 1. gh 未安装

- 现象：`./scripts/*.sh` 报 `gh CLI — MISSING`
- 原因：未安装 GitHub CLI
- 检查：`gh --version`
- 修复：`brew install gh`（macOS）

## 2. GitHub 未登录

- 现象：`./scripts/github-auth-check.sh` → `Authenticated MISSING`，`ACTION_REQUIRED: NOT_AUTHENTICATED`
- 检查：`gh auth status`
- 修复：`gh auth login`

## 3. Workflow Permission MISSING

- 现象：`github-auth-check.sh` → `Workflow Permission MISSING` / 推送报 `refusing to allow ... without 'workflow' scope`
- 原因：credential 缺少 `workflow` scope
- 检查：`./scripts/github-auth-check.sh`
- 修复：`gh auth refresh -s repo,workflow`
- 注意：仅在**已认证**时提示 refresh；未登录时应先 `gh auth login`

## 4. Repository Access Denied

- 现象：`Repository Access MISSING` / `REPOSITORY_ACCESS_DENIED`
- 原因：当前账号无 `JerseyBro/web3-radar` 访问权限
- 检查：`gh repo view JerseyBro/web3-radar --json name`
- 修复：联系仓库管理员授权

## 5. OPENAI_API_KEY 缺失

- 现象：`./scripts/secrets-doctor.sh` → `OPENAI_API_KEY MISSING`；`python -m radar ai-test` → `BLOCKED_BY_CONFIGURATION`
- 检查：`./scripts/secrets-doctor.sh`
- 修复：`./scripts/secrets-set-keychain.sh` → 选 1 → 粘贴 Key → `./scripts/secrets-sync-github.sh`

## 6. OpenAI 认证失败

- 现象：`ai-test` 报 401 / invalid_api_key
- 原因：Key 拼写错误、已过期或被 revoke
- 检查：`./scripts/with-secrets.sh python -m radar ai-test`
- 修复：OpenAI Platform 重新创建 Key → `secrets-set-keychain.sh` 覆盖 → `secrets-sync-github.sh`

## 7. 模型不可用

- 现象：OpenAI 返回 404 / `model_not_found`
- 原因：`config/models.yaml` 中模型名错误或账户无权
- 检查：`cat config/models.yaml` 对比 `ai-test` 报错中的模型名
- 修复：更正 `classifier.primary` / `synthesis.primary`

## 8. Budget Exceeded

- 现象：日志 `WARN: MONTHLY BUDGET EXCEEDED` / `BudgetGuard` 阻止后续 AI 调用
- 原因：`storage/state/cost.json` 月累计 ≥ `monthly_ai_budget_usd`（默认 $5）
- 检查：`cat storage/state/cost.json | python -m json.tool`
- 修复：AI 自动停止，保留确定性候选，pipeline 不崩；如需提高预算：改 `config/models.yaml` 或环境变量 `MONTHLY_AI_BUDGET_USD`

## 9. Lark Webhook 缺失

- 现象：`secrets-doctor.sh` → `LARK_WEBHOOK_INDUSTRY/COMPETITOR MISSING`；`output-test --push` 报 `BLOCKED_BY_CONFIGURATION`
- 检查：`./scripts/secrets-doctor.sh`
- 修复：`./scripts/secrets-set-keychain.sh` → 选 2/3 → 填 Webhook URL（V0.1 允许两个共用同一个）

## 10. Lark Webhook 无效

- 现象：`output-test` 返回 `INVALID_WEBHOOK`
- 原因：Webhook URL 拼写错误或 Bot 已删除
- 检查：`./scripts/with-secrets.sh python -m radar output-test --target lark --radar industry --push`
- 修复：飞书群重新创建 Custom Bot，更新 Keychain

## 11. Lark 关键词拦截

- 现象：返回 `KEYWORD_REJECTED`
- 原因：群机器人设置了关键词白名单，消息未命中
- 修复：调整群机器人关键词设置，或联系群主

## 12. Lark 签名错误

- 现象：返回 `SIGNATURE_ERROR`
- 原因：`LARK_SIGNING_SECRET_*` 与机器人签名密钥不一致，或未开启签名却传了签名
- 检查：`./scripts/secrets-doctor.sh` → 签名段
- 修复：核对 Signing Secret；不启用签名时不要配置该 Secret（显示 OPTIONAL 即正常）

## 13. Lark 限流

- 现象：返回 `RATE_LIMITED`
- 原因：短时间发送过多
- 修复：等待后重试；`--force-push` 会绕过幂等，需谨慎

## 14. Lark 超时

- 现象：`DeliveryError: TIMEOUT`
- 原因：网络或飞书服务抖动
- 修复：`output-test` 有 `retry_max: 3` 自动重试；持续超时检查网络

## 15. Collector 失败

- 现象：日志 `sources_failed` 增高，某源 `failed`
- 原因：对方 403 / 超时 / RSS 失效
- 检查：日志 `sources=12 failed=2` 具体失败源
- 修复：单源失败隔离，不影响其他源；更新 `config/sources.yaml` 的 URL

## 16. App Store 解析失败

- 现象：`python -m radar resolve` 某钱包 `unresolved`
- 原因：iTunes Search 未可靠匹配到同名 App
- 修复：保持 `unresolved`，不误绑；核对 `app_store_name` 是否准确

## 17. Google Play Unresolved

- 现象：该钱包无 Google Play 事件
- 原因：包名可达性验证失败或解析受限（已知限制）
- 修复：保持 `unresolved`（不阻塞 v0.1，见 README Known Limitations）

## 18. State 分支缺失

- 现象：首次运行无 `radar-state` 分支
- 检查：`git ls-remote --heads origin radar-state`
- 修复：首次 `scan.yml` / `weekly.yml` 运行会自动创建；或手动 `git push origin radar-state`

## 19. State Push 冲突

- 现象：`git_state push` 冲突
- 原因：两个 workflow 同时修改 `radar-state`
- 修复：workflow 已 `concurrency: group: web3-radar-state, cancel-in-progress: false` 串行 + 冲突自动 retry，无需手动处理；禁止 force push

## 20. State 损坏

- 现象：`StateStore` 加载报错 / JSON 解析失败
- 修复：`StateStore` 自动 reinit 损坏文件；或手动删除 `storage/state/<file>.json` 重建（会丢失该文件历史，需人工确认）

## 21. GitHub Actions 超时

- 现象：Job 超过 30 分钟被终止
- 原因：Collector 异常长期占用
- 检查：Actions 日志最后的 source
- 修复：`timeout-minutes: 30` 已配置；检查是否某源持续超时，考虑暂时移除

## 22. 报告为空

- 现象：`reports/YYYY-WW-*.md` 只有 `本周无高信号事件`
- 原因：本周无 `tier ≥ weekly` 事件（Signal > Coverage，属正常）
- 修复：非故障；可 `python -m radar scan --no-ai` 查看 `candidates` 数量

## 23. 重复推送

- 现象：同一报告收到两次 Lark 消息
- 原因：默认同 `target+report_id` 幂等，不重复发送；仅 `--force-push` 会重发
- 检查：`storage/state/deliveries.json`
- 修复：不要无故使用 `--force-push`

## 24. AI Fallback

- 现象：日志 `MODEL_FALLBACK from=gpt-5.6-terra to=gpt-5.6-luna reason=...`
- 原因：`synthesis.primary` 失败，自动用 `fallback` 重试
- 修复：正常行为；若频繁 fallback，检查 `config/models.yaml` 模型名与账户权限

## 25. with-secrets 缺 Keychain 条目

- 现象：`./scripts/with-secrets.sh python -m radar ai-test` 仍报 `BLOCKED_BY_CONFIGURATION`
- 原因：Keychain 中无对应条目，`with-secrets` 只注入已存在的 Secret
- 检查：`./scripts/secrets-doctor.sh` → `Local Secret Store` 段
- 修复：`./scripts/secrets-set-keychain.sh` 补齐缺失项

## 26. acceptance.sh 中断

- 现象：`./scripts/acceptance.sh` 跑完后显示某一步失败，但后续步骤仍继续执行
- 原因：这是设计行为，不是脚本崩溃
- 检查：看每步的 `reason` 和 `next`
- 修复：按 Summary 里第一个 `BLOCKED` / `FAIL` 步骤修复后重跑

---

> 仍未解决？查看 [OPERATIONS](OPERATIONS.md) 日志速查与 [GITHUB_ACTIONS](GITHUB_ACTIONS.md) / [LARK_SETUP](LARK_SETUP.md) 专项文档。
