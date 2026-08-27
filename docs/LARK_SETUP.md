# Lark Setup

Lark / 飞书配置手册。

## 创建 Custom Bot

飞书群 → 设置 → 群机器人 → 添加机器人（自定义 Webhook）→ 获得 Webhook URL。
可选「签名校验」获得 Signing Secret。

## Industry Webhook

配置环境变量 / GitHub Secret：`LARK_WEBHOOK_INDUSTRY`

## Competitor Webhook

`LARK_WEBHOOK_COMPETITOR`

两个 Webhook 可以相同，也可以不同。

## Signing Secret（Optional）

`LARK_SIGNING_SECRET_INDUSTRY` / `LARK_SIGNING_SECRET_COMPETITOR`
不配置也能用普通 Webhook。

## GitHub Secrets

仓库 → Settings → Secrets → 添加 `LARK_WEBHOOK_INDUSTRY` / `LARK_WEBHOOK_COMPETITOR`（可选签名）。

## 本地 .env

```
LARK_WEBHOOK_INDUSTRY=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
LARK_WEBHOOK_COMPETITOR=https://open.feishu.cn/open-apis/bot/v2/hook/yyy
# 可选
LARK_SIGNING_SECRET_INDUSTRY=
LARK_SIGNING_SECRET_COMPETITOR=
```

## Smoke Test

```bash
python -m radar output-test --target lark --radar industry --push
python -m radar output-test --target lark --radar competitor --push
```

## Weekly Push

调度运行自动 `--push`；`workflow_dispatch` 默认 `push=false`（安全）。

## 常见错误入口

- INVALID_WEBHOOK：URL 错
- SIGNATURE_ERROR：签名密钥不一致
- KEYWORD_REJECTED：群机器人关键词拦截
- IP_REJECTED：IP 白名单

> 禁止在文档/日志/代码中记录真实 Webhook 与 Secret。
