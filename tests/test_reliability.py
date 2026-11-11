from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from outputs.base import DeliveryResult
from outputs.router import OutputRouter
from radar.cli import build_report, deliver_weekly, handle_critical, main, report_run_url, run_radar
from radar.report import Report
from radar.schema import Event, RadarType
from storage import git_state
from storage.state import StateStore


def _event(event_id: str, tier: str, score: int) -> Event:
    return Event(
        event_id=event_id, radar=RadarType.industry, source="Official",
        source_url=f"https://example.com/{event_id}", title=f"Update {event_id}",
        tier=tier, score=score,
    )


def test_failed_critical_delivery_remains_eligible_on_next_scan():
    critical = _event("critical-1", "critical", 95)
    ordinary = _event("ordinary-1", "archive", 45)

    async def fake_scan(*args, seen, **kwargs):
        events = [event for event in (critical, ordinary) if event.event_id not in seen]
        return {
            "events": events,
            "processed_ids": [event.event_id for event in events],
            "critical_events": [event for event in events if event.tier == "critical"],
        }

    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        with (
            patch("radars.industry.run_industry_scan", fake_scan),
            patch("outputs.lark.send_lark", side_effect=[
                {"ok": False, "error_type": "INVALID_WEBHOOK", "error_message": "test failure"},
                {"ok": True},
            ]) as send,
            patch.dict(os.environ, {"LARK_WEBHOOK_INDUSTRY": "https://lark.example/hook"}),
        ):
            first = asyncio.run(run_radar("industry", {}, state, None, None, None, False, weekly=False))
            assert state.load_seen() == {ordinary.event_id}
            try:
                asyncio.run(handle_critical(state, first, "industry", True, False, False))
            except RuntimeError as exc:
                assert "critical delivery failed" in str(exc)
            else:
                assert False, "live delivery failure must fail the scan"
            assert state.is_new_critical(critical.event_id)

            second = asyncio.run(run_radar("industry", {}, state, None, None, None, False, weekly=False))
            assert [event.event_id for event in second["critical_events"]] == [critical.event_id]
            asyncio.run(handle_critical(state, second, "industry", True, False, False))
            assert not state.is_new_critical(critical.event_id)
            assert send.call_count == 2


def test_dry_run_with_push_gate_does_not_mark_critical_as_alerted():
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        with (
            patch("outputs.lark.send_lark") as send,
            patch.dict(os.environ, {"LARK_WEBHOOK_INDUSTRY": "https://lark.example/hook"}),
        ):
            result = {"critical_events": [_event("preview-only", "critical", 95)]}
            asyncio.run(handle_critical(state, result, "industry", can_push=True, force=False, dry_run=True))
            assert state.is_new_critical("preview-only")
            assert state.load_deliveries() == []
            send.assert_not_called()


def test_distinct_critical_batches_in_one_week_are_both_delivered():
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        with (
            patch("outputs.lark.send_lark", return_value={"ok": True}) as send,
            patch.dict(os.environ, {"LARK_WEBHOOK_INDUSTRY": "https://lark.example/hook", "GITHUB_REPOSITORY": "owner/repo", "GITHUB_RUN_ID": "123"}),
        ):
            asyncio.run(handle_critical(state, {"critical_events": [_event("a", "critical", 95)]}, "industry", True, False, False))
            asyncio.run(handle_critical(state, {"critical_events": [_event("b", "critical", 96)]}, "industry", True, False, False))
            assert send.call_count == 2
            assert not state.is_new_critical("a") and not state.is_new_critical("b")
            assert all("打开运行记录并下载完整报告" not in json.dumps(call.args[1], ensure_ascii=False) for call in send.call_args_list)
            report_ids = [record["key"] for record in state.load_deliveries() if record["key"] not in {"a", "b"}]
            assert len(set(report_ids)) == 2


def test_four_critical_events_are_individual_and_partial_failure_retries_only_failed_event():
    event_ids = ["crit-one", "crit-two", "crit-three", "crit-four"]
    result = {"critical_events": [_event(event_id, "critical", 95) for event_id in event_ids]}
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        responses = [
            {"ok": True},
            {"ok": False, "error_type": "INVALID_WEBHOOK", "error_message": "test failure"},
            {"ok": True},
            {"ok": True},
            {"ok": True},
        ]
        with (
            patch("outputs.lark.send_lark", side_effect=responses) as send,
            patch.dict(os.environ, {"LARK_WEBHOOK_INDUSTRY": "https://lark.example/hook"}),
        ):
            asyncio.run(handle_critical(state, result, "industry", can_push=False, force=False, dry_run=False))
            send.assert_not_called()
            assert all(state.is_new_critical(event_id) for event_id in event_ids)

            try:
                asyncio.run(handle_critical(state, result, "industry", can_push=True, force=False, dry_run=False))
            except RuntimeError as exc:
                assert "critical delivery failed for 1 event" in str(exc)
            else:
                assert False, "a failed live alert must make the task fail"
            assert send.call_count == 4
            for index, call in enumerate(send.call_args_list):
                card = json.dumps(call.args[1], ensure_ascii=False)
                assert f"https://example.com/{event_ids[index]}" in card
                assert all(f"https://example.com/{other}" not in card for other in event_ids if other != event_ids[index])
            assert state.is_new_critical("crit-two")
            assert all(not state.is_new_critical(event_id) for event_id in ("crit-one", "crit-three", "crit-four"))

            asyncio.run(handle_critical(state, result, "industry", can_push=True, force=False, dry_run=False))
            assert send.call_count == 5
            assert not state.is_new_critical("crit-two")


def test_weekly_file_is_written_before_external_delivery_and_is_required():
    order: list[str] = []
    report = Report(radar="industry", period="2026-W46", markdown="# source-linked brief")
    settings = {"runtime": {"delivery": {"default_outputs": ["lark"]}}}

    class FileOutput:
        target = "file"

        def deliver(self, report, context):
            order.append("file")
            return DeliveryResult(target="file", success=True, status="success")

    class LarkOutput:
        target = "lark"

        def deliver(self, report, context):
            order.append("lark")
            return DeliveryResult(target="lark", success=True, status="success")

    with patch("radar.cli.build_report", return_value=report), patch.dict(OutputRouter.TARGETS, {"file": FileOutput, "lark": LarkOutput}):
        _, results = asyncio.run(deliver_weekly("industry", {"events": []}, settings, None, None, None, True, "lark", True, False, False))
    assert order == ["file", "lark"]
    assert [result.target for result in results] == ["file", "lark"]

    class FailingFileOutput:
        target = "file"

        def deliver(self, report, context):
            order.append("file-failed")
            return DeliveryResult(target="file", success=False, status="failed")

    with patch("radar.cli.build_report", return_value=report), patch.dict(OutputRouter.TARGETS, {"file": FailingFileOutput, "lark": LarkOutput}):
        try:
            asyncio.run(deliver_weekly("industry", {"events": []}, settings, None, None, None, True, "lark", True, False, False))
        except RuntimeError as exc:
            assert "file delivery failed" in str(exc)
        else:
            assert False, "external delivery must stop if the complete report cannot be written"
    assert order == ["file", "lark", "file-failed"]


def test_archive_candidates_are_labeled_and_do_not_trigger_synthesis():
    events = [_event(str(i), "archive", 55 - i) for i in range(4)]
    res = {"events": events, "sources_checked": 7, "sources_failed": 2, "collected": 14, "high_signal": 0, "empty_reason": "EMPTY_BY_SCORE"}
    settings = {"models": {}, "runtime": {"report": {"synthesis_enabled": True}}}
    guard = SimpleNamespace(cost_this_run=0.0)
    with (
        patch("radar.cli.synthesize_report", side_effect=AssertionError("archive candidates must not be synthesized")),
        patch.dict(os.environ, {"GITHUB_REPOSITORY": "JerseyBro/web3-radar", "GITHUB_RUN_ID": "12345"}),
    ):
        report = build_report("industry", res, settings, SimpleNamespace(available=lambda: True), guard, False)
    assert len(report.events) == 3
    assert report.meta["candidate_only"] is True
    assert report.meta["sources_checked"] == 7
    assert report.meta["sources_failed"] == 2
    assert report.meta["analysis_mode"] == "rules"
    assert report.meta["report_url"] == "https://github.com/JerseyBro/web3-radar/actions/runs/12345"
    assert "待验证候选" in report.markdown
    assert "来源成功 5/7" in report.markdown


def test_synthesis_requires_explicit_opt_in_and_valid_run_url():
    event = _event("high", "weekly", 70)
    res = {"events": [event], "ai_calls": 2}
    guard = SimpleNamespace(cost_this_run=0.0)
    with (
        patch("radar.cli.synthesize_report", side_effect=AssertionError("synthesis is opt-in")),
        patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_RUN_ID": "../bad"}),
    ):
        report = build_report("industry", res, {"models": {}, "runtime": {}}, None, guard, False)
        assert report_run_url() is None
    assert "report_url" not in report.meta
    assert report.meta["analysis_mode"] == "ai"
    assert "证据：" in report.markdown
    assert "https://example.com/high" in report.markdown


def test_noise_events_are_not_promoted_to_weekly_candidates():
    res = {"events": [_event("noise", "noise", 15)], "empty_reason": "EMPTY_BY_SCORE"}
    report = build_report("industry", res, {"models": {}, "runtime": {}}, None, SimpleNamespace(cost_this_run=0.0), True)
    assert report.events == []
    assert report.meta["candidate_only"] is False
    assert "本轮候选未达到入选门槛" in report.markdown


def test_github_actions_without_state_remote_fails_before_running():
    with tempfile.TemporaryDirectory() as tmp:
        env = {"GITHUB_ACTIONS": "true", "GITHUB_TOKEN": "", "STATE_PUSH_TOKEN": "", "GITHUB_REPOSITORY": "", "RADAR_STATE_REPO_URL": ""}
        with patch.dict(os.environ, env):
            for operation in (git_state.pull_state, git_state.push_state):
                try:
                    operation(Path(tmp))
                except RuntimeError as exc:
                    assert "not configured" in str(exc)
                else:
                    assert False, "CI must not silently use an empty local state"


def test_state_branch_bootstrap_and_round_trip_with_local_git_remote():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        state_dir = root / "local-state"
        state_dir.mkdir()
        state_file = state_dir / "seen.json"
        state_file.write_text('{"schema_version":2,"items":{"event":"2026-11-11T00:00:00Z"}}', encoding="utf-8")
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            assert git_state.pull_state(state_dir) is False  # first-run branch absence
            assert git_state.push_state(state_dir, "test") is True
            state_file.unlink()
            assert git_state.pull_state(state_dir) is True
        assert '"event"' in state_file.read_text(encoding="utf-8")
        assert (state_dir / "cost.json").is_file()
        assert (state_dir / "deliveries.json").is_file()


def test_existing_state_branch_without_core_files_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        work = root / "work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
        commands = [
            ["checkout", "-b", "radar-state"],
            ["config", "user.email", "test@local"],
            ["config", "user.name", "test"],
        ]
        for args in commands:
            subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)
        (work / "README.md").write_text("missing state", encoding="utf-8")
        for args in (["add", "README.md"], ["commit", "-m", "state branch without files"], ["remote", "add", "origin", str(remote)], ["push", "origin", "radar-state"]):
            subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)
        state_dir = root / "state"
        state_dir.mkdir()
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            try:
                git_state.pull_state(state_dir)
            except RuntimeError as exc:
                assert "missing required files" in str(exc)
            else:
                assert False, "existing incomplete remote state must not be treated as a blank first run"


def test_semantically_invalid_remote_cost_fails_before_copy():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        source = root / "source-state"
        source.mkdir()
        (source / "cost.json").write_text("{}", encoding="utf-8")
        destination = root / "destination-state"
        destination.mkdir()
        (destination / "cost.json").write_text('{"local":true}', encoding="utf-8")
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            assert git_state.push_state(source, "test invalid core") is True
            try:
                git_state.pull_state(destination)
            except RuntimeError as exc:
                assert "cost.json: invalid schema" in str(exc)
            else:
                assert False, "valid JSON without cost state fields must fail closed"
        assert (destination / "cost.json").read_text(encoding="utf-8") == '{"local":true}'


def test_optional_critical_state_is_validated_when_present():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        source = root / "source-state"
        source.mkdir()
        (source / "critical_alerts.json").write_text("{}", encoding="utf-8")
        destination = root / "destination-state"
        destination.mkdir()
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            assert git_state.push_state(source, "invalid optional alert state") is True
            try:
                git_state.pull_state(destination)
            except RuntimeError as exc:
                assert "critical_alerts.json: invalid schema" in str(exc)
            else:
                assert False, "corrupt alert dedupe state must fail closed"


def test_optional_candidate_state_validates_shape_and_event_rows():
    event = _event("cache-one", "weekly", 72)
    event.published_at = datetime.now(timezone.utc)
    row = event.model_dump(mode="json", exclude={"raw_meta"})
    valid = {"schema_version": 2, "radar": "industry", "events": [row]}
    name = "candidates_industry.json"
    git_state._validate_candidate_state(name, valid, len(json.dumps(valid).encode("utf-8")))
    invalid = [
        {**valid, "schema_version": 1},
        {**valid, "radar": "competitor"},
        {**valid, "events": {}},
        {**valid, "events": [row] * (git_state.CANDIDATE_MAX_ITEMS + 1)},
        {**valid, "events": [{"event_id": "broken"}]},
        {**valid, "events": [{**row, "radar": "competitor"}]},
    ]
    for payload in invalid:
        try:
            git_state._validate_candidate_state(name, payload, 100)
        except ValueError:
            pass
        else:
            assert False, "candidate state with wrong schema, radar, size, or event must fail"
    try:
        git_state._validate_candidate_state(name, valid, git_state.CANDIDATE_MAX_FILE_BYTES + 1)
    except ValueError as exc:
        assert "size limit" in str(exc)
    else:
        assert False, "oversize candidate cache must fail"


def test_invalid_remote_candidate_state_fails_before_copy():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        source = root / "source-state"
        source.mkdir()
        (source / "candidates_industry.json").write_text(json.dumps({
            "schema_version": 2, "radar": "industry", "events": [{"event_id": "broken"}],
        }), encoding="utf-8")
        destination = root / "destination-state"
        destination.mkdir()
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            assert git_state.push_state(source, "invalid candidate state") is True
            try:
                git_state.pull_state(destination)
            except RuntimeError as exc:
                assert "candidates_industry.json: invalid event at index 0" in str(exc)
            else:
                assert False, "remote invalid candidate must fail before StateStore can silently discard it"
        assert not (destination / "candidates_industry.json").exists()


def test_legacy_v1_core_state_pulls_with_delivery_migration():
    assert git_state._validate_core_state("seen.json", ["old-id"]) == {"schema_version": 1, "ids": ["old-id"]}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        source = root / "legacy-state"
        source.mkdir()
        (source / "seen.json").write_text(json.dumps({"schema_version": 1, "ids": ["old-id"]}), encoding="utf-8")
        (source / "cost.json").write_text(json.dumps({
            "schema_version": 1, "month": datetime.now(timezone.utc).strftime("%Y-%m"),
            "estimated_cost_usd": 0.75, "calls": 1, "input_tokens": 100, "output_tokens": 50,
        }), encoding="utf-8")
        (source / "deliveries.json").write_text(json.dumps({
            "schema_version": 1,
            "deliveries": {"lark:report-1": {"status": "ok", "delivered_at": "2026-11-11T00:00:00Z"}},
        }), encoding="utf-8")
        destination = root / "destination-state"
        destination.mkdir()
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            assert git_state.push_state(source, "legacy state") is True
            assert git_state.pull_state(destination) is True
        state = StateStore(state_dir=destination, namespace="test")
        assert state.monthly_cost_usd() == 0.75
        assert state.already_delivered("lark", "report-1") is True
        assert json.loads((destination / "deliveries.json").read_text())["schema_version"] == 2


def test_configured_remote_failure_is_not_treated_as_first_run():
    with tempfile.TemporaryDirectory() as tmp:
        bad_remote = str(Path(tmp) / "missing.git")
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": bad_remote, "GITHUB_ACTIONS": "true"}):
            for operation in (git_state.pull_state, git_state.push_state):
                try:
                    operation(Path(tmp))
                except RuntimeError as exc:
                    assert "branch check failed" in str(exc)
                else:
                    assert False, "remote access failure must fail the run"


def test_state_push_rejection_surfaces_after_retries():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        state_dir = root / "state"
        state_dir.mkdir()
        state_file = state_dir / "seen.json"
        state_file.write_text('{"schema_version":2,"items":{}}', encoding="utf-8")
        with patch.dict(os.environ, {"RADAR_STATE_REPO_URL": str(remote), "GITHUB_ACTIONS": "true"}):
            assert git_state.push_state(state_dir, "bootstrap") is True
            state_file.write_text('{"schema_version":2,"items":{"new":"2026-11-11T00:00:00Z"}}', encoding="utf-8")
            real_run = git_state._run

            def reject_push(cmd, *args, **kwargs):
                if "push" in cmd:
                    raise RuntimeError("simulated rejected push")
                return real_run(cmd, *args, **kwargs)

            with patch("storage.git_state._run", side_effect=reject_push), patch("storage.git_state.time.sleep"):
                try:
                    git_state.push_state(state_dir, "failed run")
                except RuntimeError as exc:
                    assert "push failed after retries" in str(exc)
                else:
                    assert False, "remote push rejection must not be reported as success"


def test_main_pushes_partial_state_after_scan_error_but_not_after_pull_error():
    async def fail_scan(*args, **kwargs):
        raise RuntimeError("later radar failed")

    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(state_dir=Path(tmp), namespace="test")
        with (
            patch("radar.cli.StateStore", return_value=state),
            patch("radar.cli.get_settings", return_value={}),
            patch("radar.cli.make_client", return_value=None),
            patch("radar.cli.do_scan", fail_scan),
            patch.object(sys, "argv", ["radar", "scan"]),
        ):
            with patch("radar.cli.sync_state_pull") as pull, patch("radar.cli.sync_state_push") as push:
                try:
                    main()
                except RuntimeError as exc:
                    assert "later radar failed" in str(exc)
                else:
                    assert False, "scan failure must stay visible"
                pull.assert_called_once()
                push.assert_called_once()

            with patch("radar.cli.sync_state_pull", side_effect=RuntimeError("state unavailable")), patch("radar.cli.sync_state_push") as push:
                try:
                    main()
                except RuntimeError as exc:
                    assert "state unavailable" in str(exc)
                else:
                    assert False, "remote state failure must prevent the scan"
                push.assert_not_called()
