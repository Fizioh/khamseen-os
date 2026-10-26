# ADR-002: Runtime Portability and Hermes Reference Execution Boundary

## Status

Accepted — experimental alpha

## Context

Autonomous agent systems often conflate four distinct concerns inside a single framework:

1. **Organizational governance** (company goals, role hierarchies, budgets, and delegation).
2. **Task coordination** (boards, queues, and collaborative assignment).
3. **Agent execution** (LLM turns, native tools, skills, local state, and session memory).
4. **Reliability, policy enforcement, and auditability** (execution contracts, independent verification evidence, bounded retry loops, and human approval gates).

Within our reference stack:

- **Paperclip** provides optional higher-level company organization, goals, budgets, and delegation.
- **Hermes Agent** ([NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)) provides the reference agent execution runtime, including native toolsets, skills, session memory, and CLI/ACP execution capabilities.
- **Hermes Kanban** provides native task collaboration and execution coordination.
- **GitHub** hosts the development backlog, source code, pull requests, and continuous integration.

If Khamseen OS rebuilt agent runners, dashboards, org charts, memory stores, or Kanban boards, it would duplicate mature capabilities in Hermes and Paperclip while weakening its core value. Conversely, relying directly on unconstrained runtime invocations leaves autonomous workflows vulnerable to missing verification evidence, runaway retry loops, silent approval bypasses (for example, one-shot CLI invocations that auto-bypass interactive prompts), and vendor lock-in.

## Decision

### 1. Khamseen OS is a provider-independent reliability and policy layer

Khamseen OS focuses exclusively on **portable execution contracts, deterministic policy enforcement, evidence verification, auditability, bounded autonomy, and runtime conformance**.

- **Hermes Agent** is our **reference execution runtime** behind the `RuntimeProvider` boundary.
- **Paperclip** is an **optional higher-level organizational integration** above Khamseen OS.
- **Khamseen OS** sits at the verification and policy boundary between task intent and runtime execution.

### 2. Separation of Task, Run, Evidence, Policy, and Runtime

Khamseen OS enforces strict separation across five primitives:

| Primitive | Responsibility | Authority |
|-----------|----------------|-----------|
| **Task** | Requested outcome, scope, constraints, and sensitivity policy. | Control plane (`khamseen_os`) |
| **Run** | A single bounded execution attempt for a `Task`. Retries always create a new `Run` record. | Control plane (`khamseen_os`) |
| **Evidence** | Verifiable, deterministic artifacts produced during or after a `Run` (test exit codes, lint results, diff hashes, independent review verdicts, usage ledgers). | Verified by control plane; never trusted solely from LLM prose |
| **Policy (`PolicyDecision`)** | Deterministic evaluation returning `ALLOW`, `DENY`, or `HUMAN_REQUIRED` based on attempt bounds, budgets, evidence completeness, and action sensitivity. | Deterministic Python policy engine + human authority |
| **Runtime (`RuntimeProvider`)** | Narrow execution interface that accepts a scoped `Task`/`Run` request and returns a normalized `ExecutionResult`. | Pluggable adapter (`FakeRuntime`, `HermesCliRuntimeAdapter`, etc.) |

### 3. Lifecycle state ownership and cross-system ID correlation

Khamseen OS owns the authoritative lifecycle state of a `Task` (`REQUEST` → `IMPLEMENT` → `CHECK` → `REVIEW` → `REMEDIATE` → `QA` → `HUMAN_APPROVAL` → `DONE` / `FAILED`) and its `Run` attempts. External systems correlate through explicit, immutable identifiers without collapsing state machines:

| System | Identifier | Correlation mapping in Khamseen OS |
|--------|------------|------------------------------------|
| **Paperclip** (optional) | Goal / delegation ticket ID | `Task.metadata["external_goal_id"]` |
| **Hermes Kanban / GitHub** | Card ID / GitHub Issue or PR number | `Task.external_ref` |
| **Khamseen OS** | `task_id`, `run_id`, `correlation_id` | Primary audit and state keys across all `Event` and `Evidence` records |
| **Hermes Agent** | `session_id` (from `--usage-file` or session store) | `Run.external_run_id` and `ExecutionResult.external_session_id` |

A runtime checkpoint or resumed Hermes session (`--resume <session_id>`) is a runtime-level execution detail. It does not replace Khamseen OS `Run` records, gate decisions, or append-only audit events.

### 4. Non-duplication of Hermes and Paperclip

The public `khamseen-os` package **must not** rebuild:

- Paperclip dashboards, org-chart editors, or company budget planners.
- Hermes Agent loops, native toolset implementations, skill hubs, session SQLite stores, or TUI/gateway servers.
- Hermes Kanban boards or schedulers.

Khamseen OS invokes the runtime through documented interfaces (such as `hermes --oneshot <prompt> --usage-file <path>` with scoped `--toolsets` and `--skills`) and verifies the resulting outputs and usage artifacts.

### 5. No Cursor, Grok, OpenCode, or subscription-specific runtime dependencies

- **No OpenCode dependency** may be introduced into the repository or runtime layer.
- **No Cursor, Cursor Cloud, Grok, or proprietary IDE/subscription authentication** may be a runtime dependency of `khamseen-os`.
- Development tools used by contributors to edit code must remain completely decoupled from the shipped package. The public package must install and pass all default tests offline without API keys or vendor accounts.

### 6. Security responsibilities enforced outside the LLM

An LLM or agent runtime cannot be the final authority on its own permissions, completion claims, or resource limits:

1. **Independent evidence verification**: A task is never marked `DONE` merely because an agent claims success in natural language. Deterministic checks and independent review findings must be attached as verified `Evidence`.
2. **External approval enforcement**: In scripted one-shot execution (such as `hermes -z / --oneshot`), interactive CLI prompts are bypassed by design (`HERMES_YOLO_MODE=1`). Therefore, Khamseen OS must evaluate `PolicyDecision.HUMAN_REQUIRED` **before** dispatching sensitive operations or privileged toolsets.
3. **Budget and loop bounds**: Maximum attempts, wall-clock timeouts, identical-failure circuit breakers, and token/cost budgets (verified via structured usage reports) are enforced deterministically by Khamseen OS.
4. **OS and container isolation boundary**: Python policy objects validate state transitions, budgets, and evidence contracts, but **OS-level process, filesystem, network, and credential isolation must be enforced by an external secure sandbox or container runtime**.

## Consequences

### Positive

- Clear, non-overlapping role in the open-source stack alongside Paperclip, Hermes Agent, Hermes Kanban, and GitHub.
- Deterministic, offline-runnable conformance tests using `FakeRuntime`.
- Portable contracts that allow Hermes Agent as the reference runtime while remaining testable and vendor-neutral.
- Explicit protection against silent approval bypass and unverified agent completion claims.

### Negative / Trade-offs

- Khamseen OS does not provide a standalone chat UI, LLM client, or Kanban board out of the box; users pair it with Hermes Agent or another conforming `RuntimeProvider`.
- Full process/network sandboxing requires external OS/container enforcement beyond the Python package.

## Alternatives considered

- **Rebuild a full agent orchestrator and dashboard in `khamseen-os`**: Rejected because it duplicates Hermes Agent, Hermes Kanban, and Paperclip while inflating maintenance scope.
- **Couple directly to LangGraph, OpenCode, or IDE-specific harnesses as the core domain model**: Rejected because coupling control-plane truth to a single graph library or vendor CLI breaks portability and blurs the boundary between runtime execution and policy verification.
- **Keep `khamseen-os` documentation-only**: Rejected because contracts without executable state machines, policy guards, and conformance tests cannot verify runtime behavior.
