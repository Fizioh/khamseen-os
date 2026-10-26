# Roadmap

**Experimental alpha.** This roadmap tracks the public open-source reliability and policy layer in `Fizioh/khamseen-os`.

## Milestone 0 — Open documentation & boundary definition (Completed)

- [x] Public repository under Apache-2.0 license
- [x] Core vocabulary (`docs/concepts.md`) and module boundary (`docs/module-contract.md`)
- [x] [ADR-001: Public core and private modules](docs/decisions/ADR-001-public-core-private-modules.md)
- [x] [ADR-002: Runtime portability and Hermes reference execution boundary](docs/decisions/ADR-002-runtime-portability.md)

## Milestone 1 — Executable reliability core & CI (Completed)

- [x] Zero-dependency Python package (`src/khamseen_os/`) with typed `Task`, `Run`, `Evidence`, `PolicyDecision`, `RuntimeProvider`, and `ExecutionResult` contracts
- [x] Deterministic state machines and bounded autonomy guards (`PolicyEngine`)
- [x] Runnable synthetic engineering workflow example (`examples/engineering-loop/`) using `FakeRuntime`
- [x] Public GitHub Actions CI (Pytest, Ruff, Mypy, example execution, Markdown link & secret validation)

## Milestone 2 — Provider conformance & Hermes reference adapter (Completed)

- [x] Reusable 9-point `ProviderConformanceHarness` (`src/khamseen_os/conformance.py`)
- [x] Experimental `HermesCliRuntimeAdapter` targeting verified `hermes --oneshot ... --usage-file ...` flags
- [x] JSON schema and validator for domain module manifests (`schemas/module-manifest.schema.json`, `src/khamseen_os/manifest.py`)
- [x] 12-vector autonomous agent threat model (`docs/security/threat-model.md`) with deterministic regression tests

## Milestone 3 — Next high-value open-source improvements (Up next)

- [ ] **Hermes ACP / Gateway streaming adapter**: Extend Hermes integration beyond `--oneshot` CLI to support streaming events and cancellation over `acp_adapter` / gateway sessions.
- [ ] **Cryptographic evidence signing & JSONL audit sink**: Add optional Ed25519/HMAC evidence signatures and append-only JSONL audit export for tamper-evident cross-process verification.
- [ ] **Container sandbox runner profile**: Provide a reference rootless Docker/Podman execution wrapper around `HermesCliRuntimeAdapter` enforcing network, filesystem, and PID isolation.

## Non-goals

- Rebuilding Paperclip org charts/budgets or Hermes Agent native memory, toolsets, or Kanban boards.
- Bundling IDE-specific harnesses (Cursor, Grok, OpenCode) as runtime dependencies.
- Copying proprietary domain modules into the open-source repository.

## How to contribute

Browse [open issues](https://github.com/Fizioh/khamseen-os/issues) labeled `good first issue` or `help wanted` and see [CONTRIBUTING.md](CONTRIBUTING.md).
