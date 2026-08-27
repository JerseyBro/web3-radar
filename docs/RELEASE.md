# Release

Release 规范。

## 版本号

- 当前：**v0.1.0**
- 未来：
  - `v0.1.x`：Bug Fix / 小修补
  - `v0.2.0`：新能力 / Signal Quality 提升
  - `v1.0.0`：稳定兼容 / 架构确认

语义：
- patch = Bug Fix
- minor = Feature / Capability
- major = Compatibility / Architecture

版本唯一来源：`pyproject.toml` 的 `version`（不要多文件人工维护）。

## Release 流程

```
tests (FAILED=0)
  ↓
doctor (READY)
  ↓
secret scan (PASS)
  ↓
E2E (Industry / Competitor Weekly)
  ↓
release checklist
  ↓
commit
  ↓
tag -a v0.1.0
  ↓
push origin main + push origin v0.1.0
```
