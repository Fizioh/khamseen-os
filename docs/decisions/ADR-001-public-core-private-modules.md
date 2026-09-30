# ADR-001: Public core and private modules

## Status

Accepted — experimental alpha

## Context

Khamseen OS needs an **open** home for generic control-plane concepts, contracts, and extracted code so contributors can participate without exposing client data, production configuration, or proprietary domain logic.

A private prototype repository explores end-to-end orchestration including domain-specific business units. That history must not be bulk-copied into the public repository.

## Decision

1. **`khamseen-os` (public)** hosts:
   - Apache 2.0 licensed **open core** documentation and, incrementally, extracted generic control-plane code
   - Reference contracts (Task, Run, Event, module manifest, provider interfaces)
   - Contributor templates and public issues

2. **Private repositories** retain:
   - Client data and secrets
   - Production deployment configuration
   - Proprietary domain modules and business strategies
   - Experiments not ready for public API commitment

3. **Extraction** moves generic code across the boundary via reviewed PRs — not by making the private repo public.

4. **Documentation** may lead implementation during experimental alpha; public docs must **not** claim features exist in this repo unless the files are present here.

## Consequences

- Contributors can start with docs and contracts immediately.
- Domain modules (commerce, custom SaaS, etc.) can stay private while conforming to [module-contract.md](../module-contract.md).
- Issue trackers stay separate; public issues must not depend on private ticket ids.
- API stability guarantees begin only when runtime artifacts and versioning are published.

## Alternatives considered

- **Monorepo public from day one** — rejected due to leakage risk and mixed maturity.
- **Docs only forever** — rejected; open core code is the end state, docs unblock parallel contribution.
