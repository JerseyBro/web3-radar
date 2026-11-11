from __future__ import annotations
import json
import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qsl, quote, urlsplit

from radar.schema import Event


_VERIFY_BY_TYPE = {
    "app_update": (
        "这次版本变化是否解决了一个可复用的用户问题？",
        "核对官方版本说明与实际产品入口，记录功能、适用地区和可复现步骤。",
    ),
    "github_release": (
        "是否出现值得复用的接口、工具或兼容性变化？",
        "阅读 Release 与变更记录，运行最小示例并确认影响范围。",
    ),
    "docs_update": (
        "文档或代码变化是否影响现有集成，或提供新的实现路径？",
        "对照提交差异与文档，确认可用版本并尝试最小复现。",
    ),
    "defi_metric": (
        "这个指标变化是否持续，并对应可验证的产品使用需求？",
        "核对指标口径、时间窗口和历史基线；不要据此直接推断资金流向。",
    ),
    "market_data": (
        "这条市场热度线索是否对应持续的用户需求？",
        "核对榜单口径和过去几期变化，再寻找独立使用数据佐证。",
    ),
    "news": (
        "报道中的变化是否值得进一步做产品或技术验证？",
        "打开原文并追溯一手公告，核对日期、对象和具体变化。",
    ),
    "blog_post": (
        "文章描述的变化是否提供可复用的产品或技术方向？",
        "阅读原文与相关文档，核对发布状态并记录可测试的具体能力。",
    ),
}
_TEXT_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)


def verification_for_event(event: Event) -> tuple[str, str]:
    title = event.title.casefold()
    if event.event_type.value in {"blog_post", "docs_update", "github_release"} and re.search(r"\b(api|sdk)\b", title):
        return (
            "公告中的开发接口或 SDK 是否已可用，并适合当前产品问题？",
            "打开官方文档，核对版本、端点与限制；用只读最小请求复现一项能力。",
        )
    if event.event_type.value == "docs_update" and "eip-" in title:
        return (
            "这项 EIP 处于什么状态，是否影响当前集成？",
            "核对 EIP 状态和规范差异，在测试环境复现受影响的接口。",
        )
    return _VERIFY_BY_TYPE.get(
        event.event_type.value,
        ("这条变化是否与当前项目或用户问题相关？", "打开原始来源，核对具体变化并记录一个可验证的下一步。"),
    )


def _plain(value: object, limit: int = 180) -> str:
    """Keep untrusted source text on a single literal Markdown line."""
    value = re.sub(r"\s+", " ", redact_access_urls(value)).strip()
    if len(value) > limit:
        value = value[:max(0, limit - 1)].rstrip() + "…"
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+!|])", r"\\\1", value)


def public_source_url(value: str) -> str | None:
    """Return a source URL safe to place in reports and outbound messages."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
    except (TypeError, ValueError):
        return None
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        return None
    if any(ch.isspace() or ord(ch) < 32 or ch in "<>`" for ch in value):
        return None
    host_lower = host.lower()
    path_lower = parsed.path.lower()
    if (host_lower in {"hooks.slack.com", "open.feishu.cn", "open.larksuite.com"}
            and any(part in path_lower for part in ("/services/", "/hook/"))):
        return None
    if host_lower in {"discord.com", "discordapp.com"} and "/api/webhooks/" in path_lower:
        return None
    if host_lower == "api.telegram.org" and path_lower.startswith("/bot"):
        return None
    if re.search(r"/(?:webhooks?|hooks?)/[A-Za-z0-9_-]{16,}", parsed.path, re.IGNORECASE):
        return None
    secret_names = {"key", "token", "auth", "authorization", "sig", "jwt"}
    secret_markers = ("api_key", "apikey", "accesskey", "token", "secret", "signature", "credential", "password", "jwt", "session", "x_amz", "x_goog")
    query_names = [key.lower().replace("-", "_") for key, _ in parse_qsl(parsed.query, keep_blank_values=True)]
    fragment_names = [key.lower().replace("-", "_") for key, _ in parse_qsl(parsed.fragment, keep_blank_values=True)]
    if any(name in secret_names or any(marker in name for marker in secret_markers)
           for name in query_names + fragment_names):
        return None
    if any("http://" in item.lower() or "https://" in item.lower()
           for _, item in parse_qsl(parsed.query, keep_blank_values=True)):
        # Avoid forwarding a signed URL nested inside an otherwise harmless
        # query argument; sources can link to the original page directly.
        return None
    return value


def redact_access_urls(value: object) -> str:
    """Keep ordinary text while hiding access-bearing URLs embedded within it."""
    return _TEXT_URL.sub(
        lambda match: match.group(0) if public_source_url(match.group(0)) else "[敏感链接已隐藏]",
        str(value or ""),
    )


def _source_url(value: str) -> str:
    """Only display traceable web links supplied by the collectors."""
    public = public_source_url(value)
    if public is None:
        return "来源链接不可用"
    safe_url = quote(public, safe="-._~:/?#@!$&+,;=%")
    return f"<{safe_url}>"


def build_solo_report(
    radar: str,
    period: str,
    events: list[Event],
    *,
    sources_checked: int | None = None,
    sources_failed: int = 0,
    empty_reason: str | None = None,
    max_items: int = 6,
    candidate_only: bool = False,
    cached_count: int = 0,
) -> str:
    """Build a source-first brief for a solo Web3 developer without an LLM.

    Each event is framed as an observation and a question to verify. The
    numeric score controls ordering only; it is not presented as confidence.
    """
    label = "行业" if radar == "industry" else "产品与竞品"
    ranked = sorted(events, key=lambda event: (-event.score, event.event_id))
    selected = ranked[:max(0, max_items)]
    only_candidates = candidate_only or (bool(events) and all(
        event.tier not in {"weekly", "important", "critical"} for event in events
    ))
    lines = [f"# 独立开发者情报简报 · {label} · {_plain(period, 40)}", ""]
    if sources_checked is None:
        coverage = "来源覆盖未提供"
    else:
        covered = max(0, sources_checked - sources_failed)
        coverage = f"来源成功 {covered}/{sources_checked}"
    count_label = "待验证候选" if only_candidates else "入选线索"
    lines.append(f"本轮展示 {len(events)} 条{count_label}；{coverage}。")
    if cached_count > 0:
        lines.append(f"其中 {cached_count} 条来自本周此前扫描的跨运行候选缓存，已按发布时间过滤。")
    lines.append("以下是待核实的研究线索；排序分数不代表事实可信度或投资判断。")
    if sources_failed:
        lines.append(f"有 {sources_failed} 个来源采集失败，本期可能遗漏变化。")
    lines.append("")

    if not selected:
        reasons = {
            "EMPTY_BY_SEEN": "本轮没有新增线索；此前处理过的事件可能已被去重。",
            "EMPTY_BY_WINDOW": "本轮采集内容未落入报告时间窗口。",
            "EMPTY_BY_SCORE": "本轮候选未达到入选门槛。",
        }
        lines.extend(["## 本轮结论", reasons.get(empty_reason, "本轮没有可展示的线索。")])
        lines.append("这不证明观察期内没有重要变化；请结合来源健康和原始事件核查。")
        return "\n".join(lines)

    lines.append("## 待验证候选" if only_candidates else "## 值得验证的线索")
    for number, event in enumerate(selected, 1):
        question, action = verification_for_event(event)
        suggested_action = getattr(event, "developer_action", None)
        published = "未提供" if event.published_at is None else event.published_at.isoformat()
        source_observation = _plain(event.excerpt, 240) or "仅有标题，缺少可核对的摘要"
        lines.extend([
            "",
            f"### {number}. {'[待验证候选] ' if only_candidates or event.tier not in {'weekly', 'important', 'critical'} else ''}{_plain(event.title)}",
            f"- 来源记录：{_plain(event.source, 80)} · {event.event_type.value} · {source_observation}。",
            f"- 产品 / 技术机会假设：{question}",
            f"- 下一步验证：{action}",
            f"- 证据：{_source_url(event.source_url)} · 发布时间：{published}",
            "- 不确定性：目前仅有该来源的线索；具体影响和机会尚未独立核实。",
        ])
        if suggested_action:
            lines.append(f"- AI 建议验证动作（待核查）：{_plain(suggested_action, 220)}")
    if len(events) > len(selected):
        lines.extend(["", f"另有 {len(events) - len(selected)} 条{count_label}未在简报中展开，可在 JSON 报告中查看。"])
    return "\n".join(lines)


def make_report_id(radar: str, period: str, kind: str = "weekly") -> str:
    raw = f"{radar}|{period}|{kind}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Report:
    radar: str
    period: str            # e.g. 2026-W35
    kind: str = "weekly"   # weekly | critical | smoke
    id: str = ""
    title: str = ""
    markdown: str = ""
    events: list[Event] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    generated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = make_report_id(self.radar, self.period, self.kind)
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()
        if not self.title:
            self.title = f"{self.radar.capitalize()} {self.kind} report {self.period}"

    def canonical_json(self) -> dict:
        return {
            "schema_version": "1",
            "report_id": self.id,
            "radar": self.radar,
            "period": self.period,
            "kind": self.kind,
            "title": self.title,
            "generated_at": self.generated_at,
            "meta": self.meta,
            "events": [
                {
                    "event_id": e.event_id,
                    "title": redact_access_urls(e.title),
                    "source": redact_access_urls(e.source),
                    "source_url": public_source_url(e.source_url) or "",
                    "published_at": e.published_at.isoformat() if e.published_at else None,
                    "event_type": e.event_type.value,
                    "entity": redact_access_urls(e.entity) if e.entity else None,
                    "excerpt": redact_access_urls(e.excerpt),
                    "score": e.score,
                    "tier": e.tier,
                    "tags": [redact_access_urls(tag) for tag in e.tags],
                    "developer_action": redact_access_urls(e.developer_action) if e.developer_action else None,
                } for e in self.events[:50]
            ],
            "markdown": redact_access_urls(self.markdown),
        }
