from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pipeline.llm import PROVIDER_DEFS
from pipeline.llm.registry import required_api_key_envs, resolve_role
from radar.config import ROOT, get_settings


STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_BLOCKED = "BLOCKED"
STATUS_SKIPPED = "SKIPPED"
STATUS_WARN = "WARN"


@dataclass
class CommandResult:
    rc: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class StepResult:
    no: int
    label: str
    status: str
    command: str = ""
    rc: int | None = None
    summary: str = ""
    reason: str = ""
    next_action: str = ""


def _redact(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9._-]{4,}", "[REDACTED]", text)
    text = re.sub(r"ghp_[A-Za-z0-9._-]{12,}", "[REDACTED]", text)
    text = re.sub(r"github_pat_[A-Za-z0-9._-]{12,}", "[REDACTED]", text)
    text = re.sub(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[^\s'\"]+", "[REDACTED]", text)
    text = re.sub(r"https://open\.larksuite\.com/open-apis/bot/v2/hook/[^\s'\"]+", "[REDACTED]", text)
    return text


def _summary(text: str, limit: int = 3) -> str:
    lines = [line.strip() for line in _redact(text).splitlines() if line.strip()]
    if not lines:
        return "(no output)"
    if len(lines) <= limit:
        return " | ".join(lines)
    return " | ".join(lines[-limit:])


def _dotted(label: str, width: int = 30) -> str:
    pad = max(1, width - len(label))
    return f"{label}{'.' * pad}"


def _parse_bash_array(src: str, name: str) -> list[str]:
    lines = src.splitlines()
    capture = False
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not capture:
            if line.startswith(f"{name}=("):
                capture = True
            continue
        if line == ")":
            break
        if not line or line.startswith("#"):
            continue
        match = re.search(r'"([^"]+)"', line)
        if match:
            out.append(match.group(1))
    return out


def _load_keychain_mapping(repo_root: Path) -> tuple[dict[str, str], dict[str, str], list[str]]:
    source = (repo_root / "scripts" / "lib" / "keychain.sh").read_text()
    services = _parse_bash_array(source, "RADAR_SERVICES")
    envs = _parse_bash_array(source, "RADAR_ENV_NAMES")
    required = _parse_bash_array(source, "RADAR_REQUIRED_SERVICES")
    env_to_service = {env: svc for svc, env in zip(services, envs)}
    service_to_env = {svc: env for svc, env in zip(services, envs)}
    return env_to_service, service_to_env, required


class SubprocessExecutor:
    def run(self, name: str, cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 120) -> CommandResult:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return CommandResult(proc.returncode, proc.stdout or "", proc.stderr or "")


class AcceptanceRunner:
    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        repo: str | None = None,
        settings: dict | None = None,
        executor: SubprocessExecutor | None = None,
        secret_exists: Callable[[str], bool] | None = None,
        no_ai: bool = False,
        no_push: bool = False,
        e2e: bool = False,
    ) -> None:
        self.repo_root = repo_root or ROOT
        self.repo = repo or os.getenv("GH_REPO", "JerseyBro/web3-radar")
        self.settings = settings or get_settings()
        self.models = self.settings["models"]
        self.executor = executor or SubprocessExecutor()
        self.no_ai = no_ai
        self.no_push = no_push
        self.e2e = e2e
        self.results: list[StepResult] = []
        self.notes: list[str] = []
        self.env_to_service, self.service_to_env, self.required_services = _load_keychain_mapping(self.repo_root)
        self.secret_exists = secret_exists or self._secret_exists
        self.python_bin = self._select_python_bin()
        self.role_resolved = {
            "classifier": resolve_role(self.models, "classifier"),
            "synthesis": resolve_role(self.models, "synthesis"),
        }
        self.role_required_envs = {
            role: self._role_envs(role) for role in ("classifier", "synthesis")
        }
        self.all_required_envs = sorted(required_api_key_envs(self.models))

    def _secret_exists(self, env_name: str) -> bool:
        svc = self.env_to_service.get(env_name)
        if not svc:
            return False
        return self._keychain_exists(svc)

    @staticmethod
    def _keychain_exists(service: str) -> bool:
        user = os.getenv("USER", "")
        try:
            proc = subprocess.run(
                ["security", "find-generic-password", "-a", user, "-s", service],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        return proc.returncode == 0

    def _select_python_bin(self) -> str:
        candidates = [
            os.getenv("PYTHON_BIN"),
            str(self.repo_root / ".venv" / "bin" / "python"),
            str(Path.home() / ".agent-reach-venv" / "bin" / "python3.12"),
            shutil.which("python3.12"),
            shutil.which("python3"),
            shutil.which("python"),
            sys.executable,
        ]
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            if not Path(candidate).exists():
                continue
            try:
                probe = subprocess.run([candidate, "-c", "import openai, httpx"], capture_output=True, text=True)
            except Exception:
                continue
            if probe.returncode == 0:
                return candidate
        return sys.executable

    def _role_envs(self, role: str) -> list[str]:
        envs: list[str] = []
        resolved = self.role_resolved.get(role, {})
        user_providers = self.models.get("providers", {}) or {}
        for slot in ("primary", "fallback"):
            item = resolved.get(slot)
            if not item:
                continue
            provider = item[0]
            cfg = user_providers.get(provider) or PROVIDER_DEFS.get(provider, {})
            env_name = cfg.get("api_key_env") or f"{provider.upper()}_API_KEY"
            if env_name not in envs:
                envs.append(env_name)
        return envs

    def _provider_model(self, role: str) -> tuple[str, str]:
        primary = self.role_resolved[role].get("primary")
        if not primary:
            return ("?", "?")
        return primary

    def _record(self, label: str, status: str, *, command: str = "", rc: int | None = None, summary: str = "", reason: str = "", next_action: str = "") -> StepResult:
        step = StepResult(len(self.results) + 1, label, status, command, rc, summary, reason, next_action)
        self.results.append(step)
        return step

    def _print_step(self, step: StepResult) -> None:
        print(f"[{step.no:02d}] {_dotted(step.label)} {step.status}")
        if step.command:
            print(f"      command: {step.command}")
        if step.rc is not None:
            print(f"      exit: {step.rc}")
        if step.summary:
            print(f"      summary: {step.summary}")
        if step.reason:
            print(f"      reason: {step.reason}")
        if step.next_action:
            print(f"      next: {step.next_action}")

    def _run(self, name: str, cmd: list[str]) -> CommandResult:
        return self.executor.run(name, cmd, cwd=self.repo_root)

    def _classify_text(self, text: str) -> str:
        low = text.lower()
        if "warn:" in low:
            return STATUS_WARN
        return STATUS_PASS

    def _github_cli(self) -> None:
        if shutil.which("gh") is None:
            self._record("GitHub CLI", STATUS_BLOCKED, reason="gh CLI missing", next_action="Install GitHub CLI then re-run ./scripts/acceptance.sh")
            for label in ("GitHub Authentication", "Repository Access", "Contents Write", "Workflow Permission"):
                self._record(label, STATUS_SKIPPED, reason="blocked by missing gh CLI")
            return

        res = self._run("gh-version", ["gh", "--version"])
        text = _redact(res.stdout + res.stderr)
        status = STATUS_PASS if res.rc == 0 else STATUS_FAIL
        self._record("GitHub CLI", status, command=shlex.join(["gh", "--version"]), rc=res.rc, summary=_summary(text), reason="gh available" if status == STATUS_PASS else "gh --version failed", next_action="")

        auth = self._run("gh-auth", ["gh", "auth", "status"])
        auth_text = _redact(auth.stdout + auth.stderr)
        auth_ok = auth.rc == 0
        auth_status = STATUS_PASS if auth_ok else STATUS_BLOCKED
        auth_reason = "authenticated" if auth_ok else self._classify_auth_failure(auth_text)
        self._record("GitHub Authentication", auth_status, command=shlex.join(["gh", "auth", "status"]), rc=auth.rc, summary=_summary(auth_text), reason=auth_reason, next_action=self._next_auth_action(auth_status))

        if not auth_ok:
            self._record("Repository Access", STATUS_SKIPPED, reason="blocked by GitHub authentication")
            self._record("Contents Write", STATUS_SKIPPED, reason="blocked by GitHub authentication")
            self._record("Workflow Permission", STATUS_SKIPPED, reason="blocked by GitHub authentication")
            return

        repo = self._run("gh-repo-view", ["gh", "repo", "view", self.repo, "--json", "name"])
        repo_text = _redact(repo.stdout + repo.stderr)
        repo_ok = repo.rc == 0
        self._record(
            "Repository Access",
            STATUS_PASS if repo_ok else STATUS_BLOCKED,
            command=shlex.join(["gh", "repo", "view", self.repo, "--json", "name"]),
            rc=repo.rc,
            summary=_summary(repo_text),
            reason="repository accessible" if repo_ok else "repository access denied",
            next_action="Contact repo admin or fix GH permissions" if not repo_ok else "",
        )

        contents = self._run("gh-contents-write", ["gh", "api", f"repos/{self.repo}", "--jq", ".permissions.push"])
        contents_text = _redact(contents.stdout + contents.stderr)
        contents_ok = contents.rc == 0 and contents_text.strip().lower().endswith("true")
        self._record(
            "Contents Write",
            STATUS_PASS if contents_ok else STATUS_BLOCKED,
            command=shlex.join(["gh", "api", f"repos/{self.repo}", "--jq", ".permissions.push"]),
            rc=contents.rc,
            summary=_summary(contents_text),
            reason="contents write enabled" if contents_ok else "contents:write missing",
            next_action="Refresh gh auth with repo,workflow if needed" if not contents_ok else "",
        )

        workflow = self._run("gh-workflow-scope", ["gh", "api", "-i", "user"])
        workflow_text = _redact(workflow.stdout + workflow.stderr)
        workflow_ok = False
        scopes_match = re.search(r"^x-oauth-scopes:\s*(.+)$", workflow_text, re.IGNORECASE | re.MULTILINE)
        if scopes_match:
            scopes = [s.strip().lower() for s in scopes_match.group(1).split(",")]
            workflow_ok = "workflow" in scopes
        self._record(
            "Workflow Permission",
            STATUS_PASS if workflow_ok else STATUS_BLOCKED,
            command=shlex.join(["gh", "api", "-i", "user"]),
            rc=workflow.rc,
            summary=_summary(workflow_text),
            reason="workflow scope present" if workflow_ok else "workflow scope missing",
            next_action="gh auth refresh -s repo,workflow" if not workflow_ok else "",
        )

    @staticmethod
    def _classify_auth_failure(text: str) -> str:
        low = text.lower()
        if "not logged in" in low or "not authenticated" in low:
            return "not authenticated"
        if "permission" in low or "denied" in low:
            return "authentication/permission failure"
        return "gh auth status failed"

    @staticmethod
    def _next_auth_action(status: str) -> str:
        if status == STATUS_BLOCKED:
            return "Run gh auth login or gh auth refresh -s repo,workflow"
        return ""

    def _bootstrap(self) -> None:
        res = self._run("bootstrap", ["bash", str(self.repo_root / "scripts" / "bootstrap.sh"), "--non-interactive"])
        text = _redact(res.stdout + res.stderr)
        if "READY_FOR_E2E" in text:
            status = STATUS_PASS
            reason = "bootstrap ready"
        elif "BLOCKED_BY_CONFIGURATION" in text:
            status = STATUS_BLOCKED
            reason = "bootstrap blocked by configuration"
        elif res.rc == 0:
            status = STATUS_PASS
            reason = "bootstrap completed"
        else:
            status = STATUS_FAIL
            reason = "bootstrap failed"
        self._record("Secret Bootstrap Check", status, command=shlex.join(["bash", str(self.repo_root / "scripts" / "bootstrap.sh"), "--non-interactive"]), rc=res.rc, summary=_summary(text), reason=reason, next_action="Fix the listed configuration blocker(s) and re-run" if status == STATUS_BLOCKED else "")

    def _secret_step(self, label: str, envs: list[str], *, missing_reason: str) -> StepResult:
        present = [env for env in envs if self.secret_exists(env)]
        status = STATUS_PASS if present else STATUS_BLOCKED
        reason = f"present: {', '.join(present)}" if present else missing_reason
        next_action = "Configure the missing Secret(s) and re-run" if not present else ""
        summary = f"env(s): {', '.join(envs)}"
        if present:
            summary += f" | present: {', '.join(present)}"
        return self._record(label, status, summary=summary, reason=reason, next_action=next_action)

    def _github_secret_sync(self) -> None:
        self._record("GitHub Secret Sync", STATUS_SKIPPED, reason="read-only acceptance; sync is intentional/manual", next_action="Use ./scripts/secrets-sync-github.sh only when you intend to write GitHub Secrets")

    def _production_check(self) -> None:
        res = self._run("production-check", ["bash", str(self.repo_root / "scripts" / "production-check.sh")])
        text = _redact(res.stdout + res.stderr)
        if "READY_FOR_E2E" in text:
            status = STATUS_PASS
            reason = "production ready"
        elif "BLOCKED_BY_CONFIGURATION" in text:
            status = STATUS_BLOCKED
            reason = "production blocked by configuration"
        elif res.rc == 0:
            status = STATUS_PASS
            reason = "production check completed"
        else:
            status = STATUS_FAIL
            reason = "production check failed"
        self._record("Production Readiness", status, command=shlex.join(["bash", str(self.repo_root / "scripts" / "production-check.sh")]), rc=res.rc, summary=_summary(text), reason=reason, next_action="Resolve the blocker(s) above and re-run" if status == STATUS_BLOCKED else "")

    @staticmethod
    def _classify_ai(result: CommandResult) -> tuple[str, str]:
        text = (result.stdout + result.stderr).lower()
        if "result: blocked_by_configuration" in text or "llm provider: blocked_by_configuration" in text:
            return STATUS_BLOCKED, "configuration missing"
        if "structured output: fail" in text or "result: fail" in text:
            return STATUS_FAIL, "structured output failed"
        if any(tok in text for tok in ("unauthorized", "invalid_api_key", "401", "403", "billing", "model_not_found", "not found")):
            return STATUS_BLOCKED, "provider auth/model/config issue"
        if any(tok in text for tok in ("rate limit", "timeout", "network")):
            return STATUS_BLOCKED, "transient provider/network issue"
        if result.rc == 0:
            return STATUS_PASS, "ai smoke passed"
        return STATUS_FAIL, "ai smoke failed"

    @staticmethod
    def _classify_lark(result: CommandResult) -> tuple[str, str]:
        text = (result.stdout + result.stderr).lower()
        if "[deliver:lark] success" in text:
            return STATUS_PASS, "lark delivery succeeded"
        if "[deliver:lark] skipped" in text:
            return STATUS_SKIPPED, "lark delivery skipped (idempotency)"
        if "[deliver:lark] preview" in text:
            return STATUS_WARN, "preview only"
        if "invalid_webhook" in text or "signature_error" in text or "keyword_rejected" in text or "ip_rejected" in text:
            return STATUS_BLOCKED, "delivery configuration rejected"
        if "invalid_payload" in text:
            return STATUS_FAIL, "invalid payload"
        if "rate_limit" in text or "timeout" in text or "network_error" in text:
            return STATUS_BLOCKED, "transient delivery issue"
        if result.rc == 0:
            return STATUS_PASS, "lark command completed"
        return STATUS_FAIL, "lark delivery failed"

    def _run_ai_smoke(self, label: str, model_arg: str, envs: list[str]) -> None:
        if self.no_ai:
            self._record(label, STATUS_SKIPPED, reason="--no-ai supplied")
            return
        if not any(self.secret_exists(env) for env in envs):
            self._record(label, STATUS_SKIPPED, reason="blocked by missing LLM Secret(s)", next_action="Configure the required LLM Secret(s) and re-run")
            return
        cmd = ["bash", str(self.repo_root / "scripts" / "with-secrets.sh"), self._python_bin(), "-m", "radar", "ai-test"]
        if model_arg == "synthesis":
            cmd.extend(["--model", "synthesis"])
        res = self._run(label.lower().replace(" ", "-"), cmd)
        status, reason = self._classify_ai(res)
        self._record(label, status, command=shlex.join(cmd), rc=res.rc, summary=_summary(res.stdout + res.stderr), reason=reason, next_action="Check the provider error above and re-run" if status in (STATUS_BLOCKED, STATUS_FAIL) else "")

    def _run_lark_smoke(self, label: str, radar: str, env_name: str) -> None:
        if self.no_push:
            self._record(label, STATUS_SKIPPED, reason="--no-push supplied")
            return
        if not self.secret_exists(env_name):
            self._record(label, STATUS_SKIPPED, reason=f"blocked by missing {env_name}", next_action="Configure the webhook Secret and re-run")
            return
        report_id = f"acceptance-{radar}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        cmd = [
            "bash", str(self.repo_root / "scripts" / "with-secrets.sh"), self._python_bin(),
            "-m", "radar", "output-test", "--target", "lark", "--radar", radar, "--push",
            "--force-push", "--report-id", report_id,
        ]
        res = self._run(f"lark-{radar}", cmd)
        status, reason = self._classify_lark(res)
        self._record(label, status, command=shlex.join(cmd), rc=res.rc, summary=_summary(res.stdout + res.stderr), reason=reason, next_action="Check webhook / signing / network and re-run" if status in (STATUS_BLOCKED, STATUS_FAIL) else "")

    def _run_scan(self) -> None:
        cmd = ["bash", str(self.repo_root / "scripts" / "with-secrets.sh"), self._python_bin(), "-m", "radar", "scan", "--no-ai"]
        res = self._run("scan", cmd)
        text = _redact(res.stdout + res.stderr)
        if "blocked_by_configuration" in text.lower():
            status, reason = STATUS_BLOCKED, "scan blocked by configuration"
        elif res.rc == 0:
            status, reason = self._classify_text(text), "scan completed"
        else:
            status, reason = STATUS_FAIL, "scan failed"
        self._record("Basic Radar Scan", status, command=shlex.join(cmd), rc=res.rc, summary=_summary(text), reason=reason, next_action="Inspect the scan error above" if status == STATUS_FAIL else "")

    def _run_e2e(self, radar: str) -> None:
        if not self.e2e:
            self._record(f"Production E2E {radar.capitalize()}", STATUS_SKIPPED, reason="--e2e not supplied")
            return
        if self.no_push:
            self._record(f"Production E2E {radar.capitalize()}", STATUS_SKIPPED, reason="--no-push supplied")
            return
        required = "LARK_WEBHOOK_INDUSTRY" if radar == "industry" else "LARK_WEBHOOK_COMPETITOR"
        if not self.secret_exists(required):
            self._record(f"Production E2E {radar.capitalize()}", STATUS_SKIPPED, reason=f"blocked by missing {required}")
            return
        cmd = ["bash", str(self.repo_root / "scripts" / "with-secrets.sh"), self._python_bin(), "-m", "radar", radar, "--weekly", "--output", "lark,file", "--push"]
        res = self._run(f"e2e-{radar}", cmd)
        text = _redact(res.stdout + res.stderr)
        if res.rc == 0:
            status, reason = STATUS_PASS, f"{radar} e2e passed"
        elif "blocked_by_configuration" in text.lower():
            status, reason = STATUS_BLOCKED, f"{radar} e2e blocked by configuration"
        else:
            status, reason = STATUS_FAIL, f"{radar} e2e failed"
        self._record(f"Production E2E {radar.capitalize()}", status, command=shlex.join(cmd), rc=res.rc, summary=_summary(text), reason=reason, next_action="Resolve the blocker(s) and re-run with --e2e" if status in (STATUS_BLOCKED, STATUS_FAIL) else "")

    def _python_bin(self) -> str:
        return self.python_bin

    def _print_header(self) -> None:
        classifier_provider, classifier_model = self._provider_model("classifier")
        synthesis_provider, synthesis_model = self._provider_model("synthesis")
        print("Web3 Intelligence Radar Acceptance")
        print("===================================\n")
        print(f"Repository: {self.repo}")
        print(f"Classifier Provider: {classifier_provider}")
        print(f"Classifier Model: {classifier_model}")
        print(f"Synthesis Provider: {synthesis_provider}")
        print(f"Synthesis Model: {synthesis_model}")
        print(f"Required Secret Env(s): {', '.join(self.all_required_envs) if self.all_required_envs else '(none)'}")
        print("REAL LLM API CALL: classifier / synthesis smoke")
        print("REAL LARK MESSAGE: industry / competitor smoke")
        google_service = self.env_to_service.get("GEMINI_API_KEY")
        if google_service and self.secret_exists("GEMINI_API_KEY") and classifier_provider != "google" and synthesis_provider != "google":
            self.notes.append("WARN: Google Gemini API key configured but active provider is not google.")

    def _print_notes(self) -> None:
        for note in self.notes:
            print(note)

    def run(self) -> int:
        self._print_header()
        self._print_notes()
        self._github_cli()
        self._bootstrap()
        self._secret_step("LLM Secret (Classifier)", self.role_required_envs["classifier"], missing_reason="missing classifier LLM Secret(s)")
        self._secret_step("LLM Secret (Synthesis)", self.role_required_envs["synthesis"], missing_reason="missing synthesis LLM Secret(s)")
        self._secret_step("Industry Webhook", ["LARK_WEBHOOK_INDUSTRY"], missing_reason="missing LARK_WEBHOOK_INDUSTRY")
        self._secret_step("Competitor Webhook", ["LARK_WEBHOOK_COMPETITOR"], missing_reason="missing LARK_WEBHOOK_COMPETITOR")
        self._github_secret_sync()
        self._production_check()

        self._run_ai_smoke("LLM Classifier Smoke", "classifier", self.role_required_envs["classifier"])
        self._run_ai_smoke("LLM Synthesis Smoke", "synthesis", self.role_required_envs["synthesis"])
        self._run_lark_smoke("Lark Industry Smoke", "industry", "LARK_WEBHOOK_INDUSTRY")
        self._run_lark_smoke("Lark Competitor Smoke", "competitor", "LARK_WEBHOOK_COMPETITOR")
        self._run_scan()
        self._run_e2e("industry")
        self._run_e2e("competitor")

        for step in self.results:
            self._print_step(step)

        return self._print_summary()

    def _print_summary(self) -> int:
        counts = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_BLOCKED: 0, STATUS_FAIL: 0, STATUS_SKIPPED: 0}
        for step in self.results:
            counts[step.status] = counts.get(step.status, 0) + 1
        counts[STATUS_WARN] += len(self.notes)

        print("\n===================================")
        print("Acceptance Summary")
        print("===================================\n")
        print(f"PASS      {counts[STATUS_PASS]}")
        print(f"WARN      {counts[STATUS_WARN]}")
        print(f"BLOCKED   {counts[STATUS_BLOCKED]}")
        print(f"FAIL      {counts[STATUS_FAIL]}")
        print(f"SKIPPED   {counts[STATUS_SKIPPED]}")

        overall = self._overall_status(counts)
        print(f"\nOverall:\n{overall}")
        print("\nNext Action:")
        for step in self.results:
            if step.status in (STATUS_BLOCKED, STATUS_FAIL):
                if step.next_action:
                    print(f"1. {step.next_action}")
                else:
                    print("1. Re-run ./scripts/acceptance.sh after fixing the blocker")
                break
        else:
            if overall in ("BASIC_ACCEPTANCE_PASS", "FULL_ACCEPTANCE_PASS"):
                if self.e2e:
                    print("1. Review the E2E artifacts and reports")
                else:
                    print("1. ./scripts/acceptance.sh --e2e")
            else:
                print("1. Re-run ./scripts/acceptance.sh")

        return 0 if overall in ("BASIC_ACCEPTANCE_PASS", "FULL_ACCEPTANCE_PASS") else (2 if counts[STATUS_BLOCKED] else 1)

    def _overall_status(self, counts: dict[str, int]) -> str:
        if counts[STATUS_FAIL] > 0:
            return "FAIL"
        if counts[STATUS_BLOCKED] > 0:
            return "BLOCKED_BY_CONFIGURATION"
        if self.e2e:
            return "FULL_ACCEPTANCE_PASS"
        return "BASIC_ACCEPTANCE_PASS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="acceptance")
    parser.add_argument("--repo", default=os.getenv("GH_REPO", "JerseyBro/web3-radar"))
    parser.add_argument("--e2e", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args(argv)

    runner = AcceptanceRunner(repo=args.repo, no_ai=args.no_ai, no_push=args.no_push, e2e=args.e2e)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
