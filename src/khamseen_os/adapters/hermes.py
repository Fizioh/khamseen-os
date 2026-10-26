from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from khamseen_os.contracts import (
    Evidence,
    EvidenceKind,
    ExecutionRequest,
    ExecutionResult,
    RunStatus,
    UsageMetrics,
    redact_secrets,
)

_INTERRUPTED_EXIT_CODE = 130
_WILDCARD_TOOLSETS: frozenset[str] = frozenset({"all", "*"})

_DEFAULT_PASSTHROUGH_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SystemRoot",
    "COMSPEC",
    "HOME",
    "USERPROFILE",
    "TMP",
    "TEMP",
    "TMPDIR",
    "HERMES_HOME",
    "HERMES_INFERENCE_MODEL",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "NOUS_API_KEY",
)


@dataclass(frozen=True)
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float = 0.1


SubprocessRunner = Callable[
    [list[str], float, dict[str, str], str | None, Path],
    SubprocessResult,
]


@dataclass(frozen=True)
class HermesAdapterConfig:
    binary: str = "hermes"
    profile: str | None = None
    model: str | None = None
    provider: str | None = None
    reasoning: str | None = None
    default_toolsets: tuple[str, ...] = ()
    default_skills: tuple[str, ...] = ()
    allow_wildcard_toolsets: bool = False
    passthrough_env_keys: tuple[str, ...] = _DEFAULT_PASSTHROUGH_ENV_KEYS


class HermesCliRuntimeAdapter:
    """Experimental adapter for NousResearch/hermes-agent using the verified `-z` / `--oneshot` CLI."""

    def __init__(
        self,
        config: HermesAdapterConfig | None = None,
        runner_fn: SubprocessRunner | None = None,
    ) -> None:
        self.config = config or HermesAdapterConfig()
        self._runner_fn = runner_fn
        self.cancelled_run_ids: set[str] = set()
        self.executed_commands: list[list[str]] = []

    @property
    def provider_name(self) -> str:
        return "hermes-cli"

    def healthcheck(self) -> bool:
        if self._runner_fn is not None:
            return True
        return shutil.which(self.config.binary) is not None

    def cancel(self, run_id: str) -> bool:
        self.cancelled_run_ids.add(run_id)
        return True

    def build_command(self, request: ExecutionRequest, usage_file_path: Path) -> list[str]:
        toolsets = request.allowed_tools or self.config.default_toolsets
        if not self.config.allow_wildcard_toolsets:
            for item in toolsets:
                if item.strip().lower() in _WILDCARD_TOOLSETS:
                    raise ValueError(
                        f"Wildcard Hermes toolset '{item}' is prohibited by adapter policy"
                    )

        argv: list[str] = [self.config.binary]
        if self.config.profile:
            argv.extend(["--profile", self.config.profile])
        if self.config.model:
            argv.extend(["--model", self.config.model])
        if self.config.provider:
            argv.extend(["--provider", self.config.provider])
        if self.config.reasoning:
            argv.extend(["--reasoning", self.config.reasoning])
        if toolsets:
            argv.extend(["--toolsets", ",".join(toolsets)])

        skills = request.allowed_skills or self.config.default_skills
        if skills:
            argv.extend(["--skills", ",".join(skills)])
        if request.resume_session_id:
            argv.extend(["--resume", request.resume_session_id])
        if request.workdir:
            argv.extend(["--in", request.workdir])

        argv.extend(["--oneshot", request.prompt, "--usage-file", str(usage_file_path)])
        return argv

    def build_sanitized_env(
        self,
        request: ExecutionRequest,
        base_env: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        source = base_env if base_env is not None else os.environ
        env: dict[str, str] = {}
        for key in self.config.passthrough_env_keys:
            if key in source:
                env[key] = source[key]
        env["KHAMSEEN_TASK_ID"] = request.task_id
        env["KHAMSEEN_RUN_ID"] = request.run_id
        env["KHAMSEEN_CORRELATION_ID"] = request.correlation_id
        return env

    @staticmethod
    def parse_usage_report(
        report_data: dict[str, Any],
    ) -> tuple[UsageMetrics, str | None, dict[str, Any]]:
        totals_block = report_data.get("total_including_auxiliary")
        input_tokens = int(report_data.get("input_tokens") or 0)
        output_tokens = int(report_data.get("output_tokens") or 0)

        if isinstance(totals_block, dict):
            total_tokens = int(
                totals_block.get("total_tokens")
                or report_data.get("total_tokens")
                or (input_tokens + output_tokens)
            )
            raw_cost = totals_block.get(
                "estimated_cost_usd", report_data.get("estimated_cost_usd")
            )
            api_calls = int(totals_block.get("api_calls") or report_data.get("api_calls") or 0)
        else:
            total_tokens = int(
                report_data.get("total_tokens") or (input_tokens + output_tokens)
            )
            raw_cost = report_data.get("estimated_cost_usd")
            api_calls = int(report_data.get("api_calls") or 0)

        estimated_cost_usd = float(raw_cost) if raw_cost is not None else None
        cost_source = str(report_data.get("cost_source") or "hermes_usage_file")
        session_id_val = report_data.get("session_id")
        session_id = str(session_id_val) if session_id_val else None

        usage = UsageMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            api_calls=api_calls,
            verified=True,
            cost_source=cost_source,
        )
        safe_meta = {
            "model": report_data.get("model"),
            "provider": report_data.get("provider"),
            "session_id": session_id,
            "completed": report_data.get("completed"),
            "partial": report_data.get("partial"),
            "interrupted": report_data.get("interrupted"),
            "turn_exit_reason": report_data.get("turn_exit_reason"),
            "cost_status": report_data.get("cost_status"),
        }
        return usage, session_id, safe_meta

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if request.run_id in self.cancelled_run_ids:
            return ExecutionResult(
                run_id=request.run_id,
                task_id=request.task_id,
                correlation_id=request.correlation_id,
                status=RunStatus.CANCELLED,
                output_text="",
                claimed_success=False,
                duration_seconds=0.0,
                error_code="RUN_CANCELLED",
                error_message=f"Run {request.run_id} was cancelled before Hermes dispatch",
            )

        with tempfile.TemporaryDirectory(prefix="khamseen_hermes_") as tmp_dir:
            usage_file_path = Path(tmp_dir) / f"usage_{request.run_id}.json"
            try:
                argv = self.build_command(request, usage_file_path)
            except ValueError as exc:
                return ExecutionResult(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    correlation_id=request.correlation_id,
                    status=RunStatus.FAILED,
                    output_text="",
                    claimed_success=False,
                    duration_seconds=0.0,
                    error_code="INVALID_HERMES_REQUEST",
                    error_message=str(exc),
                )

            self.executed_commands.append(argv)
            env = self.build_sanitized_env(request)

            try:
                proc_result = self._invoke(
                    argv=argv,
                    timeout_seconds=request.timeout_seconds,
                    env=env,
                    workdir=request.workdir,
                    usage_file_path=usage_file_path,
                )
            except subprocess.TimeoutExpired as exc:
                usage, session_id, report_meta = self._read_usage_if_present(usage_file_path)
                partial_out = (
                    exc.stdout.decode("utf-8", errors="replace")
                    if isinstance(exc.stdout, bytes)
                    else (exc.stdout or "")
                )
                return ExecutionResult(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    correlation_id=request.correlation_id,
                    status=RunStatus.TIMED_OUT,
                    output_text=redact_secrets(partial_out),
                    claimed_success=False,
                    duration_seconds=request.timeout_seconds,
                    usage=usage,
                    error_code="EXECUTION_TIMEOUT",
                    error_message=f"Hermes CLI timed out after {request.timeout_seconds}s",
                    external_session_id=session_id or f"hermes_timeout_{request.run_id}",
                    raw_metadata={"provider": self.provider_name, **report_meta},
                )
            except FileNotFoundError:
                return ExecutionResult(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    correlation_id=request.correlation_id,
                    status=RunStatus.FAILED,
                    output_text="",
                    claimed_success=False,
                    duration_seconds=0.0,
                    error_code="HERMES_BINARY_NOT_FOUND",
                    error_message=f"Hermes CLI binary '{self.config.binary}' was not found on PATH",
                )

            usage, session_id, report_meta = self._read_usage_if_present(usage_file_path)

            if (
                proc_result.returncode == _INTERRUPTED_EXIT_CODE
                or report_meta.get("interrupted") is True
            ):
                return ExecutionResult(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    correlation_id=request.correlation_id,
                    status=RunStatus.CANCELLED,
                    output_text=redact_secrets(proc_result.stdout),
                    claimed_success=False,
                    duration_seconds=proc_result.duration_seconds,
                    usage=usage,
                    error_code="HERMES_INTERRUPTED",
                    error_message=redact_secrets(
                        proc_result.stderr.strip() or "Hermes turn interrupted (exit 130)"
                    ),
                    external_session_id=session_id or f"hermes_int_{request.run_id}",
                    raw_metadata={"provider": self.provider_name, **report_meta},
                )

            if proc_result.duration_seconds > request.timeout_seconds:
                return ExecutionResult(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    correlation_id=request.correlation_id,
                    status=RunStatus.TIMED_OUT,
                    output_text=redact_secrets(proc_result.stdout),
                    claimed_success=False,
                    duration_seconds=proc_result.duration_seconds,
                    usage=usage,
                    error_code="EXECUTION_TIMEOUT",
                    error_message=f"Hermes CLI exceeded timeout of {request.timeout_seconds}s",
                    external_session_id=session_id or f"hermes_slow_{request.run_id}",
                    raw_metadata={"provider": self.provider_name, **report_meta},
                )

            completed_flag = report_meta.get("completed")
            if proc_result.returncode != 0 or completed_flag is False:
                reason = (
                    str(report_meta.get("turn_exit_reason") or "")
                    or proc_result.stderr.strip()
                    or f"Hermes CLI exited with code {proc_result.returncode}"
                )
                return ExecutionResult(
                    run_id=request.run_id,
                    task_id=request.task_id,
                    correlation_id=request.correlation_id,
                    status=RunStatus.FAILED,
                    output_text=redact_secrets(proc_result.stdout),
                    claimed_success=False,
                    duration_seconds=proc_result.duration_seconds,
                    usage=usage,
                    error_code="HERMES_EXECUTION_FAILED",
                    error_message=redact_secrets(reason),
                    external_session_id=session_id or f"hermes_err_{request.run_id}",
                    raw_metadata={"provider": self.provider_name, **report_meta},
                )

            evidence_items: list[Evidence] = []
            if usage.verified:
                evidence_items.append(
                    Evidence(
                        task_id=request.task_id,
                        run_id=request.run_id,
                        kind=EvidenceKind.USAGE_REPORT,
                        producer_id=request.agent_id,
                        producer_role=request.agent_role,
                        passed=True,
                        verified=True,
                        summary=f"Hermes usage ledger verified ({usage.total_tokens} tokens)",
                        details={
                            "total_tokens": usage.total_tokens,
                            "estimated_cost_usd": usage.estimated_cost_usd,
                            "session_id": session_id,
                        },
                    )
                )

            return ExecutionResult(
                run_id=request.run_id,
                task_id=request.task_id,
                correlation_id=request.correlation_id,
                status=RunStatus.SUCCEEDED,
                output_text=redact_secrets(proc_result.stdout.strip()),
                claimed_success=True,
                duration_seconds=proc_result.duration_seconds,
                usage=usage,
                evidence=tuple(evidence_items),
                external_session_id=session_id or f"hermes_sess_{request.run_id}",
                raw_metadata={"provider": self.provider_name, **report_meta},
            )

    def _invoke(
        self,
        argv: list[str],
        timeout_seconds: float,
        env: dict[str, str],
        workdir: str | None,
        usage_file_path: Path,
    ) -> SubprocessResult:
        if self._runner_fn is not None:
            return self._runner_fn(argv, timeout_seconds, env, workdir, usage_file_path)

        started = time.monotonic()
        completed = subprocess.run(
            argv,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = time.monotonic() - started
        return SubprocessResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=elapsed,
        )

    def _read_usage_if_present(
        self, usage_file_path: Path
    ) -> tuple[UsageMetrics, str | None, dict[str, Any]]:
        if not usage_file_path.is_file():
            return UsageMetrics(verified=False), None, {}
        try:
            raw = json.loads(usage_file_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return self.parse_usage_report(raw)
        except (OSError, ValueError):
            pass
        return UsageMetrics(verified=False), None, {}
