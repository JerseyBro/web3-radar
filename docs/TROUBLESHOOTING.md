# Troubleshooting

按问题索引。每个问题：现象 / 可能原因 / 检查方法 / 解决方式。

## doctor NOT READY
- 现象：`python -m radar doctor` 显示 NOT READY
- 可能原因：依赖缺失 / 配置文件缺失 / State 目录损坏
- 检查：`doctor` 输出的 FAIL 行
- 解决：补依赖（`pip install -e .`）、补 config、删除损坏的 state json

## OPENAI_API_KEY missing
- 现象：ai-test 显示 BLOCKED_BY_CONFIGURATION
- 检查：`echo $OPENAI_API_KEY` 为空
- 解决：在 `.env` 或环境变量配置

## openai package missing
- 现象：ai-test 报 BLOCKED
- 解决：`pip install openai`

## model not found
- 现象：OpenAI 返回 404
- 可能原因：模型名拼写错误或账户无权
- 解决：核对 `config/models.yaml` 中 primary 模型名

## Structured Output parse error
- 现象：AI 返回非 JSON
- 解决：检查 prompt；代码已对解析失败降级为确定性评分

## OpenAI timeout
- 现象：调用超时
- 解决：网络/限流；Cost Guard 不会因此崩溃

## budget exceeded
- 现象：日志出现 `MONTHLY BUDGET EXCEEDED`
- 解决：AI 调用自动停止，保留候选；如需提高预算改 `MONTHLY_AI_BUDGET_USD`

## Lark webhook invalid
- 错误类型：INVALID_WEBHOOK
- 解决：检查 `LARK_WEBHOOK_INDUSTRY/COMPETITOR` 是否正确

## Lark signature error
- 错误类型：SIGNATURE_ERROR
- 解决：核对 `LARK_SIGNING_SECRET_*`，确认开启签名且与机器人一致

## Lark keyword rejected
- 错误类型：KEYWORD_REJECTED
- 解决：群机器人关键词拦截，调整文案或机器人关键词

## Lark IP restriction
- 错误类型：IP_REJECTED
- 解决：飞书机器人 IP 白名单限制

## Lark message too long
- 现象：卡片超长被拒
- 解决：报告已做长度裁剪；检查 Top Signals 数量

## Local HTTP connection refused
- 现象：output-test local-http 失败
- 解决：先启动 `python -m radar receiver --host 127.0.0.1 --port 8787`

## GitHub Action failed
- 现象：Job 红
- 检查：Actions 日志
- 解决：常见为缺 Secret 或 `contents: write` 未开

## contents: write denied
- 现象：state push 失败
- 解决：仓库 Settings → Actions → Workflow permissions → Read and write

## radar-state missing
- 现象：首次运行无 radar-state 分支
- 解决：首次 `scan.yml` 运行会自动创建；或手动 `git push -u origin radar-state`

## radar-state conflict
- 现象：push 冲突
- 解决：workflow 已 `concurrency` 串行 + 冲突 retry，无需手动处理

## State JSON corrupted
- 现象：load 报错
- 解决：StateStore 自动 reinit；或删除该文件重建

## Collector 403 / timeout
- 现象：`sources_failed` 增高
- 解决：单源失败隔离，不影响其他源；更换/补充 Source

## RSS invalid
- 解决：Source 失效，更新 `config/sources.yaml` 的 URL

## Google Play unresolved
- 现象：该钱包无 Google Play 事件
- 解决：解析受限；保持 unresolved，不误绑

## App Store unresolved
- 解决：Resolver 未可靠匹配；保持 unresolved

## report empty
- 现象：本周无高信号事件
- 解决：正常（Signal > Coverage），非故障

## duplicate message
- 现象：重复 Lark 消息
- 解决：Delivery 幂等；除非 `--force-push`，否则同 report_id 不重发

## report not pushed
- 现象：报告生成但没发 Lark
- 解决：确认传了 `--push` 且 `push.weekly_enabled=true`
