from __future__ import annotations
import hashlib
from collections import defaultdict
from pipeline.normalize import canonicalize_url, normalize_title
from radar.schema import Event

def exact_dedupe(events: list[Event]) -> tuple[list[Event], int]:
    seen_url = {}
    seen_hash = {}
    result = []
    dup_count = 0
    for e in events:
        canon = canonicalize_url(e.source_url)
        e.source_url = canon
        h = hashlib.sha256(f"{canon}|{normalize_title(e.title)}".encode()).hexdigest()
        if canon in seen_url or h in seen_hash:
            # mark duplicate
            orig = seen_url.get(canon) or seen_hash.get(h)
            if orig:
                e.duplicate_of = orig.event_id
            dup_count += 1
            continue
        seen_url[canon] = e
        seen_hash[h] = e
        result.append(e)
    return result, dup_count

def fuzzy_dedupe(events: list[Event], threshold: int = 88) -> tuple[list[Event], int]:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return events, 0
    # Group by same entity/radar to reduce compares
    kept = []
    dup = 0
    for e in events:
        is_dup = False
        norm_title = normalize_title(e.title)
        for k in kept:
            score = fuzz.ratio(norm_title, normalize_title(k.title))
            if score >= threshold:
                # Also check URL similarity or same source domain - boost confidence
                # For app store release notes, titles often identical across platforms
                e.duplicate_of = k.event_id
                # Merge: keep earliest or highest credibility
                is_dup = True
                break
        if is_dup:
            dup += 1
        else:
            kept.append(e)
    return kept, dup

def dedupe(events: list[Event], fuzzy_threshold: int = 88) -> tuple[list[Event], dict]:
    after_exact, exact_dup = exact_dedupe(events)
    after_fuzzy, fuzzy_dup = fuzzy_dedupe(after_exact, threshold=fuzzy_threshold)
    stats = {"exact_duplicates": exact_dup, "fuzzy_duplicates": fuzzy_dup, "total_removed": exact_dup + fuzzy_dup}
    return after_fuzzy, stats
