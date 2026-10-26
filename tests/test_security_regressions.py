from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from khamseen_os.contracts import (
    AuditEvent,
    Evidence,
    EvidenceKind,
    ExecutionResult,
    LifecycleStage,
    RunStatus,
    Task,
)
from khamseen_os.examples.import EngineeringWorkflowRunner, FakeRuntime, FakeStepSpec

def test_t5_secret_exposure_redacted_across_contracts() -> None:
    fake_openai = "sk-" + "liveSecretKeyValue1234567890"
    fake_gh = "ghp_" + "liveGithubTokenValue1234567890"
    fake_aws = "AKIA" + "1234567890ABCDEF"
    fake_fine_grained_pat = "github_pat_" + "11ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef1234567890"
    fake_jwt = "Bearer " + "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUPOTHSR8U"

    result = ExecutionResult(
        run_id="run_t5",
        task_id="task_t5",
        correlation_id="corr_t5",
        status=RunStatus.FAILED,
        output_text=f"Leaked key {fake_openai} and {fake_gh} and {fake_fine_grained_pat}",
        error_message=f"Auth failed with aws={fake_aws} and password=supersecretvalue and {fake_jwt}",
        raw_metadata={"api_key": fake_openai, "nested": {"access_token": fake_gh}},
    )
    assert fake_openai not in result.output_text
    assert fake_gh not in result.output_text
    assert fake_fine_grained_pat not in result.output_text
    assert fake_aws not in (result.error_message or "")
    assert "supersecretvalue" not in (result.error_message or "")
    assert fake_jwt not in (result.error_message or "")
    assert result.raw_metadata["api_key"] == "[REDACTED]"
    assert result.raw_metadata["nested"]["access_token"] == "[REDACTED]"
