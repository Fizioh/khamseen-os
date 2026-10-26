# Changelog

All notable changes to the public `khamseen-os` repository are documented in this file.

## [0.1.0a1] - 2026-10-26

### Added
- **Architecture & ADR-002**: Published `docs/decisions/ADR-002-runtime-portability.md` formalizing Hermes Agent (`NousResearch/hermes-agent`) as the reference execution runtime, Paperclip as optional higher-level organization, and Khamseen OS as a provider-independent reliability and policy layer.
- **Typed reliability core (`src/khamseen_os/`)**: Added zero-dependency Python 3.11+ package with `Task`, `Run`, `Evidence`, `PolicyDecision`, `RuntimeProvider`, `ExecutionRequest`, `ExecutionResult`, `AuditEvent`, `ApprovalRecord`, `BudgetSpec`, and `UsageMetrics`.
- **Bounded autonomy guards (`PolicyEngine`)**: Deterministic enforcement of allowed state transitions, max attempts, execution timeouts, verified token/cost budgets, repeated identical-failure circuit breakers, implementer vs reviewer separation, SHA-256 evidence integrity, and `HUMAN_REQUIRED` approval gates.
- **Synthetic engineering loop (`examples/engineering-loop/`)**: Runnable offline example (`REQUEST -> IMPLEMENT -> CHECK -> REVIEW -> REMEDIATE -> QA -> DONE`) using `FakeRuntime`.
- **Provider conformance suite (`ProviderConformanceHarness`)**: 9-point reusable conformance test suite for `RuntimeProvider` implementations.
- **Hermes CLI adapter (`HermesCliRuntimeAdapter`)**: Reference adapter contract and conformance fixtures for `hermes --oneshot ... --usage-file ...` with child environment sanitization, wildcard toolset blocking, and usage ledger verification.
- **Module manifest schema & validator**: Added `schemas/module-manifest.schema.json`, `examples/engineering-loop/module-manifest.json`, and `src/khamseen_os/manifest.py`.
- **Security threat model**: Published 12-vector threat model in `docs/security/threat-model.md` backed by 12 deterministic regression tests in `tests/test_security_regressions.py`.
- **Public GitHub Actions CI**: Added `.github/workflows/ci.yml` and `scripts/validate_repo.py` running Ruff, Mypy, Pytest, example execution, Markdown link validation, and secret/dependency hygiene checks.

### Contributors
- Recognized [@wufangyong973](https://github.com/wufangyong973) for clarifying `Agent ≠ Model` and `Task ≠ Run` in `docs/concepts.md` ([PR #12](https://github.com/Fizioh/khamseen-os/pull/12)).
