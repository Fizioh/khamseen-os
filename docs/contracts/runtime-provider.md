# Runtime Provider Interface and Conformance Contract

This contract defines the `RuntimeProvider` boundary in `khamseen_os` and the mandatory conformance test cases every runtime adapter must satisfy.

## Protocol surface (`RuntimeProvider`)

```python
class RuntimeProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    def execute(self, request: ExecutionRequest) -> ExecutionResult: ...

    def cancel(self, run_id: str) -> bool: ...

    def healthcheck(self) -> bool: ...
```

### Input: `ExecutionRequest`

- `task_id`: Khamseen OS task identifier.
- `run_id`: Khamseen OS single-attempt run identifier.
- `attempt`: 1-based attempt counter for bounded remediation loops.
- `agent_id` & `agent_role`: Organizational identity (`implementer`, `checker`, `reviewer`, `qa`).
- `stage`: Active `LifecycleStage`.
- `prompt`: Scoped task instruction.
- `correlation_id`: End-to-end audit correlation identifier.
- `timeout_seconds`: Hard wall-clock execution limit for this run.
- `allowed_tools`, `allowed_skills`, `allowed_scopes`: Explicit policy allowlists for the runtime turn.
- `workdir` & `resume_session_id`: Optional workspace path and external session resume handle.

### Output: `ExecutionResult`

- `run_id`, `task_id`, `correlation_id`: Must match the originating `ExecutionRequest`.
- `status`: Normalized `RunStatus` (`SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`).
- `output_text`: Redacted output text from the runtime.
- `claimed_success`: Whether the runtime/agent claimed completion (never trusted without `Evidence`).
- `duration_seconds`: Measured wall-clock runtime duration.
- `usage`: Normalized `UsageMetrics` (`input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`, `api_calls`, `verified`, `cost_source`).
- `evidence`: Tuple of structured `Evidence` records emitted during the run.
- `error_code` & `error_message`: Normalized failure details when `status != RunStatus.SUCCEEDED`.
- `external_session_id`: Runtime session identifier (e.g., Hermes `session_id`) for cross-system correlation.

## Mandatory conformance suite (`ProviderConformanceHarness`)

Every `RuntimeProvider` adapter (`FakeRuntime`, `HermesCliRuntimeAdapter`, or future adapters) is verified against nine deterministic checks in `ProviderConformanceHarness`:

1. **`successful_execution`**: Completes `REQUEST → IMPLEMENT → CHECK → REVIEW → QA → DONE` when all verification stages pass.
2. **`runtime_failure`**: Normalizes non-zero exits or runtime exceptions into `RunStatus.FAILED` with preserved `run_id` and `correlation_id`.
3. **`timeout_and_cancellation`**: Enforces `timeout_seconds` (`RunStatus.TIMED_OUT`) and honors `cancel(run_id)` (`RunStatus.CANCELLED`).
4. **`repeated_failures`**: Triggers the identical-failure circuit breaker (`repeated_identical_failure_limit_reached`) and escalates without exhausting remaining attempts.
5. **`missing_evidence`**: Fails closed (`LifecycleStage.FAILED`, `PolicyDecision.DENY`) when mandatory verification evidence is absent, even if `claimed_success=True`.
6. **`budget_rejection`**: Halts and escalates when cumulative verified token or cost usage exceeds `Task.budget`.
7. **`approval_required`**: Pauses in `WAITING_APPROVAL` (`PolicyDecision.HUMAN_REQUIRED`) for sensitive tasks until an independent human `ApprovalRecord` is supplied.
8. **`normalized_execution_results`**: Returns a valid, secret-redacted `ExecutionResult` with `UsageMetrics` and `external_session_id`.
9. **`repeated_event_delivery_idempotency`**: Deduplicates repeated event deliveries (`record_external_event`) so duplicate webhooks or callbacks never produce duplicate completion events.

## Running the conformance suite

```bash
pytest tests/test_runtime_conformance.py -v
```
