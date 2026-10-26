from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from khamseen_os.contracts import (
    Evidence,
    EvidenceKind,
    ExecutionRequest,
    ExecutionResult,
    LifecycleStage,
    RunStatus,
    UsageMetrics,
)


@dataclass(frozen=True)
class FakeStepSpec:
    status: RunStatus = RunStatus.SUCCEEDED
    output_text: str = "Synthetic execution completed"
    claimed_success: bool = True
    duration_seconds: float = 0.25
    usage: UsageMetrics = field(
        default_factory=lambda: UsageMetrics(
            input_tokens=120,
            output_tokens=80,
            total_tokens=200,
            estimated_cost_usd=0.002,
            api_calls=1,
            verified=True,
            cost_source="fake_ledger",
        )
    )
    evidence_specs: tuple[dict[str, Any], ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    external_session_id: str | None = None


class FakeRuntime:
    """Deterministic in-memory RuntimeProvider for offline tests and examples."""

    def __init__(
        self,
        steps: list[FakeStepSpec] | None = None,
        stage_handlers: dict[tuple[LifecycleStage, int], FakeStepSpec] | None = None,
        custom_handler: Callable[[ExecutionRequest], ExecutionResult] | None = None,
        healthy: bool = True,
    ) -> None:
        self._steps: list[FakeStepSpec] = list(steps or [])
        self._stage_handlers: dict[tuple[LifecycleStage, int], FakeStepSpec] = dict(
            stage_handlers or {}
        )
        self._custom_handler = custom_handler
        self._healthy = healthy
        self.executed_requests: list[ExecutionRequest] = []
        self.cancelled_run_ids: set[str] = set()

    @property
    def provider_name(self) -> str:
        return "fake"

    def healthcheck(self) -> bool:
        return self._healthy

    def cancel(self, run_id: str) -> bool:
        self.cancelled_run_ids.add(run_id)
        return True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.executed_requests.append(request)

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
                error_message=f"Run {request.run_id} was cancelled before completion",
            )

        if not self._healthy:
            return ExecutionResult(
                run_id=request.run_id,
                task_id=request.task_id,
                correlation_id=request.correlation_id,
                status=RunStatus.FAILED,
                output_text="",
                claimed_success=False,
                duration_seconds=0.0,
                error_code="PROVIDER_UNHEALTHY",
                error_message="FakeRuntime is marked unhealthy",
            )

        if self._custom_handler is not None:
            return self._custom_handler(request)

        spec = self._resolve_spec(request)

        if spec.duration_seconds > request.timeout_seconds or spec.status == RunStatus.TIMED_OUT:
            return ExecutionResult(
                run_id=request.run_id,
                task_id=request.task_id,
                correlation_id=request.correlation_id,
                status=RunStatus.TIMED_OUT,
                output_text=spec.output_text,
                claimed_success=False,
                duration_seconds=spec.duration_seconds,
                usage=spec.usage,
                error_code=spec.error_code or "EXECUTION_TIMEOUT",
                error_message=spec.error_message
                or f"Execution exceeded timeout of {request.timeout_seconds}s",
                external_session_id=spec.external_session_id or f"fake_sess_{request.run_id}",
            )

        built_evidence = tuple(
            Evidence(
                task_id=request.task_id,
                run_id=request.run_id,
                kind=EvidenceKind(ev_spec["kind"])
                if isinstance(ev_spec["kind"], str)
                else ev_spec["kind"],
                producer_id=str(ev_spec.get("producer_id", request.agent_id)),
                producer_role=str(ev_spec.get("producer_role", request.agent_role)),
                passed=bool(ev_spec.get("passed", True)),
                verified=bool(ev_spec.get("verified", True)),
                summary=str(ev_spec.get("summary", "Evidence artifact recorded")),
                details=dict(ev_spec.get("details", {})),
            )
            for ev_spec in spec.evidence_specs
        )

        return ExecutionResult(
            run_id=request.run_id,
            task_id=request.task_id,
            correlation_id=request.correlation_id,
            status=spec.status,
            output_text=spec.output_text,
            claimed_success=spec.claimed_success,
            duration_seconds=spec.duration_seconds,
            usage=spec.usage,
            evidence=built_evidence,
            error_code=spec.error_code,
            error_message=spec.error_message,
            external_session_id=spec.external_session_id or f"fake_sess_{request.run_id}",
            raw_metadata={"provider": self.provider_name, "stage": request.stage.value},
        )

    def _resolve_spec(self, request: ExecutionRequest) -> FakeStepSpec:
        key = (request.stage, request.attempt)
        if key in self._stage_handlers:
            return self._stage_handlers[key]
        if self._steps:
            return self._steps.pop(0)
        return FakeStepSpec()
