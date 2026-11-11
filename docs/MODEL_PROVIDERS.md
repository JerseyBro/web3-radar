# Model Providers

> 适合谁：需要切换或新增 LLM 供应商的人。
> 什么时候看：想用 DeepSeek / Claude / Qwen 等替代 OpenAI，或接入自定义网关时。

---

## Provider 总览

| Provider | Protocol | Base URL | Secret Env | Model 示例 | 状态 |
|----------|----------|----------|------------|------------|------|
| OpenAI | OpenAI-compatible | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-6-luna` | 适配器测试通过；真实 API 待验收 |
| DeepSeek | OpenAI-compatible | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | `deepseek-flash` | 适配器测试通过；真实 API 待验收 |
| Anthropic Claude | Anthropic Messages API | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | 由用户配置 | 适配器已实现，未验收 |
| Alibaba DashScope | OpenAI-compatible | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | 由用户配置 | 适配器已实现，未验收 |
| Tencent Hunyuan | OpenAI-compatible | `https://api.hunyuan.cloud.tencent.com/v1` | `TENCENT_LLM_API_KEY` | 由用户配置 | 适配器已实现，未验收 |
| Volcengine Ark | OpenAI-compatible | `https://ark.cn-beijing.volces.com/api/v3` | `VOLCENGINE_API_KEY` | 由用户配置 | 适配器已实现，未验收 |
| OpenCode Go | OpenAI-compatible | `https://opencode.ai/zen/go/v1` | `OPENCODE_GO_API_KEY` | 由用户配置 | 适配器已实现，未验收 |
| Google Gemini | OpenAI-compatible | `https://generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` | 由用户配置 | 适配器已实现，未验收 |
| Generic | OpenAI-compatible | （自定义） | `CUSTOM_LLM_API_KEY` | 由用户配置 | 适配器已实现，未验收 |

> 本表只说明代码有相应协议适配器；不能代替真实 API 验收。模型名称、价格与接口能力请以供应商官方文档为准。当前默认模型的价格使用 DeepSeek 峰时非缓存费率和 OpenAI 标准费率。

---

## 配置方式

### 当前默认（DeepSeek 主模型，未启用跨厂商 fallback）

```yaml
# config/models.yaml — 已默认配置，无需修改
roles:
  classifier:
    primary: {provider: deepseek, model: deepseek-flash}
    fallback: null
  synthesis:
    primary: {provider: deepseek, model: deepseek-flash}
    fallback: null
```

### 仅使用 DeepSeek

```yaml
roles:
  classifier:
    primary: {provider: deepseek, model: deepseek-flash}
    fallback: null
  synthesis:
    primary: {provider: deepseek, model: deepseek-flash}
    fallback: null
```

然后配置 `DEEPSEEK_API_KEY`（见 [SECRET_BOOTSTRAP](SECRET_BOOTSTRAP.md)）。

### 切换到其他 Provider

```yaml
roles:
  classifier:
    primary: {provider: google, model: CURRENT_OFFICIAL_MODEL_ID}
    fallback: null
pricing:
  CURRENT_OFFICIAL_MODEL_ID:
    input: VERIFIED_USD_PER_1M_INPUT
    output: VERIFIED_USD_PER_1M_OUTPUT
```

占位值必须替换为供应商当前官方模型 ID 与价格，再配置对应 API Key、运行 `ai-test`。其他 Provider 同理。

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
pricing:
  my-model: {input: VERIFIED_USD_PER_1M_INPUT, output: VERIFIED_USD_PER_1M_OUTPUT}
```

无需新增 Python 代码，但要核实协议兼容性和真实价格。

---

## Provider 能力

| 能力 | 是否需要 | 说明 |
|------|----------|------|
| text input / output | ✅ 必须 | Radar 核心需求 |
| system prompt | ✅ 必须 | classifier / synthesis 均使用 |
| non-stream | ✅ 必须 | 同步调用 |
| JSON structured output | ✅ 必须 | `response_format: json_object`（Anthropic 用 prompt hint） |
| usage / token metadata | 可选 | 无则标记 `USAGE_UNKNOWN`，不阻塞 |
| pricing | 正式 AI Pipeline 必填 | 任一角色模型无价格时跳过 AI，保留确定性报告 |

不支持（非 Radar 需求）：vision / tools / audio / image / agents / web search。

---

## Fallback

跨 Provider fallback，显式日志：

```
MODEL_FALLBACK from_provider=deepseek from_model=deepseek-flash to_provider=openai to_model=gpt-6-luna reason=rate limit 429
```

Fallback 仅针对：provider unavailable / rate limit / timeout / 5xx 等可重试错误。

**不**触发 fallback：`invalid_api_key` / `unauthorized` / `billing` / `budget exceeded` / `model_not_found`。

---

## Cost Guard

- `config/models.yaml` → 当前角色主模型或 fallback 缺少 `pricing` 时，正式分类/合成跳过 AI，保留确定性报告。直接调用 `LLMClient` 的工具不受 CostGuard 保护。
- Provider 不返回 `usage` → `USAGE_UNKNOWN`，用 `len//4` 估算。
- `$5` 是应用内估算预算，不能代替服务商账户消费上限；默认关闭 AI 长文合成，DeepSeek 的分类调用关闭默认思考模式以控制成本。

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
6. 在 `pricing` 加当前官方模型价格（正式 AI Pipeline 必填）
7. 用 `python -m radar ai-test` Smoke

Generic OpenAI-Compatible 无需改 Python。

---

## 来源

- DeepSeek 模型与价格: https://api-docs.deepseek.com/quick_start/pricing/
- DeepSeek Thinking Mode: https://api-docs.deepseek.com/guides/thinking_mode/
- OpenAI GPT-6 Luna: https://developers.openai.com/api/docs/models/gpt-6-luna
- Anthropic: https://docs.anthropic.com/en/api/messages
- Alibaba DashScope: https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
- Tencent Hunyuan: https://cloud.tencent.com/document/product/1729/111007
- Volcengine Ark: https://www.volcengine.com/docs/82379
- OpenCode Go: https://opencode.ai/zen/go/v1 (via https://docs.docker.com/ai/docker-agent/providers/opencode-go/)
- Google Gemini: https://ai.google.dev/gemini-api/docs/openai
