from __future__ import annotations
import re
from radar.schema import Event

DEFAULT_NOISE_KEYWORDS = [
    "bug fix", "bug fixes", "minor fix", "minor fixes",
    "performance improvement", "performance improvements",
    "stability improvement", "stability improvements",
    "various improvement", "minor update", "small fix",
]

def is_noise(event: Event, noise_keywords: list[str] | None = None) -> bool:
    kws = [k.lower() for k in (noise_keywords or DEFAULT_NOISE_KEYWORDS)]
    combined = f"{event.title} {event.excerpt}".lower()
    # If title+excerpt very short and matches noise patterns, filter
    for kw in kws:
        if kw in combined:
            # If content is short and only contains noise phrases, it's noise
            # Heuristic: if title length < 80 and contains noise keyword and no substantive words
            # Check if combined is mostly noise
            # Simple: if title exactly is noise phrase or with version number
            if len(combined) < 500:
                # Count substantive tokens besides noise
                # If after removing noise keywords, remaining text is short (<20 chars without version)
                # For competitor radar, stricter: short release notes that are only noise
                # Detect version-only titles like "v2.3.1" + noise
                stripped = combined
                for k in kws:
                    stripped = stripped.replace(k, "")
                stripped = re.sub(r"v?\d+(\.\d+)+", "", stripped)
                stripped = re.sub(r"[^a-zA-Z]", "", stripped)
                if len(stripped.strip()) < 10:
                    return True
                # Also if title itself is noise keyword
                title_norm = event.title.lower().strip()
                if any(title_norm == kw or title_norm.startswith(kw) for kw in kws):
                    return True
    return False

def filter_events(events: list[Event], noise_keywords: list[str] | None = None) -> tuple[list[Event], list[Event]]:
    kept = []
    removed = []
    for e in events:
        if is_noise(e, noise_keywords):
            removed.append(e)
        else:
            kept.append(e)
    return kept, removed
