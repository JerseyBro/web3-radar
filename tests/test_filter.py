from radar.schema import Event, RadarType
from pipeline.filter import is_noise

def mk(title, excerpt=""):
    return Event(event_id="x", radar=RadarType.competitor, source="s", source_url="https://example.com", title=title, excerpt=excerpt)

def test_noise_detection():
    assert is_noise(mk("Bug fixes")) == True
    assert is_noise(mk("Performance improvements")) == True
    assert is_noise(mk("v2.3.1"), "minor fixes and stability improvements") == True

def test_not_noise():
    assert is_noise(mk("Bitget Wallet adds Solana Chain Abstraction", "New cross-chain swap enabled")) == False
    assert is_noise(mk("Phantom introduces Passkey support for MPC wallet")) == False
