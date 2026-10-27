from __future__ import annotations

from collections import Counter

from khamseen_os.contracts import (
    ApprovalRecord,
    ApprovalStatus,
    Evidence,
    EvidenceKind,
    ExecutionResult,
    LifecycleStage,
    PolicyDecision,
    PolicyEvaluation,
    Run,
    RunStatus,
    Task,
    TaskStatus,
)


class UnsafeStateTransitionError(ValueError):
    """Raised when a Task or Run attempts an invalid state transition."""


ALLOWED_STAGE_TRANSITIONS: dict[LifecycleStage, frozenset[LifecycleStage]] = {
    LifecycleStage.REQUEST: frozenset(
        {
            LifecycleStage.PLAN,
            LifecycleStage.DELEGATE,
            LifecycleStage.IMPLEMENT,
            LifecycleStage.HUMAN_APPROVAL,
            LifecycleStage.FAILED,
        }
    ),
    LifecycleStage.PLAN: frozenset(
        {LifecycleStage.DELEGATE, LifecycleStage.IMPLEMENT, LifecycleStage.FAILED}
    ),
    LifecycleStage.DELEGATE: frozenset({LifecycleStage.IMPLEMENT, LifecycleStage.FAILED}),
    LifecycleStage.IMPLEMENT: frozenset(
        {
            LifecycleStage.CHECK,
            LifecycleStage.REMEDIATE,
            LifecycleStage.HUMAN_APPROVAL,
            LifecycleStage.FAILED,
            LifecycleStage.ESCALATED,
        }
    ),
    LifecycleStage.CHECK: frozenset(
        {
            LifecycleStage.REVIEW,
            LifecycleStage.REMEDIATE,
            LifecycleStage.FAILED,
            LifecycleStage.ESCALATED,
        }
    ),
    LifecycleStage.REVIEW: frozenset(
        {
            LifecycleStage.QA,
            LifecycleStage.REMEDIATE,
            LifecycleStage.FAILED,
            LifecycleStage.ESCALATED,
        }
    ),
    LifecycleStage.REMEDIATE: frozenset(
        {
            LifecycleStage.IMPLEMENT,
            LifecycleStage.CHECK,
            LifecycleStage.FAILED,
            LifecycleStage.ESCALATED,
        }
    ),
    LifecycleStage.QA: frozenset(
        {
            LifecycleStage.HUMAN_APPROVAL,
            LifecycleStage.DONE,
            LifecycleStage.REMEDIATE,
            LifecycleStage.FAILED,
            LifecycleStage.ESCALATED,
        }
    ),
    LifecycleStage.HUMAN_APPROVAL: frozenset(
        {
            LifecycleStage.IMPLEMENT,
            LifecycleStage.DONE,
            LifecycleStage.FAILED,
            LifecycleStage.ESCALATED,
        }
    ),
    LifecycleStage.DONE: frozenset(),
    LifecycleStage.FAILED: frozenset(),
    LifecycleStage.ESCALATED: frozenset(),
}

ALLOWED_TASK_STATUS_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {
            TaskStatus.IN_PROGRESS,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.IN_PROGRESS: frozenset(
        {
            TaskStatus.REMEDIATING,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.ESCALATED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.REMEDIATING: frozenset(
        {
            TaskStatus.IN_PROGRESS,
            TaskStatus.WAITING_APPROVAL,
            TaskStatus.FAILED,
            TaskStatus.ESCALATED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_APPROVAL: frozenset(
        {
            TaskStatus.IN_PROGRESS,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.ESCALATED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.ESCALATED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

ALLOWED_RUN_STATUS_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.REJECTED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.TIMED_OUT,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.TIMED_OUT: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.REJECTED: frozenset(),
}


def transition_task_stage(task: Task, target: LifecycleStage) -> None:
    allowed = ALLOWED_STAGE_TRANSITIONS.get(task.stage, frozenset())
    if target not in allowed:
        raise UnsafeStateTransitionError(
            f"Unsafe task stage transition from {task.stage.value} to {target.value}"
        )
    task.stage = target


def transition_task_status(task: Task, target: TaskStatus) -> None:
    allowed = ALLOWED_TASK_STATUS_TRANSITIONS.get(task.status, frozenset())
    if target not in allowed:
        raise UnsafeStateTransitionError(
            f"Unsafe task status transition from {task.status.value} to {target.value}"
        )
    task.status = target


def transition_run_status(run: Run, target: RunStatus) -> None:
    allowed = ALLOWED_RUN_STATUS_TRANSITIONS.get(run.status, frozenset())
    if target not in allowed:
        raise UnsafeStateTransitionError(
            f"Unsafe run status transition from {run.status.value} to {target.value}"
        )
    run.status = target


class PolicyEngine:
    """Deterministic policy evaluator for bounded autonomy and verification gates."""

    def evaluate_pre_run(
        self,
        task: Task,
        candidate_run: Run,
        prior_runs: tuple[Run, ...] = (),
        approvals: tuple[ApprovalRecord, ...] = (),
        require_pre_run_approval: bool = True,
    ) -> PolicyEvaluation:
        violations: list[str] = []

        same_stage_runs = [r for r in prior_runs if r.stage == candidate_run.stage]
        if (
            candidate_run.attempt > task.budget.max_attempts
            or len(same_stage_runs) >= task.budget.max_attempts
        ):
            violations.append("max_attempts_exceeded")

        failure_signatures = [
            f"{r.error_code or 'ERR'}:{r.error_message or ''}"
            for r in prior_runs
            if r.status in (RunStatus.FAILED, RunStatus.TIMED_OUT)
            and (r.error_code or r.error_message)
        ]
        if failure_signatures:
            counts = Counter(failure_signatures)
            most_common_count = counts.most_common(1)[0][1]
            if most_common_count >= task.budget.max_identical_failures:
                violations.append("repeated_identical_failure_limit_reached")

        if task.allowed_tools and candidate_run.requested_tools:
            disallowed_tools = [
                tool for tool in candidate_run.requested_tools if tool not in task.allowed_tools
            ]
            if disallowed_tools:
                violations.append(f"unauthorized_tools:{','.join(sorted(disallowed_tools))}")

        if task.allowed_scopes and candidate_run.requested_scopes:
            disallowed_scopes = [
                scope for scope in candidate_run.requested_scopes if scope not in task.allowed_scopes
            ]
            if disallowed_scopes:
                violations.append(f"cross_domain_scope_violation:{','.join(sorted(disallowed_scopes))}")

        budget_violations = self._check_cumulative_budget(task, prior_runs)
        violations.extend(budget_violations)

        if violations:
            return PolicyEvaluation(
                decision=PolicyDecision.DENY,
                reason=f"Pre-run policy rejected execution: {', '.join(violations)}",
                violated_rules=tuple(violations),
            )

        if require_pre_run_approval and (task.requires_human_approval or task.sensitive_actions):
            if any(
                a.task_id == task.task_id and not a.verify_integrity() for a in approvals
            ):
                return PolicyEvaluation(
                    decision=PolicyDecision.DENY,
                    reason="Forged or unverified human approval record rejected",
                    violated_rules=("forged_or_unverified_approval",),
                    requires_approval_for=task.sensitive_actions or ("sensitive_task",),
                )
            if any(a.status == ApprovalStatus.REJECTED for a in approvals if a.task_id == task.task_id):
                return PolicyEvaluation(
                    decision=PolicyDecision.DENY,
                    reason="Human authority explicitly rejected sensitive task execution",
                    violated_rules=("human_approval_rejected",),
                    requires_approval_for=task.sensitive_actions or ("sensitive_task",),
                )
            if not self._has_valid_human_approval(
                task=task,
                approvals=approvals,
                disallowed_actor_ids={candidate_run.agent_id},
                required_scopes=candidate_run.requested_scopes or task.allowed_scopes,
            ):
                return PolicyEvaluation(
                    decision=PolicyDecision.HUMAN_REQUIRED,
                    reason="Sensitive action requires explicit human approval before execution",
                    requires_approval_for=task.sensitive_actions or ("sensitive_task",),
                )

        return PolicyEvaluation(
            decision=PolicyDecision.ALLOW,
            reason="Pre-run policy checks passed",
        )

    def evaluate_post_run(
        self,
        task: Task,
        run: Run,
        result: ExecutionResult,
        prior_runs: tuple[Run, ...] = (),
    ) -> PolicyEvaluation:
        violations: list[str] = []

        if (
            result.status == RunStatus.TIMED_OUT
            or result.duration_seconds > task.budget.timeout_seconds
        ):
            violations.append("execution_timeout_exceeded")

        if result.status == RunStatus.CANCELLED:
            violations.append("execution_cancelled")

        if result.status == RunStatus.FAILED:
            violations.append(f"runtime_failure:{result.error_code or 'unknown'}")

        all_runs = (*prior_runs, run)
        budget_violations = self._check_cumulative_budget(task, all_runs, latest_result=result)
        violations.extend(budget_violations)

        if violations:
            return PolicyEvaluation(
                decision=PolicyDecision.DENY,
                reason=f"Post-run policy failed: {', '.join(violations)}",
                violated_rules=tuple(violations),
            )

        return PolicyEvaluation(
            decision=PolicyDecision.ALLOW,
            reason="Post-run execution constraints satisfied",
        )

    def evaluate_completion_gate(
        self,
        task: Task,
        implementer_run: Run,
        evidence_records: tuple[Evidence, ...],
        approvals: tuple[ApprovalRecord, ...] = (),
    ) -> PolicyEvaluation:
        violations: list[str] = []

        valid_evidence: list[Evidence] = []
        for ev in evidence_records:
            if ev.task_id != task.task_id:
                continue
            if not ev.verify_integrity():
                violations.append(f"forged_or_unverified_evidence:{ev.kind.value}")
                continue
            valid_evidence.append(ev)

        for required_kind in task.required_evidence:
            matching = [ev for ev in valid_evidence if ev.kind == required_kind]
            if not matching:
                violations.append(f"missing_mandatory_evidence:{required_kind.value}")
                continue
            latest_matching = matching[-1]
            if not latest_matching.passed:
                violations.append(f"failed_evidence_check:{required_kind.value}")
                continue
            if required_kind == EvidenceKind.INDEPENDENT_REVIEW:
                if (
                    latest_matching.producer_id == implementer_run.agent_id
                    or latest_matching.producer_role != "reviewer"
                ):
                    violations.append("implementer_reviewer_separation_violation")
            elif required_kind == EvidenceKind.DETERMINISTIC_CHECK:
                if (
                    latest_matching.producer_id == implementer_run.agent_id
                    or latest_matching.producer_role != "checker"
                ):
                    violations.append("invalid_checker_evidence_producer")
            elif required_kind == EvidenceKind.QA_VERIFICATION:
                if (
                    latest_matching.producer_id == implementer_run.agent_id
                    or latest_matching.producer_role != "qa"
                ):
                    violations.append("invalid_qa_evidence_producer")

        if not task.required_evidence and implementer_run.claimed_success and not valid_evidence:
            violations.append("unverified_agent_completion_claim")

        if violations:
            return PolicyEvaluation(
                decision=PolicyDecision.DENY,
                reason=f"Completion gate failed closed: {', '.join(violations)}",
                violated_rules=tuple(violations),
            )

        if task.requires_human_approval or task.sensitive_actions:
            if any(
                a.task_id == task.task_id and not a.verify_integrity() for a in approvals
            ):
                return PolicyEvaluation(
                    decision=PolicyDecision.DENY,
                    reason="Forged or unverified human approval record rejected",
                    violated_rules=("forged_or_unverified_approval",),
                    requires_approval_for=task.sensitive_actions or ("sensitive_task",),
                )
            if any(a.status == ApprovalStatus.REJECTED for a in approvals if a.task_id == task.task_id):
                return PolicyEvaluation(
                    decision=PolicyDecision.DENY,
                    reason="Human authority rejected task approval",
                    violated_rules=("human_approval_rejected",),
                    requires_approval_for=task.sensitive_actions or ("sensitive_task",),
                )
            if not self._has_valid_human_approval(
                task=task,
                approvals=approvals,
                disallowed_actor_ids={implementer_run.agent_id},
                required_scopes=implementer_run.requested_scopes or task.allowed_scopes,
            ):
                return PolicyEvaluation(
                    decision=PolicyDecision.HUMAN_REQUIRED,
                    reason="Mandatory human approval required before marking task DONE",
                    requires_approval_for=task.sensitive_actions or ("sensitive_task",),
                )

        return PolicyEvaluation(
            decision=PolicyDecision.ALLOW,
            reason="All mandatory evidence verified and policy gates satisfied",
        )

    def _check_cumulative_budget(
        self,
        task: Task,
        runs: tuple[Run, ...],
        latest_result: ExecutionResult | None = None,
    ) -> list[str]:
        violations: list[str] = []
        usages = [r.usage for r in runs]
        if latest_result is not None and (not runs or runs[-1].usage != latest_result.usage):
            usages = [r.usage for r in runs[:-1]] + [latest_result.usage]

        if task.budget.max_total_tokens is not None:
            if any(not u.verified for u in usages):
                violations.append("unverified_token_usage_data")
            else:
                total_tokens = sum(u.total_tokens for u in usages)
                if total_tokens > task.budget.max_total_tokens:
                    violations.append("token_budget_exceeded")

        if task.budget.max_cost_usd is not None:
            if any(not u.verified or u.estimated_cost_usd is None for u in usages):
                violations.append("unverified_cost_usage_data")
            else:
                total_cost = sum(u.estimated_cost_usd or 0.0 for u in usages)
                if total_cost > task.budget.max_cost_usd:
                    violations.append("cost_budget_exceeded")

        return violations

    @staticmethod
    def _has_valid_human_approval(
        task: Task,
        approvals: tuple[ApprovalRecord, ...],
        disallowed_actor_ids: set[str],
        required_scopes: tuple[str, ...] = (),
    ) -> bool:
        non_human_prefixes = ("agent_", "system_", "bot_")
        required_actions = set(task.sensitive_actions)
        scope_set = set(required_scopes)

        for approval in approvals:
            approver = approval.approver_id.strip()
            if (
                approval.task_id != task.task_id
                or approval.status != ApprovalStatus.APPROVED
                or not approval.verify_integrity()
                or not approver
                or approver in disallowed_actor_ids
                or approver.lower().startswith(non_human_prefixes)
            ):
                continue
            if required_actions:
                if not approval.approved_actions or not required_actions.issubset(
                    set(approval.approved_actions)
                ):
                    continue
            if approval.approved_scopes and scope_set:
                if not scope_set.issubset(set(approval.approved_scopes)):
                    continue
            return True
        return False
