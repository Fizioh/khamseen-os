from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from khamseen_os.contracts import (
    ApprovalRecord,
    AuditEvent,
    Evidence,
    EvidenceKind,
    ExecutionRequest,
    ExecutionResult,
    LifecycleStage,
    PolicyDecision,
    PolicyEvaluation,
    Run,
    RunStatus,
    RuntimeProvider,
    Task,
    TaskStatus,
)
from khamseen_os.policy import (
    PolicyEngine,
    transition_run_status,
    transition_task_stage,
    transition_task_status,
)


@dataclass
class WorkflowOutcome:
    task: Task
    runs: list[Run] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    events: list[AuditEvent] = field(default_factory=list)
    approvals: list[ApprovalRecord] = field(default_factory=list)
    final_decision: PolicyEvaluation | None = None


StageVerifier = Callable[[Task, Run, ExecutionResult], tuple[Evidence, ...]]


class EngineeringWorkflowRunner:
    """Executes the bounded REQUEST -> IMPLEMENT -> CHECK -> REVIEW -> REMEDIATE -> QA -> DONE pipeline."""

    def __init__(
        self,
        runtime: RuntimeProvider,
        policy_engine: PolicyEngine | None = None,
        implementer_id: str = "agent_implementer",
        checker_id: str = "system_deterministic_checker",
        reviewer_id: str = "agent_independent_reviewer",
        qa_id: str = "system_qa_gate",
        stage_verifiers: dict[LifecycleStage, StageVerifier] | None = None,
    ) -> None:
        if implementer_id == reviewer_id:
            raise ValueError("Implementer and independent reviewer must have distinct agent IDs")
        self.runtime = runtime
        self.policy_engine = policy_engine or PolicyEngine()
        self.implementer_id = implementer_id
        self.checker_id = checker_id
        self.reviewer_id = reviewer_id
        self.qa_id = qa_id
        self.stage_verifiers: dict[LifecycleStage, StageVerifier] = dict(stage_verifiers or {})
        self._processed_event_keys: set[str] = set()

    def run_workflow(
        self,
        task: Task,
        approvals: tuple[ApprovalRecord, ...] = (),
        requested_tools: tuple[str, ...] = (),
        requested_scopes: tuple[str, ...] = (),
        emit_default_stage_evidence: bool | None = None,
    ) -> WorkflowOutcome:
        ignore_runtime_stage_evidence = emit_default_stage_evidence is False
        emit_illustrative = emit_default_stage_evidence is True
        outcome = WorkflowOutcome(task=task, approvals=list(approvals))
        self._emit_event(
            outcome=outcome,
            event_type="task.requested",
            stage=task.stage,
            actor_id="coordinator",
            payload={"title": task.title, "external_ref": task.external_ref},
            dedup_key=f"{task.task_id}:task.requested",
        )

        transition_task_status(task, TaskStatus.IN_PROGRESS)
        attempt = 0

        while attempt < task.budget.max_attempts:
            attempt += 1
            if task.stage == LifecycleStage.REQUEST:
                transition_task_stage(task, LifecycleStage.IMPLEMENT)
            elif task.stage == LifecycleStage.REMEDIATE:
                transition_task_stage(task, LifecycleStage.IMPLEMENT)
                transition_task_status(task, TaskStatus.IN_PROGRESS)

            impl_run = Run(
                task_id=task.task_id,
                attempt=attempt,
                agent_id=self.implementer_id,
                agent_role="implementer",
                stage=LifecycleStage.IMPLEMENT,
                correlation_id=task.correlation_id,
                prompt=f"Implement task {task.task_id}: {task.title}",
                requested_tools=requested_tools,
                requested_scopes=requested_scopes,
            )

            pre_eval = self.policy_engine.evaluate_pre_run(
                task=task,
                candidate_run=impl_run,
                prior_runs=tuple(outcome.runs),
                approvals=tuple(outcome.approvals),
                require_pre_run_approval=True,
            )
            if pre_eval.decision == PolicyDecision.HUMAN_REQUIRED:
                transition_run_status(impl_run, RunStatus.REJECTED)
                outcome.runs.append(impl_run)
                outcome.final_decision = pre_eval
                transition_task_stage(task, LifecycleStage.HUMAN_APPROVAL)
                transition_task_status(task, TaskStatus.WAITING_APPROVAL)
                self._emit_event(
                    outcome=outcome,
                    event_type="task.human_approval_required",
                    stage=task.stage,
                    actor_id="policy_engine",
                    run_id=impl_run.run_id,
                    payload={
                        "reason": pre_eval.reason,
                        "requires_approval_for": list(pre_eval.requires_approval_for),
                    },
                    dedup_key=f"{task.task_id}:{impl_run.run_id}:pre_run_approval_required",
                )
                return outcome

            if pre_eval.decision != PolicyDecision.ALLOW:
                transition_run_status(impl_run, RunStatus.REJECTED)
                outcome.runs.append(impl_run)
                outcome.final_decision = pre_eval
                self._fail_or_escalate(outcome, impl_run.run_id, pre_eval)
                return outcome

            impl_result = self._execute_stage_run(
                outcome=outcome,
                task=task,
                run=impl_run,
                emit_default_evidence=emit_illustrative,
                default_evidence_kind=EvidenceKind.IMPLEMENTATION_ARTIFACT,
                ignore_runtime_stage_evidence=ignore_runtime_stage_evidence,
            )

            post_eval = self.policy_engine.evaluate_post_run(
                task=task,
                run=impl_run,
                result=impl_result,
                prior_runs=tuple(outcome.runs[:-1]),
            )
            if post_eval.decision != PolicyDecision.ALLOW:
                outcome.final_decision = post_eval
                if not self._try_enter_remediation(outcome, impl_run.run_id, post_eval.reason):
                    return outcome
                continue

            transition_task_stage(task, LifecycleStage.CHECK)
            check_ok, check_reason = self._run_verification_stage(
                outcome=outcome,
                task=task,
                attempt=attempt,
                stage=LifecycleStage.CHECK,
                actor_id=self.checker_id,
                actor_role="checker",
                evidence_kind=EvidenceKind.DETERMINISTIC_CHECK,
                emit_default_evidence=emit_illustrative,
                ignore_runtime_stage_evidence=ignore_runtime_stage_evidence,
            )
            if not check_ok:
                if not self._try_enter_remediation(outcome, impl_run.run_id, check_reason):
                    return outcome
                continue

            transition_task_stage(task, LifecycleStage.REVIEW)
            review_ok, review_reason = self._run_verification_stage(
                outcome=outcome,
                task=task,
                attempt=attempt,
                stage=LifecycleStage.REVIEW,
                actor_id=self.reviewer_id,
                actor_role="reviewer",
                evidence_kind=EvidenceKind.INDEPENDENT_REVIEW,
                emit_default_evidence=emit_illustrative,
                ignore_runtime_stage_evidence=ignore_runtime_stage_evidence,
            )
            if not review_ok:
                if not self._try_enter_remediation(outcome, impl_run.run_id, review_reason):
                    return outcome
                continue

            transition_task_stage(task, LifecycleStage.QA)
            qa_ok, qa_reason = self._run_verification_stage(
                outcome=outcome,
                task=task,
                attempt=attempt,
                stage=LifecycleStage.QA,
                actor_id=self.qa_id,
                actor_role="qa",
                evidence_kind=EvidenceKind.QA_VERIFICATION,
                emit_default_evidence=emit_illustrative,
                ignore_runtime_stage_evidence=ignore_runtime_stage_evidence,
            )
            if not qa_ok:
                if not self._try_enter_remediation(outcome, impl_run.run_id, qa_reason):
                    return outcome
                continue

            attempt_evidence = self._evidence_for_attempt(outcome, attempt)
            gate_eval = self.policy_engine.evaluate_completion_gate(
                task=task,
                implementer_run=impl_run,
                evidence_records=attempt_evidence,
                approvals=tuple(outcome.approvals),
            )
            outcome.final_decision = gate_eval

            if gate_eval.decision == PolicyDecision.HUMAN_REQUIRED:
                transition_task_stage(task, LifecycleStage.HUMAN_APPROVAL)
                transition_task_status(task, TaskStatus.WAITING_APPROVAL)
                self._emit_event(
                    outcome=outcome,
                    event_type="task.human_approval_required",
                    stage=task.stage,
                    actor_id="policy_engine",
                    run_id=impl_run.run_id,
                    payload={
                        "reason": gate_eval.reason,
                        "requires_approval_for": list(gate_eval.requires_approval_for),
                    },
                    dedup_key=f"{task.task_id}:{impl_run.run_id}:human_approval_required",
                )
                return outcome

            if gate_eval.decision == PolicyDecision.DENY:
                transition_task_stage(task, LifecycleStage.FAILED)
                transition_task_status(task, TaskStatus.FAILED)
                self._emit_event(
                    outcome=outcome,
                    event_type="task.failed_closed",
                    stage=task.stage,
                    actor_id="policy_engine",
                    run_id=impl_run.run_id,
                    payload={
                        "reason": gate_eval.reason,
                        "violated_rules": list(gate_eval.violated_rules),
                    },
                    dedup_key=f"{task.task_id}:{impl_run.run_id}:failed_closed",
                )
                return outcome

            if task.requires_human_approval or task.sensitive_actions:
                transition_task_stage(task, LifecycleStage.HUMAN_APPROVAL)
                self._emit_event(
                    outcome=outcome,
                    event_type="task.human_approval_verified",
                    stage=task.stage,
                    actor_id=outcome.approvals[-1].approver_id,
                    run_id=impl_run.run_id,
                    payload={"approval_id": outcome.approvals[-1].approval_id},
                    dedup_key=f"{task.task_id}:{impl_run.run_id}:human_approval_verified",
                )

            transition_task_stage(task, LifecycleStage.DONE)
            transition_task_status(task, TaskStatus.COMPLETED)
            self._emit_event(
                outcome=outcome,
                event_type="task.completed",
                stage=task.stage,
                actor_id="coordinator",
                run_id=impl_run.run_id,
                payload={"attempts": attempt, "total_runs": len(outcome.runs)},
                dedup_key=f"{task.task_id}:completed",
            )
            return outcome

        outcome.final_decision = PolicyEvaluation(
            decision=PolicyDecision.DENY,
            reason=f"Maximum attempts ({task.budget.max_attempts}) exhausted without passing verification",
            violated_rules=("max_attempts_exceeded",),
        )
        if task.stage not in (LifecycleStage.FAILED, LifecycleStage.ESCALATED):
            transition_task_stage(task, LifecycleStage.ESCALATED)
        if task.status not in (TaskStatus.FAILED, TaskStatus.ESCALATED):
            transition_task_status(task, TaskStatus.ESCALATED)
        self._emit_event(
            outcome=outcome,
            event_type="task.escalated",
            stage=task.stage,
            actor_id="policy_engine",
            payload={"reason": outcome.final_decision.reason},
            dedup_key=f"{task.task_id}:escalated",
        )
        return outcome

    def record_external_event(
        self,
        outcome: WorkflowOutcome,
        dedup_key: str,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> bool:
        if dedup_key in self._processed_event_keys:
            return False
        self._emit_event(
            outcome=outcome,
            event_type=event_type,
            stage=outcome.task.stage,
            actor_id=actor_id,
            run_id=run_id,
            payload=payload or {},
            dedup_key=dedup_key,
        )
        return True

    def _execute_stage_run(
        self,
        outcome: WorkflowOutcome,
        task: Task,
        run: Run,
        emit_default_evidence: bool,
        default_evidence_kind: EvidenceKind,
        ignore_runtime_stage_evidence: bool = False,
    ) -> ExecutionResult:
        transition_run_status(run, RunStatus.RUNNING)
        request = ExecutionRequest(
            task_id=task.task_id,
            run_id=run.run_id,
            attempt=run.attempt,
            agent_id=run.agent_id,
            agent_role=run.agent_role,
            stage=run.stage,
            prompt=run.prompt,
            correlation_id=run.correlation_id,
            timeout_seconds=task.budget.timeout_seconds,
            allowed_tools=task.allowed_tools,
            allowed_scopes=task.allowed_scopes,
            sensitive_actions=task.sensitive_actions,
        )
        result = self.runtime.execute(request)
        if result.status != run.status:
            transition_run_status(run, result.status)
        run.duration_seconds = result.duration_seconds
        run.usage = result.usage
        run.error_code = result.error_code
        run.error_message = result.error_message
        run.claimed_success = result.claimed_success
        run.external_run_id = result.external_session_id
        outcome.runs.append(run)

        if result.evidence and not ignore_runtime_stage_evidence:
            outcome.evidence.extend(result.evidence)
        elif result.evidence and ignore_runtime_stage_evidence:
            outcome.evidence.extend(
                ev for ev in result.evidence if ev.kind == EvidenceKind.USAGE_REPORT
            )
        if run.stage in self.stage_verifiers and not ignore_runtime_stage_evidence:
            outcome.evidence.extend(self.stage_verifiers[run.stage](task, run, result))
        has_stage_evidence = any(
            ev.run_id == run.run_id and ev.kind == default_evidence_kind for ev in outcome.evidence
        )
        if emit_default_evidence and result.status == RunStatus.SUCCEEDED and not has_stage_evidence:
            outcome.evidence.append(
                Evidence(
                    task_id=task.task_id,
                    run_id=run.run_id,
                    kind=default_evidence_kind,
                    producer_id=run.agent_id,
                    producer_role=run.agent_role,
                    passed=True,
                    verified=False,
                    summary=result.output_text or f"{run.stage.value} illustrative stage output",
                    details={"attempt": run.attempt, "stage": run.stage.value, "illustrative": True},
                )
            )

        self._emit_event(
            outcome=outcome,
            event_type=f"run.{run.stage.value.lower()}.{run.status.value.lower()}",
            stage=run.stage,
            actor_id=run.agent_id,
            run_id=run.run_id,
            payload={
                "attempt": run.attempt,
                "status": run.status.value,
                "external_run_id": run.external_run_id,
            },
            dedup_key=f"{run.run_id}:completed",
        )
        return result

    def _run_verification_stage(
        self,
        outcome: WorkflowOutcome,
        task: Task,
        attempt: int,
        stage: LifecycleStage,
        actor_id: str,
        actor_role: str,
        evidence_kind: EvidenceKind,
        emit_default_evidence: bool,
        ignore_runtime_stage_evidence: bool = False,
    ) -> tuple[bool, str]:
        stage_run = Run(
            task_id=task.task_id,
            attempt=attempt,
            agent_id=actor_id,
            agent_role=actor_role,
            stage=stage,
            correlation_id=task.correlation_id,
            prompt=f"Verify {stage.value} for task {task.task_id} (attempt {attempt})",
        )
        result = self._execute_stage_run(
            outcome=outcome,
            task=task,
            run=stage_run,
            emit_default_evidence=emit_default_evidence,
            default_evidence_kind=evidence_kind,
            ignore_runtime_stage_evidence=ignore_runtime_stage_evidence,
        )
        if result.status != RunStatus.SUCCEEDED:
            return False, result.error_message or f"{stage.value} execution failed"

        stage_evidence = [
            ev
            for ev in outcome.evidence
            if ev.run_id == stage_run.run_id and ev.kind == evidence_kind
        ]
        if not stage_evidence:
            return True, f"{stage.value} completed without verified evidence (pending completion gate)"
        if not all(ev.passed for ev in stage_evidence):
            failed_summaries = [ev.summary for ev in stage_evidence if not ev.passed]
            return (
                False,
                "; ".join(failed_summaries) or f"{stage.value} findings rejected attempt",
            )
        if not all(ev.verify_integrity() for ev in stage_evidence):
            return True, f"{stage.value} produced unverified evidence (pending completion gate)"

        return True, f"{stage.value} passed"

    def _try_enter_remediation(
        self,
        outcome: WorkflowOutcome,
        failed_run_id: str,
        reason: str,
    ) -> bool:
        task = outcome.task
        implementer_runs = [r for r in outcome.runs if r.stage == LifecycleStage.IMPLEMENT]
        next_attempt = len(implementer_runs) + 1
        probe_run = Run(
            task_id=task.task_id,
            attempt=next_attempt,
            agent_id=self.implementer_id,
            agent_role="implementer",
            stage=LifecycleStage.IMPLEMENT,
            correlation_id=task.correlation_id,
        )
        next_eval = self.policy_engine.evaluate_pre_run(
            task=task,
            candidate_run=probe_run,
            prior_runs=tuple(outcome.runs),
            approvals=tuple(outcome.approvals),
        )
        if next_eval.decision != PolicyDecision.ALLOW:
            outcome.final_decision = next_eval
            self._fail_or_escalate(outcome, failed_run_id, next_eval)
            return False

        transition_task_stage(task, LifecycleStage.REMEDIATE)
        transition_task_status(task, TaskStatus.REMEDIATING)
        self._emit_event(
            outcome=outcome,
            event_type="task.remediate",
            stage=task.stage,
            actor_id="coordinator",
            run_id=failed_run_id,
            payload={"reason": reason, "next_attempt": next_attempt},
            dedup_key=f"{task.task_id}:remediate:{len(outcome.runs)}",
        )
        return True

    def _fail_or_escalate(
        self,
        outcome: WorkflowOutcome,
        run_id: str | None,
        evaluation: PolicyEvaluation,
    ) -> None:
        task = outcome.task
        escalate_rules = {
            "max_attempts_exceeded",
            "repeated_identical_failure_limit_reached",
            "token_budget_exceeded",
            "cost_budget_exceeded",
        }
        should_escalate = bool(set(evaluation.violated_rules) & escalate_rules)
        target_stage = LifecycleStage.ESCALATED if should_escalate else LifecycleStage.FAILED
        target_status = TaskStatus.ESCALATED if should_escalate else TaskStatus.FAILED
        if task.stage != target_stage:
            transition_task_stage(task, target_stage)
        if task.status != target_status:
            transition_task_status(task, target_status)
        self._emit_event(
            outcome=outcome,
            event_type=f"task.{target_stage.value.lower()}",
            stage=task.stage,
            actor_id="policy_engine",
            run_id=run_id,
            payload={
                "reason": evaluation.reason,
                "violated_rules": list(evaluation.violated_rules),
            },
            dedup_key=f"{task.task_id}:{target_stage.value}:{len(outcome.events)}",
        )

    @staticmethod
    def _evidence_for_attempt(outcome: WorkflowOutcome, attempt: int) -> tuple[Evidence, ...]:
        attempt_run_ids = {r.run_id for r in outcome.runs if r.attempt == attempt}
        return tuple(ev for ev in outcome.evidence if ev.run_id in attempt_run_ids)

    def _emit_event(
        self,
        outcome: WorkflowOutcome,
        event_type: str,
        stage: LifecycleStage,
        actor_id: str,
        payload: dict[str, Any],
        dedup_key: str,
        run_id: str | None = None,
    ) -> None:
        if dedup_key in self._processed_event_keys:
            return
        self._processed_event_keys.add(dedup_key)
        outcome.events.append(
            AuditEvent(
                task_id=outcome.task.task_id,
                run_id=run_id,
                correlation_id=outcome.task.correlation_id,
                event_type=event_type,
                stage=stage,
                actor_id=actor_id,
                payload=payload,
            )
        )
