# Hermes Agent Reference Adapter Contract

**Reference runtime repository:** [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)  
**Adapter implementation:** `khamseen_os.adapters.HermesCliRuntimeAdapter`  
**Status:** Verified CLI contract + deterministic conformance fixtures (live execution opt-in via `KHAMSEEN_HERMES_LIVE_TEST=1`).

## Scope and non-duplication

Hermes Agent provides native agent loops, toolsets, skills, session SQLite storage, and Hermes Kanban coordination. Khamseen OS **does not** rebuild or take over Hermes memory, scheduling, or Kanban. Instead, `HermesCliRuntimeAdapter` wraps a single bounded `Run` attempt behind `RuntimeProvider`.

## Verified CLI interface

Inspection of `NousResearch/hermes-agent` (`pyproject.toml`, `hermes_cli/_parser.py`, and `hermes_cli/oneshot.py`) establishes the non-interactive one-shot entrypoint:

```bash
hermes \
  [--profile <profile>] \
  [--model <model>] \
  [--provider <provider>] \
  [--reasoning <level>] \
  [--toolsets <comma_separated_toolsets>] \
  [--skills <comma_separated_skills>] \
  [--resume <session_id>] \
  [--in <workdir>] \
  --oneshot "<prompt>" \
  --usage-file "<temp_usage_report.json>"
```

### Usage report ledger (`--usage-file`)

Hermes writes a structured JSON usage report even when a turn fails (`hermes_cli/oneshot.py`):

- Primary keys (`_USAGE_KEYS`):
  `estimated_cost_usd`, `cost_status`, `cost_source`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `total_tokens`, `api_calls`, `model`, `provider`, `session_id`, `completed`, `partial`, `interrupted`, `turn_exit_reason`.
- Grand total block (`total_including_auxiliary`):
  `estimated_cost_usd`, `total_tokens`, `api_calls`.

`HermesCliRuntimeAdapter.parse_usage_report` extracts `total_including_auxiliary` (with fallback to main-loop counters) into `UsageMetrics(verified=True)` and records a `USAGE_REPORT` `Evidence` artifact.

## Cross-system correlation

| Khamseen OS field | Hermes Agent source |
|-------------------|---------------------|
| `ExecutionRequest.task_id` | Exported as `KHAMSEEN_TASK_ID` in child environment |
| `ExecutionRequest.run_id` | Exported as `KHAMSEEN_RUN_ID` in child environment |
| `ExecutionRequest.correlation_id` | Exported as `KHAMSEEN_CORRELATION_ID` in child environment |
| `ExecutionResult.external_session_id` / `Run.external_run_id` | Populated from `session_id` in `--usage-file` JSON |
| `ExecutionRequest.resume_session_id` | Passed via `--resume <session_id>` |

## Security and policy boundaries

1. **One-shot approval bypass mitigation**:
   In `hermes --oneshot`, Hermes sets `HERMES_YOLO_MODE=1` and auto-bypasses interactive terminal prompts for scriptability. Consequently, Khamseen OS **must** evaluate `PolicyDecision.HUMAN_REQUIRED` in `PolicyEngine` before dispatching sensitive actions or privileged skills.
2. **Wildcard toolset prohibition**:
   `HermesCliRuntimeAdapter` rejects wildcard toolsets (`--toolsets all` or `--toolsets *`) unless `allow_wildcard_toolsets=True` is explicitly configured.
3. **Environment scrubbing and secret redaction**:
   `build_sanitized_env` forwards only allowlisted environment variables (`passthrough_env_keys`) to the subprocess, and all stdout/stderr/error fields pass through `redact_secrets` before entering `ExecutionResult` or `Evidence`.
4. **Cancellation and timeouts**:
   - Subprocess timeout (`request.timeout_seconds`) maps to `RunStatus.TIMED_OUT`.
   - Exit code `130` (`_INTERRUPTED_EXIT_CODE`) or `"interrupted": true` in the usage report maps to `RunStatus.CANCELLED`.
   - Non-zero exit codes or `"completed": false` map to `RunStatus.FAILED`.

## Example usage

```python
from khamseen_os import (
    ExecutionRequest,
    HermesAdapterConfig,
    HermesCliRuntimeAdapter,
    LifecycleStage,
)

adapter = HermesCliRuntimeAdapter(
    config=HermesAdapterConfig(
        binary="hermes",
        model="anthropic/claude-sonnet-4.6",
        provider="openrouter",
        default_toolsets=("read_file", "pytest"),
    )
)

request = ExecutionRequest(
    task_id="task_101",
    run_id="run_101_1",
    attempt=1,
    agent_id="agent_implementer",
    agent_role="implementer",
    stage=LifecycleStage.IMPLEMENT,
    prompt="Run unit tests and summarize failures",
    correlation_id="corr_101",
    timeout_seconds=60.0,
)
```
