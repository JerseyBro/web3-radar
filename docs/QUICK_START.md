# Quick Start

5–10 分钟跑通第一次运行。

## 1. 准备

- Python 3.12+
- Git
- 可访问的终端

## 2. Clone & 环境

```bash
git clone https://github.com/JerseyBro/web3-radar.git
cd web3-radar
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 3. 配置

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY 与两个 Lark Webhook（必填）
```

## 4. 健康检查

```bash
python -m radar doctor
```

全部 PASS / READY 即环境就绪；缺密钥时显示 `BLOCKED_BY_CONFIGURATION`（不是代码 FAIL）。

## 5. 无 AI 验证采集链路

```bash
python -m radar scan --no-ai
```

不调用 OpenAI，验证 Collector → Pipeline 能跑通。

## 6. AI 链路验证

```bash
python -m radar ai-test                 # classifier
python -m radar ai-test --model synthesis
```

无 `OPENAI_API_KEY` 时显示 `BLOCKED_BY_CONFIGURATION`。

## 7. 本地 HTTP 自测

```bash
python -m radar receiver --host 127.0.0.1 --port 8787   # 终端 A
python -m radar output-test --target local-http --radar industry --push   # 终端 B
```

Receiver 收到 canonical envelope 并写入 `storage/local-receiver/`。

## 8. Lark Smoke Test

```bash
python -m radar output-test --target lark --radar industry --push
python -m radar output-test --target lark --radar competitor --push
```

不发 Web3 数据、不调用 OpenAI，只发极小测试卡。

## 9. 手动跑 Weekly（需 --push 才真发）

```bash
python -m radar industry --weekly --output lark,file --push
python -m radar competitor --weekly --output lark,file --push
```

## 常用命令

```bash
python -m radar doctor
python -m radar scan --no-ai
python -m radar scan --dry-run
python -m radar ai-test
python -m radar resolve
python -m radar receiver --host 127.0.0.1 --port 8787
python -m radar output-test --target lark --radar industry --push
python -m radar industry --weekly --output lark,file --push
```
