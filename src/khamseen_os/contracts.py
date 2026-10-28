from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(gh[pousr]_[A-Za-z0-9_]{16,})"),
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(xox[baprs]-[A-Za-z0-9\-]{10,})"),
    re.compile(r"(github_pat_[A-Za-z0-9_]{22,})"),
    re.compile(r"(Bearer\s+eyJ[A-Za-z0-9_\-\.]+)"),
    re.compile(
        r"(?i)((?:api[_-]?key|secret|token|password|authorization)\s*[:=]\s*['\"]?)([^\s'\",;]{6,})"
    ),
)

_SENSITIVE_KEY_NAMES: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "authorization",
        "private_key",
    }
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def redact_secrets(text: str) -> str:
    redacted = text
    for idx, pattern in enumerate(_SECRET_PATTERNS):
        if idx == len(_SECRET_PATTERNS) - 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        lowered = key.lower()
        if lowered in _SENSITIVE_KEY_NAMES or any(
            marker in lowered for marker in ("secret", "token", "password", "api_key", "private_key")
        ):
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str):
            sanitized[key] = redact_secrets(value)
        elif isinstance(value, dict):
            sanitized[key] = redact_mapping(value)
        elif isinstance(value, list):
            sanitized[key] = [
                redact_secrets(item)
                if isinstance(item, str)
                else (redact_mapping(item) if isinstance(item, dict) else item)
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class LifecycleStage(str, Enum):
    REQUEST = "REQUEST"
    PLAN = "PLAN"
    DELEGATE = "DELEGATE"
    IMPLEMENT = "IMPLEMENT"
    CHECK = "CHECK"
    REVIEW = "REVIEW"
    REMEDIATE = "REMEDIATE"
    QA = "QA"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    REMEDIATING = "REMEDIATING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class RunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EvidenceKind(str, Enum):
    IMPLEMENTATION_ARTIFACT = "IMPLEMENTATION_ARTIFACT"
    DETERMINISTIC_CHECK = "DETERMINISTIC_CHECK"
    INDEPENDENT_REVIEW = "INDEPENDENT_REVIEW"
    QA_VERIFICATION = "QA_VERIFICATION"
    USAGE_REPORT = "USAGE_REPORT"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


@dataclass(frozen=True)
class UsageMetrics:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    api_calls: int = 0
    verified: bool = False
    cost_source: str = "unknown"


@dataclass(frozen=True)
class BudgetSpec:
    max_attempts: int = 3
    timeout_seconds: float = 60.0
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None
    max_identical_failures: int = 2


def compute_evidence_hash(
    task_id: str,
    run_id: str,
    kind: EvidenceKind,
    producer_id: str,
    producer_role: str,
    passed: bool,
    summary: str,
    details: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "task_id": task_id,
            "run_id": run_id,
            "kind": kind.value,
            "producer_id": producer_id,
            "producer_role": producer_role,
            "passed": passed,
            "summary": summary,
            "details": details,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Evidence:
    task_id: str
    run_id: str
    kind: EvidenceKind
    producer_id: str
    producer_role: str
    passed: bool
    summary: str
    verified: bool = True
    details: dict[str, Any] = field(default_factory=dict)
    evidence_id: str = field(default_factory=lambda: new_id("ev"))
    content_hash: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        sanitized_summary = redact_secrets(self.summary)
        sanitized_details = redact_mapping(self.details)
        object.__setattr__(self, "summary", sanitized_summary)
        object.__setattr__(self, "details", sanitized_details)
        if not self.content_hash:
            digest = compute_evidence_hash(
                task_id=self.task_id,
                run_id=self.run_id,
                kind=self.kind,
                producer_id=self.producer_id,
                producer_role=self.producer_role,
                passed=self.passed,
                summary=sanitized_summary,
                details=sanitized_details,
            )
            object.__setattr__(self, "content_hash", digest)

    def verify_integrity(self) -> bool:
        expected = compute_evidence_hash(
            task_id=self.task_id,
            run_id=self.run_id,
            kind=self.kind,
            producer_id=self.producer_id,
            producer_role=self.producer_role,
            passed=self.passed,
            summary=self.summary,
            details=self.details,
        )
        return bool(self.verified and self.content_hash == expected)


def compute_approval_hash(
    task_id: str,
    approver_id: str,
    status: ApprovalStatus,
    reason: str,
    approved_actions: tuple[str, ...],
    approved_scopes: tuple[str, ...],
    run_id: str | None,
) -> str:
    canonical = json.dumps(
        {
            "task_id": task_id,
            "approver_id": approver_id,
            "status": status.value,
            "reason": reason,
            "approved_actions": list(approved_actions),
            "approved_scopes": list(approved_scopes),
            "run_id": run_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ApprovalRecord:
    task_id: str
    approver_id: str
    status: ApprovalStatus
    reason: str
    approved_actions: tuple[str, ...] = ()
    approved_scopes: tuple[str, ...] = ()
    verified: bool = True
    run_id: str | None = None
    approval_id: str = field(default_factory=lambda: new_id("apr"))
    content_hash: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        sanitized_reason = redact_secrets(self.reason)
        object.__setattr__(self, "reason", sanitized_reason)
        if not self.content_hash:
            digest = compute_approval_hash(
                task_id=self.task_id,
                approver_id=self.approver_id,
                status=self.status,
                reason=sanitized_reason,
                approved_actions=self.approved_actions,
                approved_scopes=self.approved_scopes,
                run_id=self.run_id,
            )
            object.__setattr__(self, "content_hash", digest)

    def verify_integrity(self) -> bool:
        expected = compute_approval_hash(
            task_id=self.task_id,
            approver_id=self.approver_id,
            status=self.status,
            reason=self.reason,
            approved_actions=self.approved_actions,
            approved_scopes=self.approved_scopes,
            run_id=self.run_id,
        )
        return bool(self.verified and self.content_hash == expected)


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: PolicyDecision
    reason: str
    violated_rules: tuple[str, ...] = ()
    requires_approval_for: tuple[str, ...] = ()


@dataclass
class Task:
    title: str
    description: str
    task_id: str = field(default_factory=lambda: new_id("task"))
    domain: str = "engineering"
    stage: LifecycleStage = LifecycleStage.REQUEST
    status: TaskStatus = TaskStatus.PENDING
    required_evidence: tuple[EvidenceKind, ...] = (
        EvidenceKind.DETERMINISTIC_CHECK,
        EvidenceKind.INDEPENDENT_REVIEW,
        EvidenceKind.QA_VERIFICATION,
    )
    sensitive_actions: tuple[str, ...] = ()
    requires_human_approval: bool = False
    allowed_tools: tuple[str, ...] = ()
    allowed_scopes: tuple[str, ...] = ()
    budget: BudgetSpec = field(default_factory=BudgetSpec)
    external_ref: str | None = None
    correlation_id: str = field(default_factory=lambda: new_id("corr"))
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class Run:
    task_id: str
    attempt: int
    agent_id: str
    agent_role: str
    stage: LifecycleStage
    run_id: str = field(default_factory=lambda: new_id("run"))
    status: RunStatus = RunStatus.QUEUED
    correlation_id: str = field(default_factory=lambda: new_id("corr"))
    external_run_id: str | None = None
    prompt: str = ""
    requested_tools: tuple[str, ...] = ()
    requested_scopes: tuple[str, ...] = ()
    duration_seconds: float = 0.0
    usage: UsageMetrics = field(default_factory=UsageMetrics)
    error_code: str | None = None
    error_message: str | None = None
    claimed_success: bool = False
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class ExecutionRequest:
    task_id: str
    run_id: str
    attempt: int
    agent_id: str
    agent_role: str
    stage: LifecycleStage
    prompt: str
    correlation_id: str
    timeout_seconds: float = 60.0
    allowed_tools: tuple[str, ...] = ()
    allowed_skills: tuple[str, ...] = ()
    allowed_scopes: tuple[str, ...] = ()
    sensitive_actions: tuple[str, ...] = ()
    workdir: str | None = None
    resume_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionResult:
    run_id: str
    task_id: str
    correlation_id: str
    status: RunStatus
    output_text: str = ""
    claimed_success: bool = False
    duration_seconds: float = 0.0
    usage: UsageMetrics = field(default_factory=UsageMetrics)
    evidence: tuple[Evidence, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    external_session_id: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_text", redact_secrets(self.output_text))
        if self.error_message is not None:
            object.__setattr__(self, "error_message", redact_secrets(self.error_message))
        object.__setattr__(self, "raw_metadata", redact_mapping(self.raw_metadata))


@dataclass(frozen=True)
class AuditEvent:
    task_id: str
    correlation_id: str
    event_type: str
    stage: LifecycleStage
    actor_id: str
    run_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: new_id("evt"))
    created_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", redact_mapping(self.payload))


@runtime_checkable
class RuntimeProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...

    def cancel(self, run_id: str) -> bool: ...

    def healthcheck(self) -> bool: ...
