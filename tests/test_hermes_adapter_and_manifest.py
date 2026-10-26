from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from khamseen_os import (
    EvidenceKind,
    ExecutionRequest,
    HermesAdapterConfig,
    HermesCliRuntimeAdapter,
    LifecycleStage,
    ManifestValidationError,
    ProviderConformanceHarness,
    RunStatus,
    SubprocessResult,
    load_and_validate_manifest,
    validate_module_manifest,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_usage_payload(
    *,
    session_id: str = "hermes_sess_abc123",
    completed: bool = True,
    interrupted: bool = False,
    turn_exit_reason: str | None = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost_usd: float = 0.0002,
) -> dict[str, Any]:
    return {
        "estimated_cost_usd": cost_usd,
        "cost_status": "estimated",
        "cost_source": "pricing_table",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "reasoning_tokens": 10,
        "total_tokens": input_tokens + output_tokens,
        "api_calls": 1,
        "model": "anthropic/claude-sonnet-4.6",
        "provider": "openrouter",
        "session_id": session_id,
        "completed": completed,
        "partial": not completed,
        "interrupted": interrupted,
        "turn_exit_reason": turn_exit_reason,
        "auxiliary": {
            "api_calls": 1,
            "input_tokens": 20,
            "output_tokens": 5,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.00005,
            "total_tokens": 25,
            "by_task": {},
        },
        "total_including_auxiliary": {
            "estimated_cost_usd": round(cost_usd + 0.00005, 6),
            "total_tokens": input_tokens + output_tokens + 25,
            "api_calls": 2,
        },
    }


def _success_runner(
    argv: list[str],
    timeout_seconds: float,
    env: dict[str, str],
    workdir: str | None,
    usage_file_path: Path,
) -> SubprocessResult:
    usage_file_path.write_text(
        json.dumps(_make_usage_payload(session_id=f"sess_{env['KHAMSEEN_RUN_ID']}")),
        encoding="utf-8",
    )
    return SubprocessResult(
        returncode=0,
        stdout="Hermes one-shot turn completed cleanly\n",
        stderr="",
        duration_seconds=0.15,
    )


def _failure_runner(
    argv: list[str],
    timeout_seconds: float,
    env: dict[str, str],
    workdir: str | None,
    usage_file_path: Path,
) -> SubprocessResult:
    usage_file_path.write_text(
        json.dumps(
            _make_usage_payload(
                session_id=f"sess_fail_{env['KHAMSEEN_RUN_ID']}",
                completed=False,
                turn_exit_reason="iteration_budget_exhausted",
            )
        ),
        encoding="utf-8",
    )
    return SubprocessResult(
        returncode=1,
        stdout="",
        stderr="Error: iteration budget exhausted",
        duration_seconds=0.2,
    )


def _timeout_runner(
    argv: list[str],
    timeout_seconds: float,
    env: dict[str, str],
    workdir: str | None,
    usage_file_path: Path,
) -> SubprocessResult:
    raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout_seconds, output="Partial stdout")


def test_hermes_adapter_passes_full_provider_conformance_harness() -> None:
    harness = ProviderConformanceHarness(
        success_provider_factory=lambda: HermesCliRuntimeAdapter(runner_fn=_success_runner),
        failure_provider_factory=lambda: HermesCliRuntimeAdapter(runner_fn=_failure_runner),
        timeout_provider_factory=lambda: HermesCliRuntimeAdapter(runner_fn=_timeout_runner),
    )
    report = harness.run_all()
    assert report.provider_name == "hermes-cli"
    for case in report.cases:
        assert case.passed, f"Hermes conformance case {case.case_name} failed: {case.detail}"
    assert report.passed is True


def test_hermes_command_builder_and_env_sanitization() -> None:
    config = HermesAdapterConfig(
        binary="hermes",
        profile="ci-worker",
        model="anthropic/claude-sonnet-4.6",
        provider="openrouter",
        reasoning="medium",
        default_toolsets=("read_file", "pytest"),
        default_skills=("hermes-agent-dev",),
    )
    adapter = HermesCliRuntimeAdapter(config=config, runner_fn=_success_runner)
    request = ExecutionRequest(
        task_id="task_42",
        run_id="run_42_1",
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        prompt="Fix bug #42",
        correlation_id="corr_42",
        workdir="/tmp/worktree",
        resume_session_id="prev_sess_01",
    )
    usage_path = Path("/tmp/usage_run_42_1.json")
    argv = adapter.build_command(request, usage_path)
    assert argv == [
        "hermes",
        "--profile",
        "ci-worker",
        "--model",
        "anthropic/claude-sonnet-4.6",
        "--provider",
        "openrouter",
        "--reasoning",
        "medium",
        "--toolsets",
        "read_file,pytest",
        "--skills",
        "hermes-agent-dev",
        "--resume",
        "prev_sess_01",
        "--in",
        "/tmp/worktree",
        "--oneshot",
        "Fix bug #42",
        "--usage-file",
        str(usage_path),
    ]

    dirty_env = {
        "PATH": "/usr/bin",
        "UNRELATED_PROD_DB_PASSWORD": "super-secret-db-password",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
    }
    clean_env = adapter.build_sanitized_env(request, base_env=dirty_env)
    assert clean_env["PATH"] == "/usr/bin"
    assert clean_env["KHAMSEEN_TASK_ID"] == "task_42"
    assert clean_env["KHAMSEEN_RUN_ID"] == "run_42_1"
    assert clean_env["KHAMSEEN_CORRELATION_ID"] == "corr_42"
    assert "UNRELATED_PROD_DB_PASSWORD" not in clean_env
    assert "AWS_SECRET_ACCESS_KEY" not in clean_env


def test_hermes_wildcard_toolset_rejected_and_exit_130_maps_to_cancelled() -> None:
    adapter = HermesCliRuntimeAdapter(runner_fn=_success_runner)
    wildcard_req = ExecutionRequest(
        task_id="task_wc",
        run_id="run_wc_1",
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        prompt="Attempt wildcard tools",
        correlation_id="corr_wc",
        allowed_tools=("all",),
    )
    wildcard_res = adapter.execute(wildcard_req)
    assert wildcard_res.status == RunStatus.FAILED
    assert wildcard_res.error_code == "INVALID_HERMES_REQUEST"

    def _interrupted_runner(
        argv: list[str],
        timeout_seconds: float,
        env: dict[str, str],
        workdir: str | None,
        usage_file_path: Path,
    ) -> SubprocessResult:
        usage_file_path.write_text(
            json.dumps(_make_usage_payload(completed=False, interrupted=True)),
            encoding="utf-8",
        )
        return SubprocessResult(returncode=130, stdout="", stderr="Interrupted by SIGINT")

    int_adapter = HermesCliRuntimeAdapter(runner_fn=_interrupted_runner)
    normal_req = ExecutionRequest(
        task_id="task_int",
        run_id="run_int_1",
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        prompt="Run and interrupt",
        correlation_id="corr_int",
    )
    int_res = int_adapter.execute(normal_req)
    assert int_res.status == RunStatus.CANCELLED
    assert int_res.error_code == "HERMES_INTERRUPTED"
    assert int_res.usage.verified is True
    assert int_res.usage.total_tokens == 175
    assert any(ev.kind == EvidenceKind.USAGE_REPORT for ev in int_res.evidence) is False


def test_reference_engineering_manifest_and_invalid_manifests() -> None:
    manifest_path = _REPO_ROOT / "examples" / "engineering-loop" / "module-manifest.json"
    manifest = load_and_validate_manifest(manifest_path)
    assert manifest.id == "engineering"
    assert manifest.chief_role == "engineering_chief"
    assert len(manifest.skills) == 3

    with pytest.raises(ManifestValidationError, match="unregistered tool"):
        validate_module_manifest(
            {
                "id": "engineering",
                "version": "0.1.0",
                "chief_role": "engineering_chief",
                "capabilities": ["code.write"],
                "tools": ["git.diff"],
                "data_scopes": ["repository:scoped"],
                "approval_policy": "policies/eng.json",
                "skills": [
                    {
                        "id": "bad_skill",
                        "capabilities": ["code.write"],
                        "allowed_tools": ["shell.arbitrary_exec"],
                    }
                ],
            }
        )

    with pytest.raises(ManifestValidationError, match="Overlapping chief_role"):
        validate_module_manifest(
            {
                "id": "engineering",
                "version": "0.1.0",
                "chief_role": "duplicate_chief",
                "capabilities": ["code.write"],
                "tools": ["git.diff"],
                "data_scopes": ["repository:scoped"],
                "approval_policy": "policies/eng.json",
            },
            existing_chief_roles={"engineering": "engineering_chief"},
        )


@pytest.mark.live_hermes
@pytest.mark.skipif(
    os.environ.get("KHAMSEEN_HERMES_LIVE_TEST") != "1" or shutil.which("hermes") is None,
    reason="Live Hermes CLI test requires KHAMSEEN_HERMES_LIVE_TEST=1 and 'hermes' binary on PATH",
)
def test_optional_live_hermes_version_check() -> None:
    adapter = HermesCliRuntimeAdapter()
    assert adapter.healthcheck() is True
