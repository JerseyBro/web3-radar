from __future__ import annotations
import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# URL canonicalization

_TRACKING_PARAMS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","fbclid","gclid","ref","_ga","mc_cid","mc_eid","igshid","spm"}

def canonicalize_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    # Remove default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    # Remove www? keep as is but normalize
    path = parsed.path or "/"
    # Remove trailing slash except root
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # Filter tracking params
    qs = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
    # Sort keys for determinism
    query = urlencode({k: v[0] if len(v)==1 else v for k,v in sorted(filtered.items())}, doseq=True)
    # Drop fragment
    result = urlunparse((scheme, netloc, path, "", query, ""))
    return result

def normalize_title(title: str) -> str:
    if not title:
        return ""
    t = title.strip().lower()
    # collapse whitespace
    t = re.sub(r"\s+", " ", t)
    # remove punctuation at ends
    t = re.sub(r"^[^\w]+|[^\w]+$", "", t)
    return t

def excerpt_from_html(html: str, max_len: int = 400) -> str:
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False) or ""
    except Exception:
        text = ""
    if not text:
        # fallback bs4
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
        except Exception:
            text = html[:max_len]
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
