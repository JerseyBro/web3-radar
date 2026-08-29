# Sources

数据源维护手册。

## Industry Sources（当前真实配置，`config/sources.yaml`）

- Official Primary：Ethereum Blog（RSS）、Ethereum EIPs（GitHub）、Solana Blog（RSS）、Base Blog（RSS）、WalletConnect Blog（RSS）
- DeFi Data：DeFiLlama Chains（API）、CoinGecko Trending（API）
- Established Media：CoinDesk（RSS）、Blockworks（RSS）、The Block（RSS）、Decrypt（RSS）

## Competitor Sources（10 Wallet，`config/sources.yaml` → `competitor.wallets`）

| Wallet | App Store | Google Play | Blog | GitHub |
|--------|-----------|-------------|------|--------|
| Bitget Wallet | `Bitget Wallet` | `com.bitkeep.wallet` | ✓ | ✓ |
| OKX Wallet | `OKX: Buy Bitcoin BTC & Crypto` | `com.okinc.okex.gp` | ✓ | ✓ |
| UniversalX | `UniversalX` | `app.universalx.mobile` | ✓ | — |
| TokenPocket | `TokenPocket - Crypto Wallet` | `vip.mytokenpocket` | ✓ | ✓ |
| Solflare | `Solflare` | `com.solflare.mobile` | ✓ | ✓ |
| Zerion | `Zerion` | `io.zerion.android` | ✓ | ✓ |
| Rabby Wallet | `Rabby Wallet` | `com.debank.rabby` | ✓ | ✓ |
| UXUY | `UXUY` | `com.uxuy.wallet` | ✓ | — |
| Exodus | `Exodus` | `exodusmovement.exodus` | ✓ | — |
| Phantom | `Phantom` | `app.phantom` | ✓ | ✓ |

> 每个钱包监测：Official Website + Blog + GitHub + App Store + Google Play。以 `storage/state/resolved_sources.json` 的 `resolved` / `unresolved` 为准。

## Source Priority

```
Official Primary
  > Official GitHub / Docs
    > Established Media
      > Secondary
        > Social Signal
```

Cluster：多个来源报道同一事必须聚合为一事件，不重复计。

## 状态定义

- `resolved`：Resolver 可靠匹配（App Store ID / Google Play ID）
- `unresolved`：无法可靠匹配，保持 unresolved，不误绑
- `failed`：本次采集失败（网络/403/超时），单源隔离
- `disabled`：显式关闭的源

## Resolver

`python -m radar resolve` 解析：
- App Store：iTunes Search + 开发商/域名验证
- Google Play：包名可达性验证
- GitHub：组织/仓库猜测 + release 抓取
- RSS / Web：直接采集

解析结果写入 `storage/state/resolved_sources.json`（位于 `radar-state` 分支）。

## 添加 Source 标准

- 可访问、可追溯
- 合法，不绕过 paywall / login / robots
- 优先官方源
- 新增强 Source 在 `config/sources.yaml` 配置并补 credibility
