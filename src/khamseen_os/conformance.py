from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from khamseen_os.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    BudgetSpec,
    Evidence,
    EvidenceKind,
    ExecutionRequest,
    ExecutionResult,
    LifecycleStage,
    PolicyDecision,
    Run,
    RunStatus,
    RuntimeProvider,
    Task,
    TaskStatus,
    UsageMetrics,
)
from khamseen_os.loop import EngineeringWorkflowRunner, StageVerifier
from khamseen_os.policy import PolicyEngine
from khamseen_os.runtime import FakeRuntime, FakeStepSpec


@dataclass(frozen=True)
class ConformanceCaseResult:
    case_name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class ConformanceReport:
    provider_name: str
    cases: tuple[ConformanceCaseResult, ...]

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)


class ProviderConformanceHarness:
    """Reusable conformance verifier for any RuntimeProvider implementation."""

    def __init__(
        self,
        success_provider_factory: Callable[[], RuntimeProvider],
        failure_provider_factory: Callable[[], RuntimeProvider],
        timeout_provider_factory: Callable[[], RuntimeProvider],
    ) -> None:
        self.success_provider_factory = success_provider_factory
        self.failure_provider_factory = failure_provider_factory
        self.timeout_provider_factory = timeout_provider_factory

    @classmethod
    def for_fake_runtime(cls) -> ProviderConformanceHarness:
        return cls(
            success_provider_factory=lambda: FakeRuntime(),
            failure_provider_factory=lambda: FakeRuntime(
                steps=[
                    FakeStepSpec(
                        status=RunStatus.FAILED,
                        output_text="",
                        claimed_success=False,
                        error_code="ADAPTER_EXEC_ERR",
                        error_message="Simulated runtime execution failure",
                    )
                    for _ in range(6)
                ]
            ),
            timeout_provider_factory=lambda: FakeRuntime(
                steps=[
                    FakeStepSpec(
                        status=RunStatus.TIMED_OUT,
                        output_text="Partial output before timeout",
                        claimed_success=False,
                        duration_seconds=35.0,
                        error_code="EXECUTION_TIMEOUT",
                        error_message="Execution timed out after 30s",
                    )
                ]
            ),
        )

    def run_all(self) -> ConformanceReport:
        sample_provider = self.success_provider_factory()
        cases = (
            self.check_successful_execution(),
            self.check_runtime_failure(),
            self.check_timeout_and_cancellation(),
            self.check_repeated_failures(),
            self.check_missing_evidence(),
            self.check_budget_rejection(),
            self.check_approval_required(),
            self.check_normalized_results(),
            self.check_repeated_event_delivery(),
        )
        return ConformanceReport(provider_name=sample_provider.provider_name, cases=cases)

    @staticmethod
    def _default_stage_verifiers() -> dict[LifecycleStage, StageVerifier]:
        def _make_verifier(kind: EvidenceKind) -> StageVerifier:
            def _verify(task: Task, run: Run, result: ExecutionResult) -> tuple[Evidence, ...]:
                if result.status != RunStatus.SUCCEEDED:
                    return ()
                if any(ev.kind == kind for ev in result.evidence):
                    return ()
                return (
                    Evidence(
                        task_id=task.task_id,
                        run_id=run.run_id,
                        kind=kind,
                        producer_id=run.agent_id,
                        producer_role=run.agent_role,
                        passed=True,
                        verified=True,
                        summary=f"Independent conformance verifier confirmed {run.stage.value}",
                        details={"attempt": run.attempt, "stage": run.stage.value},
                    ),
                )

            return _verify

        return {
            LifecycleStage.IMPLEMENT: _make_verifier(EvidenceKind.IMPLEMENTATION_ARTIFACT),
            LifecycleStage.CHECK: _make_verifier(EvidenceKind.DETERMINISTIC_CHECK),
            LifecycleStage.REVIEW: _make_verifier(EvidenceKind.INDEPENDENT_REVIEW),
            LifecycleStage.QA: _make_verifier(EvidenceKind.QA_VERIFICATION),
        }

    def check_successful_execution(self) -> ConformanceCaseResult:
        provider = self.success_provider_factory()
        assert isinstance(provider, RuntimeProvider)
        assert provider.healthcheck() is True
        runner = EngineeringWorkflowRunner(
            runtime=provider, stage_verifiers=self._default_stage_verifiers()
        )
        task = Task(title="Conformance success", description="Verify standard workflow passes")
        outcome = runner.run_workflow(task)
        passed = (
            outcome.task.stage == LifecycleStage.DONE
            and outcome.task.status == TaskStatus.COMPLETED
            and outcome.final_decision is not None
            and outcome.final_decision.decision == PolicyDecision.ALLOW
        )
        return ConformanceCaseResult(
            case_name="successful_execution",
            passed=passed,
            detail=f"stage={outcome.task.stage.value}, status={outcome.task.status.value}",
        )

    def check_runtime_failure(self) -> ConformanceCaseResult:
        provider = self.failure_provider_factory()
        req = ExecutionRequest(
            task_id="task_fail",
            run_id="run_fail_1",
            attempt=1,
            agent_id="agent_impl",
            agent_role="implementer",
            stage=LifecycleStage.IMPLEMENT,
            prompt="Trigger runtime failure",
            correlation_id="corr_fail_1",
        )
        res = provider.execute(req)
        passed = (
            res.status == RunStatus.FAILED
            and res.run_id == "run_fail_1"
            and res.correlation_id == "corr_fail_1"
            and bool(res.error_code or res.error_message)
        )
        return ConformanceCaseResult(
            case_name="runtime_failure",
            passed=passed,
            detail=f"status={res.status.value}, error_code={res.error_code}",
        )

    def check_timeout_and_cancellation(self) -> ConformanceCaseResult:
        timeout_provider = self.timeout_provider_factory()
        timeout_req = ExecutionRequest(
            task_id="task_timeout",
            run_id="run_timeout_1",
            attempt=1,
            agent_id="agent_impl",
            agent_role="implementer",
            stage=LifecycleStage.IMPLEMENT,
            prompt="Run long task",
            correlation_id="corr_timeout_1",
            timeout_seconds=10.0,
        )
        timeout_res = timeout_provider.execute(timeout_req)

        cancel_provider = self.success_provider_factory()
        cancelled_ok = cancel_provider.cancel("run_cancel_1")
        cancel_req = ExecutionRequest(
            task_id="task_cancel",
            run_id="run_cancel_1",
            attempt=1,
            agent_id="agent_impl",
            agent_role="implementer",
            stage=LifecycleStage.IMPLEMENT,
            prompt="Cancelled task",
            correlation_id="corr_cancel_1",
        )
        cancel_res = cancel_provider.execute(cancel_req)
        passed = (
            timeout_res.status == RunStatus.TIMED_OUT
            and cancelled_ok is True
            and cancel_res.status == RunStatus.CANCELLED
        )
        return ConformanceCaseResult(
            case_name="timeout_and_cancellation",
            passed=passed,
            detail=f"timeout={timeout_res.status.value}, cancel={cancel_res.status.value}",
        )

    def check_repeated_failures(self) -> ConformanceCaseResult:
        provider = self.failure_provider_factory()
        runner = EngineeringWorkflowRunner(runtime=provider)
        task = Task(
            title="Repeated failures",
            description="Must halt on repeated identical failures",
            budget=BudgetSpec(max_attempts=4, max_identical_failures=2),
        )
        outcome = runner.run_workflow(task)
        passed = (
            outcome.task.stage == LifecycleStage.ESCALATED
            and outcome.task.status == TaskStatus.ESCALATED
            and len(outcome.runs) == 2
            and outcome.final_decision is not None
            and "repeated_identical_failure_limit_reached" in outcome.final_decision.violated_rules
        )
        return ConformanceCaseResult(
            case_name="repeated_failures",
            passed=passed,
            detail=f"runs={len(outcome.runs)}, stage={outcome.task.stage.value}",
        )

    def check_missing_evidence(self) -> ConformanceCaseResult:
        provider = self.success_provider_factory()
        runner = EngineeringWorkflowRunner(runtime=provider)
        task = Task(
            title="Missing evidence check",
            description="Must fail closed when required evidence is omitted",
            required_evidence=(EvidenceKind.DETERMINISTIC_CHECK, EvidenceKind.INDEPENDENT_REVIEW),
        )
        outcome = runner.run_workflow(task, emit_default_stage_evidence=False)
        passed = (
            outcome.task.stage == LifecycleStage.FAILED
            and outcome.task.status == TaskStatus.FAILED
            and outcome.final_decision is not None
            and outcome.final_decision.decision == PolicyDecision.DENY
        )
        decision_val = outcome.final_decision.decision.value if outcome.final_decision else None
        return ConformanceCaseResult(
            case_name="missing_evidence",
            passed=passed,
            detail=f"stage={outcome.task.stage.value}, decision={decision_val}",
        )

    def check_budget_rejection(self) -> ConformanceCaseResult:
        provider = self.success_provider_factory()
        runner = EngineeringWorkflowRunner(runtime=provider)
        task = Task(
            title="Budget exceeded check",
            description="Reject when cumulative verified tokens exceed budget",
            budget=BudgetSpec(max_attempts=2, max_total_tokens=50, max_cost_usd=0.0005),
        )
        outcome = runner.run_workflow(task)
        passed = (
            outcome.task.stage == LifecycleStage.ESCALATED
            and outcome.task.status == TaskStatus.ESCALATED
            and outcome.final_decision is not None
            and outcome.final_decision.decision == PolicyDecision.DENY
            and (
                "token_budget_exceeded" in outcome.final_decision.violated_rules
                or "cost_budget_exceeded" in outcome.final_decision.violated_rules
            )
        )
        rules = outcome.final_decision.violated_rules if outcome.final_decision else ()
        return ConformanceCaseResult(
            case_name="budget_rejection",
            passed=passed,
            detail=f"stage={outcome.task.stage.value}, rules={rules}",
        )

    def check_approval_required(self) -> ConformanceCaseResult:
        provider = self.success_provider_factory()
        runner = EngineeringWorkflowRunner(runtime=provider)
        task = Task(
            title="Approval required check",
            description="Wait for approval when sensitive_actions are present",
            sensitive_actions=("secrets.rotate",),
            requires_human_approval=True,
        )
        waiting_outcome = runner.run_workflow(task)

        approved_task = Task(
            title="Approval granted check",
            description="Complete when valid human approval is supplied",
            sensitive_actions=("secrets.rotate",),
            requires_human_approval=True,
        )
        approval = ApprovalRecord(
            task_id=approved_task.task_id,
            approver_id="human_secops",
            status=ApprovalStatus.APPROVED,
            reason="Approved rotation window",
            approved_actions=("secrets.rotate",),
        )
        approved_outcome = EngineeringWorkflowRunner(
            runtime=self.success_provider_factory(),
            stage_verifiers=self._default_stage_verifiers(),
        ).run_workflow(
            approved_task, approvals=(approval,)
        )
        passed = (
            waiting_outcome.task.status == TaskStatus.WAITING_APPROVAL
            and waiting_outcome.final_decision is not None
            and waiting_outcome.final_decision.decision == PolicyDecision.HUMAN_REQUIRED
            and approved_outcome.task.status == TaskStatus.COMPLETED
            and approved_outcome.task.stage == LifecycleStage.DONE
        )
        return ConformanceCaseResult(
            case_name="approval_required",
            passed=passed,
            detail=f"unapproved={waiting_outcome.task.status.value}, approved={approved_outcome.task.status.value}",
        )

    def check_normalized_results(self) -> ConformanceCaseResult:
        provider = self.success_provider_factory()
        synthetic_token = "sk-" + "synthetic_test_token_123456"
        req = ExecutionRequest(
            task_id="task_norm",
            run_id="run_norm_1",
            attempt=1,
            agent_id="agent_impl",
            agent_role="implementer",
            stage=LifecycleStage.IMPLEMENT,
            prompt=f"Return normalized result with secret api_key={synthetic_token}",
            correlation_id="corr_norm_1",
        )
        res = provider.execute(req)
        passed = (
            isinstance(res, ExecutionResult)
            and res.task_id == "task_norm"
            and res.run_id == "run_norm_1"
            and res.correlation_id == "corr_norm_1"
            and isinstance(res.usage, UsageMetrics)
            and isinstance(res.status, RunStatus)
            and res.external_session_id is not None
        )
        return ConformanceCaseResult(
            case_name="normalized_execution_results",
            passed=passed,
            detail=f"status={res.status.value}, session={res.external_session_id}",
        )

    def check_repeated_event_delivery(self) -> ConformanceCaseResult:
        provider = self.success_provider_factory()
        runner = EngineeringWorkflowRunner(
            runtime=provider,
            policy_engine=PolicyEngine(),
            stage_verifiers=self._default_stage_verifiers(),
        )
        task = Task(title="Idempotent event delivery", description="No duplicate completion events")
        outcome = runner.run_workflow(task)
        events_before = len(outcome.events)

        first_custom = runner.record_external_event(
            outcome=outcome,
            dedup_key="webhook_delivery_99",
            event_type="runtime.webhook.completed",
            actor_id="external_runtime",
            payload={"delivery": 1},
        )
        second_custom = runner.record_external_event(
            outcome=outcome,
            dedup_key="webhook_delivery_99",
            event_type="runtime.webhook.completed",
            actor_id="external_runtime",
            payload={"delivery": 2},
        )
        duplicate_completed = runner.record_external_event(
            outcome=outcome,
            dedup_key=f"{task.task_id}:completed",
            event_type="task.completed",
            actor_id="coordinator",
        )
        completed_events = [e for e in outcome.events if e.event_type == "task.completed"]
        passed = (
            first_custom is True
            and second_custom is False
            and duplicate_completed is False
            and len(outcome.events) == events_before + 1
            and len(completed_events) == 1
        )
        return ConformanceCaseResult(
            case_name="repeated_event_delivery_idempotency",
            passed=passed,
            detail=f"completed_events={len(completed_events)}, total_events={len(outcome.events)}",
        )
