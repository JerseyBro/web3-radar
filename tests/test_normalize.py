from pipeline.normalize import canonicalize_url, normalize_title

def test_canonicalize_url():
    assert canonicalize_url("https://example.com/path/?utm_source=twitter&x=1") == "https://example.com/path?x=1"
    assert canonicalize_url("https://EXAMPLE.COM/path/") == "https://example.com/path"
    assert canonicalize_url("https://example.com/path#fragment") == "https://example.com/path"
    assert canonicalize_url("https://example.com/path?b=2&a=1") == "https://example.com/path?a=1&b=2"

def test_normalize_title():
    assert normalize_title("  Hello  World  ") == "hello world"
    assert normalize_title("Bug Fixes!") == "bug fixes"
