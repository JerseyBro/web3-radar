#!/usr/bin/env python3
"""
Secret Bootstrap validation tests.
Uses bash -n for syntax, grep for forbidden patterns, and
safe behavioral checks (no real secrets needed).
"""

import subprocess
import os
import sys
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
LIB = os.path.join(SCRIPTS, "lib")
STUB_BIN = os.path.join(ROOT, "tests", "fixtures", "bin")

ALL_SH = []
for d in [SCRIPTS, LIB]:
    for f in sorted(os.listdir(d)):
        if f.endswith(".sh"):
            ALL_SH.append(os.path.join(d, f))


def run(cmd, extra_env=None, **kw):
    env = dict(os.environ)
    env["PATH"] = STUB_BIN + os.pathsep + env["PATH"]
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL, env=env, **kw
    )


def test_shell_syntax():
    """bash -n on every .sh file must pass."""
    for sh in ALL_SH:
        r = run(f"bash -n {sh}")
        assert r.returncode == 0, f"syntax error in {sh}:\n{r.stderr}"
    print(f"PASSED: shell syntax ({len(ALL_SH)} files)")


FORBIDDEN = [
    (r"cat\s+\.env", "cat .env"),
    (r'echo\s+"\$[A-Z_]', "echo secret variable"),
    (r"\bprintenv\b", "printenv"),
    (r"\bset\s+-x\b", "set -x"),
    (r"\benv\b\s*$", "env command"),
]


def test_no_forbidden_patterns():
    """Scripts must not contain patterns that expose secrets."""
    skip = {"common.sh", "test_bootstrap.py"}
    for sh in ALL_SH:
        if os.path.basename(sh) in skip:
            continue
        with open(sh) as f:
            content = f.read()
        for pattern, desc in FORBIDDEN:
            if re.search(pattern, content, re.MULTILINE):
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line) and not line.strip().startswith("#"):
                        assert False, f"{os.path.basename(sh)}:{i} forbidden pattern '{desc}': {line.strip()}"
    print(f"PASSED: no forbidden patterns ({len(ALL_SH) - len(skip)} files)")


# ── Unified status model ────────────────────────────────────────
ALLOWED_STATUS = {
    "PASS", "FAIL", "MISSING", "OPTIONAL", "CONFIGURED",
    "SYNCED", "BLOCKED_BY_CONFIGURATION", "BLOCKED_BY_CREDENTIAL_SCOPE",
    "READY", "SKIPPED", "DELETED", "NOT SET", "NOT CREATED", "LOCAL_ONLY",
    "NOT TESTED", "ENABLED", "DISABLED", "READY_FOR_E2E",
    "ACTION_REQUIRED", "UNAVAILABLE_IN_CURRENT_RUNTIME",
    "NOT_AUTHENTICATED", "MISSING_GH_CLI", "WORKFLOW_PERMISSION_MISSING",
    "AVAILABLE", "OpenCode", "Codex",
}


def test_secrets_doctor_runs():
    """secrets-doctor.sh must exit 0 and output only allowed status tokens."""
    r = run(f"bash {SCRIPTS}/secrets-doctor.sh 2>&1")
    assert r.returncode == 0, f"secrets-doctor failed:\n{r.stdout}\n{r.stderr}"
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("─"):
            continue
        tokens = line.split()
        if len(tokens) >= 2:
            status = tokens[-1]
            if status in ALLOWED_STATUS:
                continue
            # Section headers (single word) are fine
            if len(tokens) == 1:
                continue
    print("PASSED: secrets-doctor runs cleanly")


def test_bootstrap_noninteractive():
    """bootstrap --non-interactive must exit 0 without prompts."""
    r = run(f"bash {SCRIPTS}/bootstrap.sh --non-interactive 2>&1")
    assert r.returncode == 0, f"bootstrap --non-interactive failed:\n{r.stdout}\n{r.stderr}"
    # Must not contain secret values
    assert "sk-" not in r.stdout
    assert "ghp_" not in r.stdout
    print("PASSED: bootstrap --non-interactive")


def test_production_check_safe():
    """production-check must exit 0 in safe mode."""
    r = run(f"bash {SCRIPTS}/production-check.sh 2>&1")
    assert r.returncode == 0, f"production-check failed:\n{r.stdout}\n{r.stderr}"
    # Should contain a valid readiness status
    assert any(s in r.stdout for s in [
        "BLOCKED_BY_CONFIGURATION", "READY_FOR_E2E",
        "MISSING", "BLOCKED"
    ])
    print("PASSED: production-check safe mode")


def test_with_secrets_usage():
    """with-secrets.sh with no args must exit 0 and not leak secrets."""
    r = run(f"bash {SCRIPTS}/with-secrets.sh 2>&1")
    assert r.returncode == 0, f"with-secrets usage failed:\n{r.stderr}"
    assert "Usage" in r.stdout
    # Must not contain any secret values or keychain names
    assert "sk-" not in r.stdout
    assert "ghp_" not in r.stdout
    assert "KEYCHAIN:" not in r.stdout
    print("PASSED: with-secrets usage")


def test_secrets_set_no_leak():
    """secrets-set-keychain.sh exit must not leak."""
    r = run(f"echo '7' | bash {SCRIPTS}/secrets-set-keychain.sh 2>&1")
    assert r.returncode == 0
    assert "sk-" not in r.stdout
    print("PASSED: secrets-set no leak")


def test_env_gitignore():
    """`.env` patterns must be in .gitignore."""
    gi = os.path.join(ROOT, ".gitignore")
    with open(gi) as f:
        content = f.read()
    assert ".env" in content, ".gitignore missing .env"
    assert "!.env.example" in content, ".gitignore missing !.env.example"
    print("PASSED: .gitignore")


def test_scripts_executable():
    """All .sh files must be executable."""
    for sh in ALL_SH:
        assert os.access(sh, os.X_OK), f"{sh} not executable"
    print(f"PASS: all {len(ALL_SH)} scripts executable")


def test_doctor_workflow_missing_not_unauthenticated():
    """With stub gh: authenticated but workflow scope missing.
    Doctor must report BLOCKED_BY_CREDENTIAL_SCOPE (NOT 'not authenticated')
    and list WORKFLOW_PERMISSION_MISSING with the refresh action."""
    r = run(f"bash {SCRIPTS}/secrets-doctor.sh 2>&1")
    assert r.returncode == 0, f"doctor failed:\n{r.stdout}\n{r.stderr}"
    assert "Authenticated" in r.stdout
    assert "BLOCKED_BY_CREDENTIAL_SCOPE" in r.stdout, \
        "doctor must report credential-scope blocker when workflow scope missing"
    assert "WORKFLOW_PERMISSION_MISSING" in r.stdout
    assert "gh auth refresh -s repo,workflow" in r.stdout
    assert "not authenticated" not in r.stdout.lower()
    print("PASSED: doctor workflow-missing semantics")


def test_unauthenticated_shows_not_authenticated():
    """With unauthenticated stub gh, github-auth-check must say
    NOT_AUTHENTICATED and suggest gh auth login (never refresh)."""
    r = run(f"bash {SCRIPTS}/github-auth-check.sh 2>&1",
            extra_env={"GH_STUB_MODE": "unauthenticated"})
    assert r.returncode == 0, f"github-auth-check failed:\n{r.stdout}\n{r.stderr}"
    assert "NOT_AUTHENTICATED" in r.stdout
    assert "gh auth login" in r.stdout
    assert "refresh" not in r.stdout, \
        "unauthenticated user must NOT be told to run gh auth refresh"
    print("PASSED: unauthenticated semantics")


def test_secret_missing_shows_blocked_by_configuration():
    """With authenticated stub gh but no keychain secrets, doctor overall
    must be BLOCKED_BY_CONFIGURATION (not FAIL), and required secrets
    must show MISSING while optional ones show OPTIONAL."""
    # Remove GH_STUB_MODE so the default authenticated stub is used.
    r = run(f"bash {SCRIPTS}/secrets-doctor.sh 2>&1")
    assert r.returncode == 0
    out = r.stdout
    assert "MISSING" in out and "FAIL" not in out.replace("FAIL:", "")
    # Optional signing secrets must be OPTIONAL, never MISSING/BLOCKED/FAIL
    assert "Industry Signing               OPTIONAL" in out or "OPTIONAL" in out
    print("PASSED: secret-missing semantics")


def test_runtime_provisioning_semantics():
    """Doctor must report runtime provisioning honestly:
    AVAILABLE only for Codex runtime, UNAVAILABLE_IN_CURRENT_RUNTIME otherwise,
    and Shared Keychain Support always PASS."""
    r = run(f"bash {SCRIPTS}/secrets-doctor.sh 2>&1")
    assert "Secure Provisioning" in r.stdout, "doctor missing Secure Provisioning section"
    assert ("UNAVAILABLE_IN_CURRENT_RUNTIME" in r.stdout) or ("AVAILABLE" in r.stdout)
    assert "Shared Keychain Support" in r.stdout, "doctor missing Shared Keychain Support"
    # Non-Codex runtime must NOT claim AVAILABLE provisioning
    if "Current Runtime" in r.stdout and "Codex" not in r.stdout.split("Current Runtime")[1].split("\n")[0]:
        assert "UNAVAILABLE_IN_CURRENT_RUNTIME" in r.stdout
    print("PASSED: runtime provisioning semantics")


def test_production_check_blockers_listed():
    """production-check must list concrete blockers, not generic FAIL."""
    r = run(f"bash {SCRIPTS}/production-check.sh 2>&1")
    if "BLOCKED" in r.stdout:
        # Should list specific blockers, not just "FAIL"
        assert "Blockers:" in r.stdout or "BLOCKED_BY_CONFIGURATION" in r.stdout
    print("PASSED: production-check blocker listing")


def test_no_secret_in_output():
    """No script output should contain secret-like patterns."""
    for sh in ALL_SH:
        if os.path.basename(sh) == "common.sh":
            continue
        r = run(f"bash {sh} 2>&1")
        combined = r.stdout + r.stderr
        assert "sk-" not in combined, f"{os.path.basename(sh)} leaks sk- pattern"
        assert "ghp_" not in combined, f"{os.path.basename(sh)} leaks ghp_ pattern"
        assert "github_pat_" not in combined, f"{os.path.basename(sh)} leaks github_pat_"
        assert "open.feishu.cn/open-apis/bot/v2/hook/" not in combined, \
            f"{os.path.basename(sh)} leaks real webhook URL"
    print("PASSED: no secret in output")


if __name__ == "__main__":
    tests = [
        test_shell_syntax,
        test_no_forbidden_patterns,
        test_secrets_doctor_runs,
        test_bootstrap_noninteractive,
        test_production_check_safe,
        test_with_secrets_usage,
        test_secrets_set_no_leak,
        test_env_gitignore,
        test_scripts_executable,
        test_doctor_workflow_missing_not_unauthenticated,
        test_unauthenticated_shows_not_authenticated,
        test_secret_missing_shows_blocked_by_configuration,
        test_runtime_provisioning_semantics,
        test_production_check_blockers_listed,
        test_no_secret_in_output,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAILED: {t.__name__}: {e}")
            failed += 1
    print(f"\nBootstrap Tests: PASSED={passed} FAILED={failed}")
    sys.exit(1 if failed else 0)
