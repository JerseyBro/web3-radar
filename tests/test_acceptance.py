#!/usr/bin/env python3
"""Acceptance runner tests.

These tests use a fake executor and fake secret store so we can validate
classification, dependency skipping, summary output, and exit codes without
real network/API/Lark calls.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from radar.acceptance import AcceptanceRunner, CommandResult


ROOT = Path(__file__).resolve().parents[1]


def fake_settings(classifier_provider="openai", classifier_model="gpt-5.6-luna", synthesis_provider="openai", synthesis_model="gpt-5.6-terra"):
    return {
        "models": {
            "providers": {
                "openai": {"type": "openai_compatible", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
                "deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com", "api_key_env": "DEEPSEEK_API_KEY"},
                "google": {"type": "openai_compatible", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "api_key_env": "GEMINI_API_KEY"},
            },
            "roles": {
                "classifier": {
                    "primary": {"provider": classifier_provider, "model": classifier_model},
                    "fallback": None,
                },
                "synthesis": {
                    "primary": {"provider": synthesis_provider, "model": synthesis_model},
                    "fallback": None,
                },
            },
            "pricing": {},
            "monthly_ai_budget_usd": 5,
            "max_ai_calls_per_run": 20,
        }
    }


class FakeExecutor:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def run(self, name, cmd, *, cwd, env=None, timeout=120):
        self.calls.append((name, tuple(cmd)))
        return self.responses.get(name, CommandResult(0, "", ""))


def run_runner(*, responses, secrets, settings=None, no_ai=False, no_push=False, e2e=False):
    executor = FakeExecutor(responses)
    runner = AcceptanceRunner(
        repo_root=ROOT,
        repo="JerseyBro/web3-radar",
        settings=settings or fake_settings(),
        executor=executor,
        secret_exists=lambda env: secrets.get(env, False),
        no_ai=no_ai,
        no_push=no_push,
        e2e=e2e,
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = runner.run()
    return rc, buf.getvalue(), runner, executor


def test_all_pass_basic_acceptance():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in to github.com\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=2 failed=0 raw=2\n", ""),
    }
    secrets = {
        "OPENAI_API_KEY": True,
        "LARK_WEBHOOK_INDUSTRY": True,
        "LARK_WEBHOOK_COMPETITOR": True,
    }
    rc, out, runner, executor = run_runner(responses=responses, secrets=secrets)
    assert rc == 0
    assert "BASIC_ACCEPTANCE_PASS" in out
    assert "LLM Classifier Smoke" in out
    assert "Basic Radar Scan" in out
    assert "Production E2E Industry" in out and "SKIPPED" in out
    assert any(name == "llm-classifier-smoke" for name, _ in executor.calls)


def test_github_fail_but_continues():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(1, "", "not authenticated\n"),
        "bootstrap": CommandResult(0, "BLOCKED_BY_CONFIGURATION\n", ""),
        "production-check": CommandResult(0, "BLOCKED_BY_CONFIGURATION\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, executor = run_runner(responses=responses, secrets=secrets)
    assert rc == 2
    assert "GitHub Authentication" in out
    assert "BLOCKED_BY_CONFIGURATION" in out
    assert any(name == "llm-classifier-smoke" for name, _ in executor.calls)
    assert any(name == "scan" for name, _ in executor.calls)


def test_llm_blocked_lark_continues():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "BLOCKED_BY_CONFIGURATION\n", ""),
        "production-check": CommandResult(0, "BLOCKED_BY_CONFIGURATION\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, executor = run_runner(responses=responses, secrets=secrets)
    assert rc == 2
    assert "LLM Classifier Smoke" in out and "SKIPPED" in out
    assert any(name == "lark-industry" for name, _ in executor.calls)
    assert any(name == "lark-competitor" for name, _ in executor.calls)


def test_industry_webhook_missing_competitor_pass():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, executor = run_runner(responses=responses, secrets=secrets)
    assert rc == 2
    assert "Industry Webhook" in out and "BLOCKED" in out
    assert any(name == "lark-competitor" for name, _ in executor.calls)
    assert not any(name == "lark-industry" for name, _ in executor.calls)


def test_classifier_fail_synthesis_still_runs():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(1, "Structured Output: FAIL\nResult: FAIL\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, executor = run_runner(responses=responses, secrets=secrets)
    assert rc == 1
    assert "LLM Classifier Smoke" in out and "FAIL" in out
    assert any(name == "llm-synthesis-smoke" for name, _ in executor.calls)


def test_no_ai_and_no_push_skip_smokes():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, executor = run_runner(responses=responses, secrets=secrets, no_ai=True, no_push=True)
    assert rc == 0
    assert "LLM Classifier Smoke" in out and "SKIPPED" in out
    assert "Lark Industry Smoke" in out and "SKIPPED" in out
    assert not any(name == "llm-classifier-smoke" for name, _ in executor.calls)
    assert not any(name == "lark-industry" for name, _ in executor.calls)


def test_e2e_safety():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, executor = run_runner(responses=responses, secrets=secrets, e2e=False)
    assert rc == 0
    assert "Production E2E Industry" in out and "SKIPPED" in out
    assert not any(name.startswith("e2e-") for name, _ in executor.calls)


def test_google_warning_and_dynamic_provider():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    settings = fake_settings(classifier_provider="openai", synthesis_provider="openai")
    secrets = {"OPENAI_API_KEY": True, "GEMINI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, _ = run_runner(responses=responses, secrets=secrets, settings=settings)
    assert rc == 0
    assert "WARN: Google Gemini API key configured but active provider is not google." in out
    assert "Classifier Provider: openai" in out


def test_secret_redaction_and_summary_always_printed():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "token=sk-secret-value\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(1, "https://open.feishu.cn/open-apis/bot/v2/hook/abcd\n", "SIGNATURE_ERROR\n"),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, _, _ = run_runner(responses=responses, secrets=secrets, no_push=False)
    assert rc == 2
    assert "sk-secret-value" not in out
    assert "open.feishu.cn/open-apis/bot/v2/hook/abcd" not in out
    assert "Acceptance Summary" in out


def test_lark_success_skipped_failed_classification():
    from radar.acceptance import AcceptanceRunner as AR

    s, _ = AR._classify_lark(CommandResult(0, "[deliver:lark] success\n", ""))
    assert s == "PASS"
    s, _ = AR._classify_lark(CommandResult(0, "[deliver:lark] skipped\n", ""))
    assert s == "SKIPPED"
    s, _ = AR._classify_lark(CommandResult(0, "[deliver:lark] preview\n", ""))
    assert s == "WARN"
    s, _ = AR._classify_lark(CommandResult(1, "[deliver:lark] FAILED INVALID_WEBHOOK: bad", ""))
    assert s == "BLOCKED"
    s, _ = AR._classify_lark(CommandResult(1, "[deliver:lark] FAILED TIMEOUT", ""))
    assert s == "BLOCKED"
    s, _ = AR._classify_lark(CommandResult(1, "[deliver:lark] FAILED INVALID_PAYLOAD", ""))
    assert s == "FAIL"


def test_lark_skipped_not_counted_as_pass_in_runner():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] skipped\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, runner, _ = run_runner(responses=responses, secrets=secrets)
    lark_industry = [r for r in runner.results if r.label == "Lark Industry Smoke"][0]
    assert lark_industry.status == "SKIPPED"
    assert "SKIPPED" in out
    # success still PASS
    lark_comp = [r for r in runner.results if r.label == "Lark Competitor Smoke"][0]
    assert lark_comp.status == "PASS"


def test_lark_failed_is_fail_not_pass():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(1, "[deliver:lark] FAILED NETWORK_ERROR: timeout", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, runner, _ = run_runner(responses=responses, secrets=secrets)
    assert rc == 2 or rc == 1
    assert "BLOCKED" in out or "FAIL" in out


def test_no_push_skips_lark_smokes():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, runner, executor = run_runner(responses=responses, secrets=secrets, no_push=True)
    for label in ("Lark Industry Smoke", "Lark Competitor Smoke"):
        step = [r for r in runner.results if r.label == label][0]
        assert step.status == "SKIPPED"
    assert not any(name == "lark-industry" for name, _ in executor.calls)
    assert not any(name == "lark-competitor" for name, _ in executor.calls)


def test_smoke_report_id_unique_and_force_push():
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, runner, executor = run_runner(responses=responses, secrets=secrets)
    # collect lark commands
    lark_calls = [(n, c) for n, c in executor.calls if n.startswith("lark-")]
    assert len(lark_calls) == 2
    for name, cmd in lark_calls:
        cmd_str = " ".join(cmd)
        assert "--report-id" in cmd_str
        assert "--force-push" in cmd_str
        # report id contains acceptance-<radar>
        idx = cmd.index("--report-id")
        rid = cmd[idx + 1]
        assert rid.startswith("acceptance-")
    # two lark calls must have different report ids
    ids = [c[c.index("--report-id") + 1] for _, c in lark_calls]
    assert ids[0] != ids[1]


def test_formal_delivery_idempotency_not_affected():
    from radar.report import make_report_id, Report
    from radar.cli import build_smoke_report
    # formal weekly: deterministic
    a = make_report_id("industry", "2026-W35", "weekly")
    b = make_report_id("industry", "2026-W35", "weekly")
    assert a == b
    # smoke without override: deterministic within same period
    r1 = build_smoke_report("industry")
    r2 = build_smoke_report("industry")
    assert r1.id == r2.id
    # smoke with override: unique
    r3 = build_smoke_report("industry", report_id="acceptance-industry-123-abc")
    assert r3.id == "acceptance-industry-123-abc"
    assert r3.id != r1.id
    # weekly report via Report still uses deterministic id
    w1 = Report(radar="industry", period="2026-W35", kind="weekly")
    w2 = Report(radar="industry", period="2026-W35", kind="weekly")
    assert w1.id == w2.id


def test_deepseek_role_resolution_and_openai_still_available():
    from pipeline.llm import PROVIDER_DEFS
    assert "openai" in PROVIDER_DEFS
    assert "deepseek" in PROVIDER_DEFS
    settings = fake_settings(classifier_provider="deepseek", classifier_model="deepseek-chat", synthesis_provider="deepseek", synthesis_model="deepseek-chat")
    responses = {
        "gh-version": CommandResult(0, "gh version 2.61.0\n", ""),
        "gh-auth": CommandResult(0, "Logged in\n", ""),
        "gh-repo-view": CommandResult(0, '{"name":"web3-radar"}\n', ""),
        "gh-contents-write": CommandResult(0, "true\n", ""),
        "gh-workflow-scope": CommandResult(0, "X-Oauth-Scopes: repo, workflow\n", ""),
        "bootstrap": CommandResult(0, "READY_FOR_E2E\n", ""),
        "production-check": CommandResult(0, "READY_FOR_E2E\n", ""),
        "llm-classifier-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "llm-synthesis-smoke": CommandResult(0, "AI Smoke Test\nResult: PASS\n", ""),
        "lark-industry": CommandResult(0, "[deliver:lark] success\n", ""),
        "lark-competitor": CommandResult(0, "[deliver:lark] success\n", ""),
        "scan": CommandResult(0, "[industry] sources=1 failed=0 raw=1\n", ""),
    }
    secrets = {"DEEPSEEK_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc, out, runner, _ = run_runner(responses=responses, secrets=secrets, settings=settings)
    assert "Classifier Provider: deepseek" in out
    assert "Synthesis Provider: deepseek" in out
    assert "DEEPSEEK_API_KEY" in out
    assert runner.all_required_envs == ["DEEPSEEK_API_KEY"]
    # switch back to openai
    settings2 = fake_settings(classifier_provider="openai", synthesis_provider="openai")
    secrets2 = {"OPENAI_API_KEY": True, "LARK_WEBHOOK_INDUSTRY": True, "LARK_WEBHOOK_COMPETITOR": True}
    rc2, out2, runner2, _ = run_runner(responses=responses, secrets=secrets2, settings=settings2)
    assert "Classifier Provider: openai" in out2
    assert runner2.all_required_envs == ["OPENAI_API_KEY"]


def test_secret_not_leaked_via_redact():
    from radar.acceptance import _redact
    s = "token sk-1234567890abcdef and webhook https://open.feishu.cn/open-apis/bot/v2/hook/abc123 and ghp_12345678901234567890"
    r = _redact(s)
    assert "sk-1234567890abcdef" not in r
    assert "ghp_12345678901234567890" not in r
    assert "open.feishu.cn/open-apis/bot/v2/hook" not in r
    assert "[REDACTED]" in r
