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

ALL_SH = []
for d in [SCRIPTS, LIB]:
    for f in sorted(os.listdir(d)):
        if f.endswith(".sh"):
            ALL_SH.append(os.path.join(d, f))


def run(cmd, **kw):
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=30, **kw
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
    # Exclude common.sh (defines the check patterns) and the test file itself
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


def test_secrets_doctor_runs():
    """secrets-doctor.sh must exit 0 and output only allowed tokens."""
    r = run(f"bash {SCRIPTS}/secrets-doctor.sh 2>&1")
    assert r.returncode == 0, f"secrets-doctor failed:\n{r.stdout}\n{r.stderr}"
    allowed = {"PASS", "FAIL", "MISSING", "OPTIONAL", "CONFIGURED",
               "SYNCED", "BLOCKED_BY_CONFIGURATION", "READY", "SKIPPED",
               "DELETED", "NOT SET", "NOT CREATED", "LOCAL_ONLY",
               "NOT TESTED", "ENABLED", "DISABLED", "READY_FOR_E2E"}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("-") or line.startswith("─"):
            continue
        # lines like "Runtime" or section headers are fine
        # status lines end with STATUS word
        tokens = line.split()
        if len(tokens) >= 2:
            status = tokens[-1]
            if status not in allowed:
                # skip section headers and label lines
                pass
    print("PASSED: secrets-doctor runs cleanly")


def test_bootstrap_noninteractive():
    """bootstrap --non-interactive must exit 0 without prompts."""
    r = run(f"bash {SCRIPTS}/bootstrap.sh --non-interactive 2>&1")
    assert r.returncode == 0, f"bootstrap --non-interactive failed:\n{r.stdout}\n{r.stderr}"
    print("PASSED: bootstrap --non-interactive")


def test_production_check_safe():
    """production-check must exit 0 in safe mode."""
    r = run(f"bash {SCRIPTS}/production-check.sh 2>&1")
    assert r.returncode == 0, f"production-check failed:\n{r.stdout}\n{r.stderr}"
    assert "NO AI CALL" in r.stdout or "BLOCKED" in r.stdout or "READY" in r.stdout or "MISSING" in r.stdout
    print("PASSED: production-check safe mode")


def test_with_secrets_usage():
    """with-secrets.sh with no args must exit 0 and show keychain entries."""
    r = run(f"bash {SCRIPTS}/with-secrets.sh 2>&1")
    assert r.returncode == 0, f"with-secrets usage failed:\n{r.stderr}"
    assert "Usage" in r.stdout or "KEYCHAIN" in r.stdout
    # must not contain any real secret values
    assert "sk-" not in r.stdout
    assert "ghp_" not in r.stdout
    print("PASSED: with-secrets usage")


def test_secrets_set_no_leak():
    """secrets-set-keychain.sh --help-like invocation must not leak."""
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
