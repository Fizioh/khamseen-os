from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from khamseen_os import (
    ApprovalRecord,
    ApprovalStatus,
    BudgetSpec,
    EngineeringWorkflowRunner,
    EvidenceKind,
    FakeRuntime,
    FakeStepSpec,
    LifecycleStage,
    PolicyDecision,
    RunStatus,
    Task,
    TaskStatus,
    WorkflowOutcome,
)


def run_remediation_scenario() -> WorkflowOutcome:
    runtime = FakeRuntime(
        stage_handlers={
            (LifecycleStage.REVIEW, 1): FakeStepSpec(
                status=RunStatus.SUCCEEDED,
                output_text="Independent review found missing boundary check on empty input",
                evidence_specs=(
                    {
                        "kind": EvidenceKind.INDEPENDENT_REVIEW,
                        "producer_id": "agent_independent_reviewer",
                        "producer_role": "reviewer",
                        "passed": False,
                        "verified": True,
                        "summary": "Rejected: missing boundary validation on empty payload",
                        "details": {"finding_id": "REV-101", "severity": "high"},
                    },
                ),
            ),
            (LifecycleStage.REVIEW, 2): FakeStepSpec(
                status=RunStatus.SUCCEEDED,
                output_text="Independent review verified boundary check fix",
                evidence_specs=(
                    {
                        "kind": EvidenceKind.INDEPENDENT_REVIEW,
                        "producer_id": "agent_independent_reviewer",
                        "producer_role": "reviewer",
                        "passed": True,
                        "verified": True,
                        "summary": "Approved: boundary validation and regression test added",
                        "details": {"finding_id": "REV-101", "resolved": True},
                    },
                ),
            ),
        }
    )
    task = Task(
        title="Add input payload validator",
        description="Validate incoming task payloads and reject empty structures",
        budget=BudgetSpec(
            max_attempts=3, timeout_seconds=30.0, max_total_tokens=5000, max_cost_usd=0.25
        ),
        external_ref="GH-4",
    )
    runner = EngineeringWorkflowRunner(
        runtime=runtime,
        implementer_id="agent_implementer",
        checker_id="system_deterministic_checker",
        reviewer_id="agent_independent_reviewer",
        qa_id="system_qa_gate",
    )
    outcome = runner.run_workflow(task)
    assert outcome.task.stage == LifecycleStage.DONE
    assert outcome.task.status == TaskStatus.COMPLETED
    assert len([r for r in outcome.runs if r.stage == LifecycleStage.IMPLEMENT]) == 2
    return outcome


def run_sensitive_approval_scenario(approved: bool) -> WorkflowOutcome:
    runtime = FakeRuntime()
    task = Task(
        title="Update production deployment policy manifest",
        description="Modify sensitive deployment gate rules",
        sensitive_actions=("policy.deployment.modify",),
        requires_human_approval=True,
        budget=BudgetSpec(max_attempts=2, timeout_seconds=30.0),
        external_ref="GH-4-APPROVAL",
    )
    approvals: tuple[ApprovalRecord, ...] = ()
    if approved:
        approvals = (
            ApprovalRecord(
                task_id=task.task_id,
                approver_id="human_security_lead",
                status=ApprovalStatus.APPROVED,
                reason="Verified deployment policy diff and rollback plan",
            ),
        )
    runner = EngineeringWorkflowRunner(runtime=runtime)
    outcome = runner.run_workflow(task, approvals=approvals)
    if approved:
        assert outcome.task.stage == LifecycleStage.DONE
        assert outcome.task.status == TaskStatus.COMPLETED
    else:
        assert outcome.task.stage == LifecycleStage.HUMAN_APPROVAL
        assert outcome.task.status == TaskStatus.WAITING_APPROVAL
        assert outcome.final_decision is not None
        assert outcome.final_decision.decision == PolicyDecision.HUMAN_REQUIRED
    return outcome


def run_bounded_limit_scenario() -> WorkflowOutcome:
    runtime = FakeRuntime(
        stage_handlers={
            (LifecycleStage.CHECK, 1): FakeStepSpec(
                status=RunStatus.SUCCEEDED,
                output_text="Deterministic test suite failed on attempt 1",
                evidence_specs=(
                    {
                        "kind": EvidenceKind.DETERMINISTIC_CHECK,
                        "producer_id": "system_deterministic_checker",
                        "producer_role": "checker",
                        "passed": False,
                        "verified": True,
                        "summary": "pytest exit code 1: test_edge_case failed",
                    },
                ),
            ),
            (LifecycleStage.CHECK, 2): FakeStepSpec(
                status=RunStatus.SUCCEEDED,
                output_text="Deterministic test suite failed on attempt 2",
                evidence_specs=(
                    {
                        "kind": EvidenceKind.DETERMINISTIC_CHECK,
                        "producer_id": "system_deterministic_checker",
                        "producer_role": "checker",
                        "passed": False,
                        "verified": True,
                        "summary": "pytest exit code 1: test_timeout_case failed",
                    },
                ),
            ),
        }
    )
    task = Task(
        title="Refactor retry backoff calculation",
        description="Bounded loop must stop after max_attempts=2",
        budget=BudgetSpec(max_attempts=2, timeout_seconds=15.0),
        external_ref="GH-4-LIMIT",
    )
    runner = EngineeringWorkflowRunner(runtime=runtime)
    outcome = runner.run_workflow(task)
    assert outcome.task.stage == LifecycleStage.ESCALATED
    assert outcome.task.status == TaskStatus.ESCALATED
    assert outcome.final_decision is not None
    assert "max_attempts_exceeded" in outcome.final_decision.violated_rules
    return outcome


def run_fail_closed_missing_evidence_scenario() -> WorkflowOutcome:
    runtime = FakeRuntime()
    task = Task(
        title="Unverified completion claim check",
        description="Must fail closed when mandatory evidence artifacts are absent",
        budget=BudgetSpec(max_attempts=2, timeout_seconds=15.0),
        external_ref="GH-4-FAIL-CLOSED",
    )
    runner = EngineeringWorkflowRunner(runtime=runtime)
    outcome = runner.run_workflow(task, emit_default_stage_evidence=False)
    assert outcome.task.stage == LifecycleStage.FAILED
    assert outcome.task.status == TaskStatus.FAILED
    assert outcome.final_decision is not None
    assert outcome.final_decision.decision == PolicyDecision.DENY
    assert any(
        rule.startswith("missing_mandatory_evidence:")
        for rule in outcome.final_decision.violated_rules
    )
    return outcome


def summarize_outcome(name: str, outcome: WorkflowOutcome) -> dict[str, Any]:
    return {
        "scenario": name,
        "task_id": outcome.task.task_id,
        "final_stage": outcome.task.stage.value,
        "final_status": outcome.task.status.value,
        "decision": outcome.final_decision.decision.value if outcome.final_decision else None,
        "decision_reason": outcome.final_decision.reason if outcome.final_decision else None,
        "total_runs": len(outcome.runs),
        "implementer_attempts": len(
            [r for r in outcome.runs if r.stage == LifecycleStage.IMPLEMENT]
        ),
        "evidence_recorded": len(outcome.evidence),
        "events_recorded": [e.event_type for e in outcome.events],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Khamseen OS synthetic bounded engineering workflow example."
    )
    parser.add_argument(
        "--scenario",
        choices=("all", "remediation", "approval", "limit", "fail-closed"),
        default="all",
        help="Select which synthetic engineering workflow scenario to execute.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON summary.",
    )
    args = parser.parse_args(argv)

    summaries: list[dict[str, Any]] = []
    if args.scenario in ("all", "remediation"):
        summaries.append(summarize_outcome("remediation_loop_to_done", run_remediation_scenario()))
    if args.scenario in ("all", "approval"):
        summaries.append(
            summarize_outcome(
                "sensitive_action_waiting_approval",
                run_sensitive_approval_scenario(approved=False),
            )
        )
        summaries.append(
            summarize_outcome(
                "sensitive_action_approved_done",
                run_sensitive_approval_scenario(approved=True),
            )
        )
    if args.scenario in ("all", "limit"):
        summaries.append(
            summarize_outcome("bounded_max_attempts_escalation", run_bounded_limit_scenario())
        )
    if args.scenario in ("all", "fail-closed"):
        summaries.append(
            summarize_outcome(
                "fail_closed_on_missing_evidence", run_fail_closed_missing_evidence_scenario()
            )
        )

    if args.json:
        print(json.dumps({"scenarios": summaries}, indent=2))
        return 0

    print("=== Khamseen OS Synthetic Engineering Loop Example ===")
    for item in summaries:
        print(
            f"[{item['scenario']}] stage={item['final_stage']} "
            f"status={item['final_status']} decision={item['decision']} "
            f"attempts={item['implementer_attempts']} runs={item['total_runs']} "
            f"evidence={item['evidence_recorded']}"
        )
        print(f"  reason: {item['decision_reason']}")
        print(f"  events: {' -> '.join(item['events_recorded'])}")
    print("All synthetic engineering workflow scenarios completed deterministically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
