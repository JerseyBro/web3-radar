from __future__ import annotations
import hashlib
from collections import defaultdict
from radar.schema import Event

def cluster_events(events: list[Event], fuzzy_threshold: int = 85) -> list[Event]:
    """Simple clustering: group events with similar titles or same canonical topic.
    Assigns cluster_id. Does not merge events, just labels.
    """
    try:
        from rapidfuzz import fuzz
        has_fuzz = True
    except ImportError:
        has_fuzz = False

    clusters: list[list[Event]] = []
    for e in events:
        placed = False
        norm = e.title.lower().strip()
        for cl in clusters:
            rep = cl[0]
            if has_fuzz:
                score = fuzz.ratio(norm, rep.title.lower().strip())
                if score >= fuzzy_threshold:
                    cl.append(e)
                    placed = True
                    break
            else:
                # fallback exact first 3 words
                if norm.split()[:3] == rep.title.lower().split()[:3]:
                    cl.append(e)
                    placed = True
                    break
        if not placed:
            clusters.append([e])

    # assign cluster_id
    for cl in clusters:
        if len(cl) > 1:
            # deterministic cluster id from sorted event_ids
            ids = sorted(x.event_id for x in cl)
            cid = hashlib.sha256("|".join(ids).encode()).hexdigest()[:12]
            for x in cl:
                x.cluster_id = cid
        else:
            cl[0].cluster_id = hashlib.sha256(cl[0].event_id.encode()).hexdigest()[:12]

    return events

def get_cluster_map(events: list[Event]) -> dict[str, list[Event]]:
    m = defaultdict(list)
    for e in events:
        m[e.cluster_id or e.event_id].append(e)
    return dict(m)
