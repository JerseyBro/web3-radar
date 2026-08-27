# Changelog

## 0.1.0

Initial usable release (Minimum Usable Release).

### Added
- Industry Intelligence Radar
- Competitor Intelligence Radar
- Collector pipeline (RSS / Web / GitHub / AppStore / GooglePlay / DeFiLlama / CoinGecko)
- Normalize / Filter / Dedupe (exact + fuzzy) / Cluster / Score
- AI classification (structured output) + weekly synthesis
- Model fallback config (classifier fallback=null, synthesis fallback=luna) with MODEL_FALLBACK logging
- Monthly cost guard (cross-run accumulation + month rollover)
- Persistent state on `radar-state` branch (seen / clusters / cost / deliveries / resolved), atomic writes, schema_version
- Lark delivery (timeout / retry / backoff / signing / response+business code validation / idempotency / sanitized logging)
- Local HTTP delivery (canonical envelope + optional bearer)
- File output (always markdown + json)
- Output router (multi-target, failure isolation)
- Critical duplicate protection
- CLI: scan / industry / competitor / resolve / output-test / receiver / doctor / ai-test
- Push safety: explicit `--push`, `--dry-run` never sends, `--force-push` for resend
- GitHub Actions (scan every 4h, weekly Friday Asia/Shanghai 08:20/08:35, concurrency, timeout, artifacts)
- Documentation suite (docs/)
- `doctor` and `ai-test` diagnostic commands

### Not in scope (V0.1)
- Dashboard / user system / database / Redis / MQ / Vector DB
- X API / Nansen / Arkham
- Heavy agent frameworks (LangChain / CrewAI)
