from __future__ import annotations
from datetime import datetime, timezone, timedelta
from radar.schema import Event, EventType

# Undated events that are live snapshots are considered within window.
# DeFiLlama / CoinGecko produce current TVL/trending without published_at.
SNAPSHOT_TYPES = {EventType.defi_metric, EventType.market_data}


def _event_time(event: Event) -> datetime | None:
    """Best available timestamp for window filtering.

    Priority: published_at -> raw_meta updated_at/created_at if present.
    Returns None if no reliable time.
    """
    if event.published_at:
        return event.published_at
    # raw_meta may carry updated_at / created_at from collectors
    for key in ("updated_at", "created_at", "published_at"):
        val = (event.raw_meta or {}).get(key)
        if val:
            try:
                if isinstance(val, datetime):
                    return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
                # try ISO parse
                from dateutil import parser as dateparser  # type: ignore

                dt = dateparser.parse(str(val))
                if dt and not dt.tzinfo:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    return None


def filter_by_window(
    events: list[Event],
    lookback_days: int = 7,
    now: datetime | None = None,
    *,
    keep_undated_snapshots: bool = True,
) -> tuple[list[Event], list[Event]]:
    """Split events into (kept, removed) by weekly window.

    - Window is (now - lookback_days) .. now  (inclusive, UTC).
    - Undated non-snapshot events are REMOVED (don't default to now).
    - Undated snapshot events (defi_metric/market_data) are KEPT and considered current.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    kept: list[Event] = []
    removed: list[Event] = []
    for e in events:
        ts = _event_time(e)
        if ts is None:
            if keep_undated_snapshots and e.event_type in SNAPSHOT_TYPES:
                kept.append(e)
            else:
                removed.append(e)
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff or ts > now + timedelta(seconds=60):
            removed.append(e)
        else:
            kept.append(e)
    return kept, removed
