from __future__ import annotations

import json

import pytest

from khamseen_os import (
    ApprovalRecord,
    ApprovalStatus,
    AuditEvent,
    BudgetSpec,
    EngineeringWorkflowRunner,
    Evidence,
    EvidenceKind,
    ExecutionResult,
    FakeRuntime,
    FakeStepSpec,
    LifecycleStage,
    PolicyDecision,
    PolicyEngine,
    Run,
    RunStatus,
    Task,
    TaskStatus,
    UnsafeStateTransitionError,
    UsageMetrics,
    serialize_events_jsonl,
    transition_run_status,
    transition_task_stage,
    transition_task_status,
)


def test_unsafe_state_transitions_rejected() -> None:
    task = Task(title="Test transitions", description="Ensure invalid jumps fail")
    with pytest.raises(UnsafeStateTransitionError):
        transition_task_stage(task, LifecycleStage.DONE)

    with pytest.raises(UnsafeStateTransitionError):
        transition_task_status(task, TaskStatus.COMPLETED)

    run = Run(
        task_id=task.task_id,
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
    )
    with pytest.raises(UnsafeStateTransitionError):
        transition_run_status(run, RunStatus.SUCCEEDED)


def test_agent_claim_alone_does_not_complete_task() -> None:
    task = Task(title="Verify claim vs evidence", description="Agent claim is not enough")
    run = Run(
        task_id=task.task_id,
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        status=RunStatus.SUCCEEDED,
        claimed_success=True,
    )
    engine = PolicyEngine()
    decision = engine.evaluate_completion_gate(
        task=task,
        implementer_run=run,
        evidence_records=(),
    )
    assert decision.decision == PolicyDecision.DENY
    assert "missing_mandatory_evidence:DETERMINISTIC_CHECK" in decision.violated_rules
    assert "missing_mandatory_evidence:INDEPENDENT_REVIEW" in decision.violated_rules


def test_implementer_cannot_self_review() -> None:
    task = Task(
        title="Self review check",
        description="Reviewer must be distinct from implementer",
        required_evidence=(EvidenceKind.DETERMINISTIC_CHECK, EvidenceKind.INDEPENDENT_REVIEW),
    )
    run = Run(
        task_id=task.task_id,
        attempt=1,
        agent_id="agent_alpha",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        status=RunStatus.SUCCEEDED,
    )
    check_ev = Evidence(
        task_id=task.task_id,
        run_id=run.run_id,
        kind=EvidenceKind.DETERMINISTIC_CHECK,
        producer_id="checker_1",
        producer_role="checker",
        passed=True,
        summary="Tests passed",
    )
    self_review_ev = Evidence(
        task_id=task.task_id,
        run_id=run.run_id,
        kind=EvidenceKind.INDEPENDENT_REVIEW,
        producer_id="agent_alpha",
        producer_role="reviewer",
        passed=True,
        summary="Self-approved",
    )
    engine = PolicyEngine()
    decision = engine.evaluate_completion_gate(
        task=task,
        implementer_run=run,
        evidence_records=(check_ev, self_review_ev),
    )
    assert decision.decision == PolicyDecision.DENY
    assert "implementer_reviewer_separation_violation" in decision.violated_rules


def test_forged_evidence_hash_fails_closed() -> None:
    task = Task(
        title="Integrity check",
        description="Tampered evidence must fail closed",
        required_evidence=(EvidenceKind.DETERMINISTIC_CHECK,),
    )
    run = Run(
        task_id=task.task_id,
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
    )
    forged = Evidence(
        task_id=task.task_id,
        run_id=run.run_id,
        kind=EvidenceKind.DETERMINISTIC_CHECK,
        producer_id="checker_1",
        producer_role="checker",
        passed=True,
        summary="Tampered summary",
        content_hash="0" * 64,
    )
    assert not forged.verify_integrity()
    decision = PolicyEngine().evaluate_completion_gate(
        task=task,
        implementer_run=run,
        evidence_records=(forged,),
    )
    assert decision.decision == PolicyDecision.DENY
    assert "forged_or_unverified_evidence:DETERMINISTIC_CHECK" in decision.violated_rules


def test_budget_guards_and_unverified_usage_rejection() -> None:
    task = Task(
        title="Budgeted task",
        description="Enforce verified token and cost caps",
        budget=BudgetSpec(max_attempts=3, max_total_tokens=500, max_cost_usd=0.05),
    )
    prior_run = Run(
        task_id=task.task_id,
        attempt=1,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
        status=RunStatus.SUCCEEDED,
        usage=UsageMetrics(total_tokens=450, estimated_cost_usd=0.04, verified=True),
    )
    next_run = Run(
        task_id=task.task_id,
        attempt=2,
        agent_id="agent_impl",
        agent_role="implementer",
        stage=LifecycleStage.IMPLEMENT,
    )
    over_budget_result = ExecutionResult(
        run_id=next_run.run_id,
        task_id=task.task_id,
        correlation_id=task.correlation_id,
        status=RunStatus.SUCCEEDED,
        usage=UsageMetrics(total_tokens=200, estimated_cost_usd=0.02, verified=True),
    )
    engine = PolicyEngine()
    post_eval = engine.evaluate_post_run(
        task=task,
        run=next_run,
        result=over_budget_result,
        prior_runs=(prior_run,),
    )
    assert post_eval.decision == PolicyDecision.DENY
    assert "token_budget_exceeded" in post_eval.violated_rules
    assert "cost_budget_exceeded" in post_eval.violated_rules

    unverified_result = ExecutionResult(
        run_id=next_run.run_id,
        task_id=task.task_id,
        correlation_id=task.correlation_id,
        status=RunStatus.SUCCEEDED,
        usage=UsageMetrics(total_tokens=10, estimated_cost_usd=0.001, verified=False),
    )
    unverified_eval = engine.evaluate_post_run(
        task=task,
        run=next_run,
        result=unverified_result,
        prior_runs=(),
    )
    assert unverified_eval.decision == PolicyDecision.DENY
    assert "unverified_token_usage_data" in unverified_eval.violated_rules


def test_repeated_identical_failures_escalate_early() -> None:
    runtime = FakeRuntime(
        stage_handlers={
            (LifecycleStage.IMPLEMENT, 1): FakeStepSpec(
                status=RunStatus.FAILED,
                claimed_success=False,
                error_code="SYNTAX_ERR",
                error_message="Unexpected token on line 42",
            ),
            (LifecycleStage.IMPLEMENT, 2): FakeStepSpec(
                status=RunStatus.FAILED,
                claimed_success=False,
                error_code="SYNTAX_ERR",
                error_message="Unexpected token on line 42",
            ),
        }
    )
    task = Task(
        title="Identical failure loop",
        description="Should stop after 2 identical failures even when max_attempts is 4",
        budget=BudgetSpec(max_attempts=4, max_identical_failures=2),
    )
    runner = EngineeringWorkflowRunner(runtime=runtime)
    outcome = runner.run_workflow(task)
    assert outcome.task.stage == LifecycleStage.ESCALATED
    assert outcome.task.status == TaskStatus.ESCALATED
    assert len(outcome.runs) == 2
    assert outcome.final_decision is not None
    assert "repeated_identical_failure_limit_reached" in outcome.final_decision.violated_rules


def test_human_approval_gate_pauses_and_completes_when_approved() -> None:
    runtime = FakeRuntime()
    task_pending = Task(
        title="Production schema migration",
        description="Requires explicit human approval",
        sensitive_actions=("db.schema.migrate",),
        requires_human_approval=True,
    )
    runner = EngineeringWorkflowRunner(runtime=runtime)
    outcome_pending = runner.run_workflow(task_pending)
    assert outcome_pending.task.stage == LifecycleStage.HUMAN_APPROVAL
    assert outcome_pending.task.status == TaskStatus.WAITING_APPROVAL
    assert outcome_pending.final_decision is not None
    assert outcome_pending.final_decision.decision == PolicyDecision.HUMAN_REQUIRED

    task_approved = Task(
        title="Production schema migration",
        description="Requires explicit human approval",
        sensitive_actions=("db.schema.migrate",),
        requires_human_approval=True,
    )
    approval = ApprovalRecord(
        task_id=task_approved.task_id,
        approver_id="human_release_manager",
        status=ApprovalStatus.APPROVED,
        reason="Reviewed migration plan and rollback script",
        approved_actions=("db.schema.migrate",),
    )
    outcome_approved = runner.run_workflow(task_approved, approvals=(approval,))
    assert outcome_approved.task.stage == LifecycleStage.DONE
    assert outcome_approved.task.status == TaskStatus.COMPLETED
    assert outcome_approved.final_decision is not None
    assert outcome_approved.final_decision.decision == PolicyDecision.ALLOW


@pytest.mark.parametrize("container", [list, tuple])
def test_serialize_events_jsonl_preserves_events_and_redaction(container: type) -> None:
    events = container(
        [
            AuditEvent(
                task_id="task_export",
                correlation_id="corr_export",
                event_type="stage_changed",
                stage=LifecycleStage.IMPLEMENT,
                actor_id="worker",
                run_id="run_export",
                payload={
                    "token": "sensitive-value",
                    "nested": {"password": "another-value"},
                    "message": "first line\nsecond line",
                    "count": 2,
                },
                event_id="evt_first",
                created_at="2026-11-25T00:00:00+00:00",
            ),
            AuditEvent(
                task_id="task_export",
                correlation_id="corr_export",
                event_type="checked",
                stage=LifecycleStage.CHECK,
                actor_id="checker",
                event_id="evt_second",
                created_at="2026-11-25T00:00:01+00:00",
            ),
        ]
    )
    output = serialize_events_jsonl(events)
    lines = output.splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]
    assert [record["event_id"] for record in records] == ["evt_first", "evt_second"]
    assert records[0] == {
        "task_id": "task_export",
        "correlation_id": "corr_export",
        "event_type": "stage_changed",
        "stage": "IMPLEMENT",
        "actor_id": "worker",
        "run_id": "run_export",
        "event_id": "evt_first",
        "created_at": "2026-11-25T00:00:00+00:00",
        "payload": {
            "token": "[REDACTED]",
            "nested": {"password": "[REDACTED]"},
            "message": "first line\nsecond line",
            "count": 2,
        },
    }
    assert records[1]["run_id"] is None
    assert records[1]["payload"] == {}
    assert all(line == json.dumps(record, sort_keys=True) for line, record in zip(lines, records, strict=True))
    assert "sensitive-value" not in output
    assert "another-value" not in output
    assert events[0].payload["token"] == "[REDACTED]"


def test_serialize_events_jsonl_empty() -> None:
    assert serialize_events_jsonl([]) == ""
