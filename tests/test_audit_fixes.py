from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

from collectors.app_store import AppStoreCollector
from collectors.github import GitHubCollector, GitHubOrgCollector
from collectors.rss import RSSCollector
from radar.cli import do_scan, run_radar
from radar.config import ROOT, get_settings
from radars.industry import build_collectors
from radars.competitor import build_collectors as build_competitor_collectors
from storage.git_state import _redact
from storage.state import StateStore


async def test_dry_run_path_does_not_record_seen():
    async def fake_scan(*args, **kwargs):
        return {"processed_ids": ["dry-run-event"]}

    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        with patch("radars.industry.run_industry_scan", fake_scan):
            await run_radar(
                "industry", {}, state, None, None, None,
                do_ai=False, weekly=False, record_seen=False,
            )
        assert "dry-run-event" not in state.load_seen()


async def test_app_store_event_uses_release_timestamp():
    payload = {
        "results": [{
            "version": "1.2.3",
            "releaseNotes": "New feature",
            "trackViewUrl": "https://apps.apple.com/app/id123",
            "currentVersionReleaseDate": "2026-11-10T08:30:00Z",
        }]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AppStoreCollector("Wallet", app_id="123").collect(client)
    assert result.success
    assert result.events[0].published_at is not None
    assert result.events[0].published_at.isoformat().startswith("2026-11-10T08:30:00")


async def test_rss_uses_updated_timestamp_when_published_missing():
    atom = """<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Updates</title>
      <entry>
        <title>Protocol update</title>
        <link href="https://example.com/update" />
        <id>update-1</id>
        <updated>2026-11-10T01:02:03Z</updated>
        <summary>Details</summary>
      </entry>
    </feed>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=atom.encode(), headers={"content-type": "application/atom+xml"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await RSSCollector("Updates", "https://example.com/feed").collect(client)
    assert result.success
    assert result.events[0].published_at is not None
    assert result.events[0].published_at.isoformat().startswith("2026-11-10T01:02:03")


def test_industry_github_source_is_not_parsed_as_rss():
    collectors = build_collectors(get_settings())
    github = [c for c in collectors if isinstance(c, GitHubCollector)]
    assert any(c.repo == "ethereum/EIPs" for c in github)
    rss_urls = [c.url for c in collectors if isinstance(c, RSSCollector)]
    assert "https://github.com/ethereum/EIPs" not in rss_urls


async def test_github_empty_releases_falls_back_to_dated_commits():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[{
                "sha": "abc123",
                "html_url": "https://github.com/ethereum/EIPs/commit/abc123",
                "commit": {
                    "message": "Update EIP-1234",
                    "author": {"date": "2026-11-10T00:00:00Z"},
                },
            }])
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GitHubCollector("Ethereum EIPs", "ethereum/EIPs", radar="industry").collect(client)
    assert result.success
    assert len(result.events) == 1
    assert result.events[0].published_at is not None
    assert result.events[0].raw_meta["sha"] == "abc123"


async def test_github_org_collector_uses_dated_public_activity():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{
            "id": "evt-1",
            "type": "PushEvent",
            "created_at": "2026-11-10T00:00:00Z",
            "repo": {"name": "example/wallet"},
            "payload": {
                "head": "abc123",
                "size": 1,
                "commits": [{"message": "Add passkey support"}],
            },
        }])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await GitHubOrgCollector("Example Wallet", "example").collect(client)
    assert result.success
    assert len(result.events) == 1
    assert result.events[0].published_at is not None
    assert result.events[0].source_url.endswith("/commit/abc123")


def test_competitor_org_sources_do_not_guess_repository_names():
    collectors = build_competitor_collectors(get_settings(), state=None)
    org_collectors = [c for c in collectors if isinstance(c, GitHubOrgCollector)]
    guessed_repo_collectors = [c for c in collectors if isinstance(c, GitHubCollector)]
    assert len(org_collectors) >= 1
    assert guessed_repo_collectors == []


def test_git_state_redacts_embedded_credentials():
    token = "ghs_super_secret_value"
    with patch.dict(os.environ, {"GITHUB_TOKEN": token}):
        value = _redact(f"https://x-access-token:{token}@github.com/example/repo.git {token}")
    assert token not in value
    assert "https://***:***@github.com" in value


def test_weekly_manual_dispatch_respects_selected_radar():
    workflow = (ROOT / ".github" / "workflows" / "weekly.yml").read_text(encoding="utf-8")
    assert "github.event_name == 'workflow_dispatch' && (inputs.radar == 'industry' || inputs.radar == 'all')" in workflow
    assert "github.event_name == 'workflow_dispatch' && (inputs.radar == 'competitor' || inputs.radar == 'all')" in workflow
    assert "|| github.event_name == 'workflow_dispatch'" not in workflow


def test_scheduled_scan_enables_push_gate():
    workflow = (ROOT / ".github" / "workflows" / "scan.yml").read_text(encoding="utf-8")
    assert "github.event_name == 'schedule' && 'true' || inputs.push" in workflow


def test_secret_menus_share_the_canonical_keychain_mapping():
    keychain = (ROOT / "scripts" / "lib" / "keychain.sh").read_text(encoding="utf-8")
    setter = (ROOT / "scripts" / "secrets-set-keychain.sh").read_text(encoding="utf-8")
    remover = (ROOT / "scripts" / "secrets-remove-keychain.sh").read_text(encoding="utf-8")
    assert "RADAR_LABELS=(" in keychain
    assert 'LABELS=("${RADAR_LABELS[@]}")' in setter
    assert 'LABELS=("${RADAR_LABELS[@]}")' in remover
    assert '|| "$choice" == "${#LABELS[@]}"' not in setter


def test_secret_mapping_arrays_have_equal_lengths_and_expected_google_slot():
    script = ROOT / "scripts" / "lib" / "keychain.sh"
    command = (
        f'source "{script}"; '
        'printf "%s\\n" "${#RADAR_LABELS[@]}" "${#RADAR_SERVICES[@]}" "${#RADAR_ENV_NAMES[@]}"; '
        'printf "%s|%s|%s\\n" "${RADAR_LABELS[8]}" "${RADAR_SERVICES[8]}" "${RADAR_ENV_NAMES[8]}"'
    )
    import subprocess

    result = subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=True)
    lines = result.stdout.splitlines()
    assert lines[:3] == ["14", "14", "14"]
    assert lines[3] == "Google|web3-radar-google|GEMINI_API_KEY"


async def test_scan_fails_when_every_source_fails_and_skips_delivery():
    async def fake_run(*args, **kwargs):
        return {
            "sources_checked": 3,
            "sources_failed": 3,
            "collected": 0,
            "after_window": 0,
            "removed_by_window": 0,
            "after_seen": 0,
            "removed_by_seen": 0,
            "duplicates_removed": 0,
            "noise_removed": 0,
            "candidate_events": 0,
            "high_signal": 0,
            "empty_reason": "EMPTY_BY_SCORE",
            "ai_calls": 0,
            "events": [],
            "critical_events": [],
        }

    settings = {"models": {"pricing": {}}, "runtime": {"push": {"critical_enabled": False}}}
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        try:
            with patch("radar.cli.run_radar", fake_run):
                await do_scan("industry", True, True, None, False, False, settings, state, None)
        except RuntimeError as exc:
            assert "all configured sources failed for: industry" in str(exc)
        else:
            assert False, "all-source failure must fail the run"
