# Concepts

Canonical vocabulary for Khamseen OS. Names may refine during extraction; relationships should remain stable.

## Agent ≠ Model

An **Agent** is an organizational identity (chief, reviewer, worker) with roles, permissions, and configuration.

A **Model** is a runtime dependency (LLM, embedding model, etc.). Agents reference runtimes; they do not embed model names as source of truth.

## Task ≠ Run

A **Task** is requested work (outcome, ticket, intent).

A **Run** is one **attempt** to execute a task. Retries create new runs; failed attempts remain auditable.

Task status and run status are **independent** state machines.

## Capability ≠ Skill ≠ Tool

| Concept | Meaning |
|---------|---------|
| **Capability** | Routing label — what class of work an agent may accept (`code.write`, `review.independent`). |
| **Skill** | Packaged behavior — prompts, procedures, tool allowlists, policies. |
| **Tool** | Executable action with schema’d input/output (API call, git operation, test runner). |

Capabilities route work; skills compose tools; tools perform side effects.

## Graph ≠ Loop

| Concept | Meaning |
|---------|---------|
| **Execution graph** | Which units run, in what dependency order, with which gates. |
| **Correction loop** | Inside a single unit: produce → check → (remediate → check)* until pass or escalation. |

Create an edge A → B only when B consumes output or state from A. Prefer parallel fan-out when independent.

## Context ≠ Memory ≠ Knowledge ≠ Policy

| Concept | Meaning |
|---------|---------|
| **Context** | Material assembled for **this run** (messages, files, tool results). |
| **Memory** | Durable store across runs (with retention and scope rules). |
| **Knowledge** | Retrieved facts from corpora (RAG, docs, tickets). |
| **Policy** | Hard rules (budgets, permissions, approval requirements). |

Policy can deny an action even when context suggests it is possible.

## Review finding ≠ Gate decision ≠ Human approval

| Concept | Meaning |
|---------|---------|
| **Review finding** | Evidence from an independent reviewer (issue, test failure, diff note). |
| **Gate decision** | Policy outcome at a checkpoint (pass, fail, retry, escalate). |
| **Human approval** | Explicit human authorization for a sensitive outcome. |

Findings inform gates; gates may auto-fail or request remediation; human approval is a distinct primitive.

## Events and audit

**Events** are append-only records (with `correlation_id`) linking tasks, runs, agents, tool calls, decisions, and approvals. They are the operator-visible history — not unstructured log lines alone.

## Lifecycle stages

Target pipeline:

`REQUEST` → `PLAN` → `DELEGATE` → `IMPLEMENT` → `REVIEW` → `REMEDIATE` → `QA` → `HUMAN_APPROVAL` → `DONE`

**REMEDIATE** follows a failed check. **HUMAN_APPROVAL** is required only when workflow policy demands it.

## Business truth

Measured or financial outcomes must come from **deterministic systems** (engines, tests, databases) — not from LLM invention. Missing data is **unknown**, not zero or success.

## Modules

A **module** binds a domain chief, skills, tools, data scopes, and escalation defaults. Modules plug into the same control plane lifecycle.

See [module-contract.md](module-contract.md).

## Providers

External systems implement narrow interfaces:

- Runtime / harness
- Context assembly
- Memory
- Knowledge retrieval
- Independent review
- Durable execution (future)

Integrations under evaluation (Hermes, MCP, IDE agents) belong behind the **runtime/harness** boundary unless documented otherwise.
