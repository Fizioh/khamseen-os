from __future__ import annotations

import pytest

from khamseen_os import (
    ExecutionRequest,
    FakeRuntime,
    FakeStepSpec,
    LifecycleStage,
    ProviderConformanceHarness,
    RunStatus,
    RuntimeProvider,
)


def test_fake_runtime_satisfies_full_conformance_harness() -> None:
    harness = ProviderConformanceHarness.for_fake_runtime()
    report = harness.run_all()
    assert report.provider_name == "fake"
    assert len(report.cases) == 9
    for case in report.cases:
        assert case.passed, f"Conformance case {case.case_name} failed: {case.detail}"
    assert report.passed is True


@pytest.mark.parametrize(
    "case_method",
    [
        "check_successful_execution",
        "check_runtime_failure",
        "check_timeout_and_cancellation",
        "check_repeated_failures",
        "check_missing_evidence",
        "check_budget_rejection",
        "check_approval_required",
        "check_normalized_results",
        "check_repeated_event_delivery",
    ],
)
def test_individual_conformance_cases(case_method: str) -> None:
    harness = ProviderConformanceHarness.for_fake_runtime()
    method = getattr(harness, case_method)
    result = method()
    assert result.passed is True, f"{result.case_name} failed: {result.detail}"


def test_unhealthy_provider_reports_failure() -> None:
    runtime = FakeRuntime(healthy=False)
    assert isinstance(runtime, RuntimeProvider)
    assert runtime.healthcheck() is False
    req = ExecutionRequest(
        task_id="task_unhealthy",
        run_id="run_unhealthy_1",
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        prompt="Attempt execution on unhealthy provider",
        correlation_id="corr_unhealthy",
    )
    res = runtime.execute(req)
    assert res.status == RunStatus.FAILED
    assert res.error_code == "PROVIDER_UNHEALTHY"


def test_duration_exceeding_request_timeout_maps_to_timed_out() -> None:
    runtime = FakeRuntime(
        steps=[
            FakeStepSpec(
                status=RunStatus.SUCCEEDED,
                duration_seconds=25.0,
                output_text="Finished too late",
            )
        ]
    )
    req = ExecutionRequest(
        task_id="task_slow",
        run_id="run_slow_1",
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        prompt="Run slow step",
        correlation_id="corr_slow",
        timeout_seconds=5.0,
    )
    res = runtime.execute(req)
    assert res.status == RunStatus.TIMED_OUT
    assert res.claimed_success is False
    assert res.error_code == "EXECUTION_TIMEOUT"
