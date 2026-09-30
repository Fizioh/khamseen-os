# Architecture

Khamseen OS is a **control plane** for agentic organizations: it records who did what, under which policy, with auditable events and explicit gates — while **domain modules** supply chiefs, skills, tools, and data scopes.

This document describes the **target open-core architecture**. The public repository is documentation-first; a private prototype explores implementation details that will be **extracted** incrementally.

## Layers

| Layer | Responsibility | Open core? |
|-------|----------------|------------|
| **Human authority** | Policy, budgets, final approvals | Contract + APIs |
| **Control plane** | Task, Run, Event, Tool, Decision, Approval | Yes (target) |
| **Org / delegation** | Chiefs, roles, escalation | Module-defined |
| **Execution graph** | Units, dependencies, parallelism, gates | Yes (target) |
| **Correction loop** | Per-unit produce/check/correct | Bounded by policy |
| **Providers** | Runtime, context, memory, knowledge, review | Pluggable adapters |

## Core entities (control plane)

- **Agent** — organizational identity (not a model name).
- **Task** — requested outcome or unit of work.
- **Run** — one execution attempt for a task (retries are new runs).
- **Event** — append-only audit record with correlation id.
- **Tool / ToolCall** — registered actions and invocations with redacted I/O.
- **Decision** — recorded judgment (automated or agent-produced summary).
- **Approval** — human or policy gate state (e.g. pending, approved, rejected).

Emerging orchestration concepts (names may stabilize during extraction):

- **Unit** — node in the execution graph.
- **Gate** — checkpoint (automated, review, human).
- **Correction edge** — retry/remediation path after failure.

## Delegation org chart vs execution graph

**Org chart** (delegation):

```
Human authority → domain chief → managers → specialists → workers
```

Defines **who may delegate to whom** and default escalation.

**Execution graph** (dependencies):

```
Unit A ──┬──► Unit B ──► Gate ──► Human approval
         └──► Unit C ──► Review agent
```

Defines **order and dependencies**. Prefer parallel fan-out when there is no real data dependency.

**Loop** (inside one unit):

```
produce → check → (fail → correct → check)* → pass
```

Loops are **bounded**; repeated identical failure escalates.

## Lifecycle (target)

`REQUEST` → `PLAN` → `DELEGATE` → `IMPLEMENT` → `REVIEW` → `REMEDIATE` → `QA` → `HUMAN_APPROVAL` → `DONE`

- **REMEDIATE** is entered after a failed review/check, not on every task.
- **HUMAN_APPROVAL** is conditional on workflow policy.

## Provider boundaries

Providers are **replaceable** behind narrow interfaces. The control plane must boot without any single vendor.

| Provider kind | Purpose | Integration status (public repo) |
|---------------|---------|----------------------------------|
| **Runtime / harness** | Execute agent work (CLI, HTTP worker, IDE agent) | Spec + prototype evaluation (e.g. Hermes) — not shipped here |
| **Context** | Assemble prompts/state for a run | Documented contract only |
| **Memory** | Durable agent/session memory | Documented contract only |
| **Knowledge** | Retrieval over corpora | Documented contract only |
| **Review** | Independent verification (tests, diff, policy) | Documented contract only |
| **Durable execution** | Long-running jobs, checkpoints | Planned |

Candidate tools (Cursor, Codex, Claude Code, OpenClaw, MCP servers) are **integration options** under the runtime/harness boundary — not bundled dependencies of this repository.

## Module boundary

Domain modules attach chiefs, tool catalogs, skills, and data scopes. They must not embed client secrets, production configs, or proprietary business logic in the open core.

See [docs/module-contract.md](docs/module-contract.md).

## Distinctions (summary)

Full glossary: [docs/concepts.md](docs/concepts.md).

| Term A | Term B | Relationship |
|--------|--------|----------------|
| Agent | Model | Agent is identity; model is runtime choice |
| Task | Run | Task is intent; run is attempt |
| Capability | Skill | Capability routes work; skill packages behavior |
| Skill | Tool | Skill composes tools + policy |
| Graph | Loop | Graph schedules units; loop converges one unit |
| Context | Memory | Context is assembled per run; memory persists |
| Review finding | Gate decision | Finding is evidence; gate applies policy |
| Gate decision | Human approval | Gate may auto-pass; human approval is explicit |

## Public vs private

Generic contracts and control-plane core → **this repository**.  
Client data, production configs, proprietary modules → **private repositories**.

[ADR-001: Public core and private modules](docs/decisions/ADR-001-public-core-private-modules.md)

## What exists where (honest)

| Artifact | `khamseen-os` (public) | Private prototype |
|----------|------------------------|-------------------|
| Architecture docs | Yes | Overlapping internal docs |
| Runnable Django monolith | No | Yes (experimental) |
| End-to-end domain E2E | No | Partial (orchestration paths exist; external engines often stubbed) |
| Published Python package | No | No |

Do not infer production readiness from the private prototype alone.
