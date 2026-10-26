# Architecture

Khamseen OS is an **open-source reliability and policy layer for autonomous AI agents**. It defines portable execution contracts, enforces bounded autonomy and policy gates, verifies deterministic evidence, and records append-only audit trails around agent runtimes.

## Reference stack

Khamseen OS operates alongside specialized open-source components without duplicating their responsibilities:

| Layer | Component | Responsibility | Owned by `khamseen-os`? |
|-------|-----------|----------------|-------------------------|
| **Organization & budgets** | **Paperclip** (optional) | Company goals, org hierarchy, budget allocation, high-level delegation | No (external integration via correlation metadata) |
| **Task coordination** | **Hermes Kanban / GitHub** | Task boards, issue tracking, pull requests, CI | No (linked via `Task.external_ref`) |
| **Reliability & policy** | **Khamseen OS** | `Task`, `Run`, `Evidence`, `PolicyDecision`, bounded loops, approval gates, conformance tests | **Yes (core package)** |
| **Agent execution** | **Hermes Agent** | Native tools, skills, session memory, model routing, CLI/ACP execution | No (invoked behind `RuntimeProvider`) |
| **OS / container isolation** | **External sandbox / container** | Process, filesystem, network, and credential isolation | No (required operational boundary) |

See [ADR-002: Runtime Portability and Hermes Reference Execution Boundary](docs/decisions/ADR-002-runtime-portability.md).

## Core primitives

- **`Task`** — requested outcome, scope constraints, required evidence types, budget limits, and sensitivity flags.
- **`Run`** — a single bounded execution attempt for a `Task`. Retries always generate a new `Run` record.
- **`Evidence`** — verifiable artifacts attached to a `Run` (e.g., deterministic test output, static check status, reviewer verdict, structured usage report).
- **`PolicyDecision`** — deterministic evaluation (`ALLOW`, `DENY`, `HUMAN_REQUIRED`) produced by the policy engine before and after runtime execution.
- **`RuntimeProvider`** — narrow execution interface implemented by `FakeRuntime` (for deterministic tests) and runtime adapters such as `HermesCliRuntimeAdapter`.
- **`ExecutionResult`** — normalized runtime output containing status, structured artifacts, verified token/cost usage, error details, and external session correlation.
- **`Event`** — append-only audit record linking `task_id`, `run_id`, `correlation_id`, stage transitions, policy decisions, and human approvals.

## Bounded engineering workflow

```
REQUEST → IMPLEMENT → CHECK → REVIEW → (REMEDIATE → CHECK → REVIEW)* → QA → (HUMAN_APPROVAL) → DONE
```

1. **`REQUEST`**: A scoped `Task` is registered and validated against policy.
2. **`IMPLEMENT`**: An implementer role executes a `Run` via a `RuntimeProvider`.
3. **`CHECK`**: Deterministic verification (tests, linting, artifact presence) produces `Evidence`.
4. **`REVIEW`**: A distinct reviewer role evaluates the implementation and check evidence.
5. **`REMEDIATE`**: If `CHECK` or `REVIEW` fails, a bounded correction loop spawns a new `Run` up to `max_attempts`, halting early on repeated identical failures or budget exhaustion.
6. **`QA`**: Final verification confirms all mandatory evidence is present and verified. If mandatory evidence is missing, the workflow **fails closed**.
7. **`HUMAN_APPROVAL`**: Conditional gate triggered when task policy or sensitive operations return `PolicyDecision.HUMAN_REQUIRED`.
8. **`DONE` / `FAILED` / `ESCALATED`**: Terminal auditable state.

## Cross-system correlation

Khamseen OS correlates identifiers across the stack without surrendering lifecycle state ownership:

- `Task.external_ref` links to a GitHub issue/PR or Hermes Kanban card.
- `Task.metadata["external_goal_id"]` optionally links to a Paperclip goal or budget scope.
- `Run.correlation_id` threads through all Khamseen `Event` and `Evidence` records.
- `Run.external_run_id` / `ExecutionResult.external_session_id` records the Hermes Agent `session_id` reported by `--usage-file`.

## Provider boundary and runtime independence

The `RuntimeProvider` protocol isolates Khamseen OS from runtime-specific internals:

| Provider | Purpose | Status in `khamseen-os` |
|----------|---------|-------------------------|
| **`FakeRuntime`** | Deterministic offline testing of workflows, failure modes, timeouts, and policy gates | Shipped in `khamseen_os` |
| **Hermes Agent** ([NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)) | Reference execution runtime (`hermes --oneshot ... --usage-file ...`) | Typed adapter contract + offline conformance fixtures |

No proprietary IDE harness (Cursor, Cursor Cloud, Grok) or OpenCode dependency is used or permitted as a runtime dependency of `khamseen-os`.

## Security and isolation boundary

Python policy objects enforce deterministic state machines, retry caps, cost/token budgets, approval gates, and evidence verification. However:

- **OS-level process, filesystem, network, and credential isolation must be enforced by an external container, VM, or sandbox runtime.**
- Runtime adapters must scrub sensitive environment variables before subprocess invocation and redact secret patterns from captured outputs and `Evidence` records.
- Because scripted CLI invocations (such as `hermes --oneshot`) bypass interactive terminal prompts by design, Khamseen OS enforces `HUMAN_REQUIRED` gates prior to sensitive runtime dispatch.

## Distinctions (summary)

Full glossary: [docs/concepts.md](docs/concepts.md).

| Term A | Term B | Relationship |
|--------|--------|--------------|
| Agent | Model | Agent is role identity; model is runtime configuration |
| Task | Run | Task is requested outcome; Run is a single attempt |
| Claim | Evidence | Agent output is a claim; Evidence is a verified artifact |
| Review finding | Policy decision | Finding is reviewer evidence; Policy decision (`ALLOW`/`DENY`/`HUMAN_REQUIRED`) enforces rules |
| Policy decision | Human approval | Policy flags `HUMAN_REQUIRED`; a human authority grants or rejects approval |
| Python policy | OS sandbox | Python enforces workflow contracts; OS/container enforces process and network isolation |

## Public vs private boundary

Generic reliability contracts, policy guards, conformance tests, and synthetic examples live in **this repository** (`khamseen-os`).
Proprietary business modules, internal configurations, and customer data remain in **private repositories** ([ADR-001](docs/decisions/ADR-001-public-core-private-modules.md)).
