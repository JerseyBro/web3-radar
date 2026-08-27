import json
from pipeline.openai_client import OpenAIClient
from tests._util import skip, module_available

def test_no_client():
    c = OpenAIClient(api_key=None)
    assert not c.available()
    parsed, usage = c.call_json("gpt-4o-mini","sys","user")
    assert parsed is None

def test_json_parse_logic():
    if not module_available("openai"):
        skip("openai not installed (optional dep)")
    c = OpenAIClient(api_key="sk-fake")
    est = c._estimate_tokens("hello world "*100)
    assert est > 0
