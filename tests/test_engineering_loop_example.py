from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from khamseen_os import LifecycleStage, PolicyDecision, TaskStatus

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_SCRIPT = _REPO_ROOT / "examples" / "engineering-loop" / "run_example.py"


def test_engineering_loop_cli_all_scenarios_json() -> None:
    proc = subprocess.run(
        [sys.executable, str(_EXAMPLE_SCRIPT), "--json"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    scenarios = {item["scenario"]: item for item in payload["scenarios"]}

    remediation = scenarios["remediation_loop_to_done"]
    assert remediation["final_stage"] == LifecycleStage.DONE.value
    assert remediation["final_status"] == TaskStatus.COMPLETED.value
    assert remediation["decision"] == PolicyDecision.ALLOW.value
    assert remediation["implementer_attempts"] == 2
    assert "task.remediate" in remediation["events_recorded"]

    waiting = scenarios["sensitive_action_waiting_approval"]
    assert waiting["final_stage"] == LifecycleStage.HUMAN_APPROVAL.value
    assert waiting["final_status"] == TaskStatus.WAITING_APPROVAL.value
    assert waiting["decision"] == PolicyDecision.HUMAN_REQUIRED.value

    approved = scenarios["sensitive_action_approved_done"]
    assert approved["final_stage"] == LifecycleStage.DONE.value
    assert approved["final_status"] == TaskStatus.COMPLETED.value
    assert approved["decision"] == PolicyDecision.ALLOW.value

    bounded = scenarios["bounded_max_attempts_escalation"]
    assert bounded["final_stage"] == LifecycleStage.ESCALATED.value
    assert bounded["final_status"] == TaskStatus.ESCALATED.value
    assert bounded["decision"] == PolicyDecision.DENY.value
    assert bounded["implementer_attempts"] == 2

    fail_closed = scenarios["fail_closed_on_missing_evidence"]
    assert fail_closed["final_stage"] == LifecycleStage.FAILED.value
    assert fail_closed["final_status"] == TaskStatus.FAILED.value
    assert fail_closed["decision"] == PolicyDecision.DENY.value
    assert fail_closed["evidence_recorded"] == 0
