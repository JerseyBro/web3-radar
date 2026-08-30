# Model Providers

> 适合谁：需要切换或新增 LLM 供应商的人。
> 什么时候看：想用 DeepSeek / Claude / Qwen 等替代 OpenAI，或接入自定义网关时。

---

## Provider 总览

| Provider | Protocol | Base URL | Secret Env | Model 示例 | 状态 |
|----------|----------|----------|------------|------------|------|
| OpenAI | OpenAI-compatible | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-4o-mini` | ✅ 已验证 |
| DeepSeek | OpenAI-compatible | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | `deepseek-chat` / `deepseek-reasoner` | ✅ 已验证 |
| Anthropic Claude | Anthropic Messages API | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | `claude-3-5-sonnet-20241022` | ✅ 已实现 |
| Alibaba DashScope | OpenAI-compatible | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | `qwen-plus` / `qwen-max` | ✅ 已验证 |
| Tencent Hunyuan | OpenAI-compatible | `https://api.hunyuan.cloud.tencent.com/v1` | `TENCENT_LLM_API_KEY` | `hunyuan-lite` / `hunyuan-standard` | ✅ 已验证 |
| Volcengine Ark | OpenAI-compatible | `https://ark.cn-beijing.volces.com/api/v3` | `VOLCENGINE_API_KEY` | `doubao-pro-32k` / `doubao-lite-32k` | ✅ 已验证 |
| OpenCode Go | OpenAI-compatible | `https://opencode.ai/zen/go/v1` | `OPENCODE_GO_API_KEY` | `deepseek-v4-flash` 等 | ✅ 已验证 |
| Google Gemini | OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` | `gemini-2.0-flash` / `gemini-2.0-pro` | ✅ 已验证 |
| Generic | OpenAI-compatible | （自定义） | `CUSTOM_LLM_API_KEY` | 任意 | ✅ 已实现 |

> 官方文档优先，第三方博客仅作参考。Base URL 以本表为准，未来如官方变更请以 `config/models.yaml` 注释为准。

---

## 配置方式

### 默认（OpenAI，不改配置即兼容旧行为）

```yaml
# config/models.yaml — 已默认配置，无需修改
roles:
  classifier:
    primary: {provider: openai, model: gpt-5.6-luna}
    fallback: null
  synthesis:
    primary: {provider: openai, model: gpt-5.6-terra}
    fallback: {provider: openai, model: gpt-5.6-luna}
```

### 切换到 DeepSeek

```yaml
roles:
  classifier:
    primary: {provider: deepseek, model: deepseek-chat}
    fallback: {provider: openai, model: gpt-4o-mini}
  synthesis:
    primary: {provider: deepseek, model: deepseek-chat}
    fallback: {provider: openai, model: gpt-4o-mini}
```

然后配置 `DEEPSEEK_API_KEY`（见 [SECRET_BOOTSTRAP](SECRET_BOOTSTRAP.md)）。

### 切换到 Google Gemini

```yaml
roles:
  classifier:
    primary: {provider: google, model: gemini-2.0-flash}
    fallback: {provider: openai, model: gpt-4o-mini}
  synthesis:
    primary: {provider: google, model: gemini-2.0-pro}
    fallback: {provider: deepseek, model: deepseek-chat}
```

然后配置 `GEMINI_API_KEY`（见 [SECRET_BOOTSTRAP](SECRET_BOOTSTRAP.md)）。

### 混合 Provider（不同角色用不同厂商）

```yaml
roles:
  classifier:
    primary: {provider: deepseek, model: deepseek-chat}
    fallback: {provider: openai, model: gpt-4o-mini}
  synthesis:
    primary: {provider: anthropic, model: claude-3-5-sonnet-20241022}
    fallback: {provider: deepseek, model: deepseek-chat}
```

### 自定义网关（OpenRouter / SiliconFlow / LiteLLM / vLLM / 公司网关）

```yaml
providers:
  my_gateway:
    type: openai_compatible
    base_url: https://my-gateway.example.com/v1
    api_key_env: CUSTOM_LLM_API_KEY

roles:
  classifier:
    primary: {provider: my_gateway, model: my-model}
```

无需新增 Python 代码。

---

## Provider 能力

| 能力 | 是否需要 | 说明 |
|------|----------|------|
| text input / output | ✅ 必须 | Radar 核心需求 |
| system prompt | ✅ 必须 | classifier / synthesis 均使用 |
| non-stream | ✅ 必须 | 同步调用 |
| JSON structured output | ✅ 必须 | `response_format: json_object`（Anthropic 用 prompt hint） |
| usage / token metadata | 可选 | 无则标记 `USAGE_UNKNOWN`，不阻塞 |
| pricing | 可选 | 无则标记 `COST_UNKNOWN`，不阻塞 |

不支持（非 Radar 需求）：vision / tools / audio / image / agents / web search。

---

## Fallback

跨 Provider fallback，显式日志：

```
MODEL_FALLBACK from_provider=deepseek from_model=deepseek-chat to_provider=openai to_model=gpt-4o-mini reason=rate limit 429
```

Fallback 仅针对：provider unavailable / rate limit / timeout / 5xx 等可重试错误。

**不**触发 fallback：`invalid_api_key` / `unauthorized` / `billing` / `budget exceeded` / `model_not_found`。

---

## Cost Guard

- `config/models.yaml` → `pricing` 中未配置的模型 → `COST_UNKNOWN`，只记录 `calls` / `tokens`，费用记 0，不阻塞 Pipeline。
- Provider 不返回 `usage` → `USAGE_UNKNOWN`，用 `len//4` 估算。

---

## OpenCode Go 特别说明

- 订阅制（非按量）：`https://opencode.ai/auth` 获取 `OPENCODE_GO_API_KEY`。
- 需区分：**ChatGPT/Codex Subscription** ≠ **OpenCode Go Subscription**。不能用 ChatGPT 订阅凭证当 API Key。
- Base URL: `https://opencode.ai/zen/go/v1`，OpenAI-compatible `/chat/completions`。

---

## Secret 管理

见 [SECRET_BOOTSTRAP](SECRET_BOOTSTRAP.md)。新增 Provider 时只扩充 `scripts/lib/keychain.sh` 的 `RADAR_SERVICES` / `RADAR_ENV_NAMES` 映射。

动态校验：`doctor` / `production-check` 只要求 `roles.*` 实际引用的 Provider 的 Key 为 REQUIRED，未引用者为 OPTIONAL/UNUSED。

---

## 新增 Provider 检查清单

1. 在 `config/models.yaml` → `providers` 加一项（type / base_url / api_key_env）
2. 在 `pipeline/llm/registry.py` → `PROVIDER_DEFS` 加默认值（可选，有 user config 也可）
3. 在 `scripts/lib/keychain.sh` 加映射
4. 在 `.env.example` 加示例
5. 在 `.github/workflows/*.yml` 加 env
6. 在 `pricing` 加模型价格（可选）
7. 用 `python -m radar ai-test` Smoke

Generic OpenAI-Compatible 无需改 Python。

---

## 来源

- DeepSeek: https://api-docs.deepseek.com
- Anthropic: https://docs.anthropic.com/en/api/messages
- Alibaba DashScope: https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
- Tencent Hunyuan: https://cloud.tencent.com/document/product/1729/111007
- Volcengine Ark: https://www.volcengine.com/docs/82379
- OpenCode Go: https://opencode.ai/zen/go/v1 (via https://docs.docker.com/ai/docker-agent/providers/opencode-go/)
- Google Gemini: https://ai.google.dev/gemini-api/docs/openai
