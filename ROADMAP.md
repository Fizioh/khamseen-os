# Roadmap

**Experimental alpha.** Dates are indicative; scope may change as the open core is extracted.

This roadmap tracks the **open repository** (`khamseen-os`). It does not mirror a private issue tracker.

## Phase 0 — Open documentation (current)

- [x] Public repository with Apache 2.0 license
- [x] README, architecture, concepts, module contract
- [x] Contributing, security, GitHub templates
- [x] Starter issues for contributors
- [ ] Community review of contracts (ongoing)

**Deliverable:** a credible entry point for contributors without claiming a shipped runtime.

## Phase 1 — Extract generic core

- [ ] Isolate control-plane models and services (Agent, Task, Run, Event, Approval)
- [ ] Remove domain-specific coupling from the extracted core
- [ ] Reproducible dev bootstrap + minimal synthetic scenario
- [ ] CI for the extracted core (lint, typecheck, tests)

**Exit criteria:** a contributor can clone, run tests, and execute a **synthetic** task/run/event flow without private modules.

## Phase 2 — Contracts & transitions

- [ ] Codify Task/Run/Event state machines and allowed transitions
- [ ] Document gate types and mapping to human approval
- [ ] Skills registry and capability routing contract
- [ ] Bounded graph + correction loop enforcement

## Phase 3 — Provider conformance

- [ ] First provider interface (runtime/harness) frozen enough for adapters
- [ ] Conformance test suite (fake provider + one reference adapter behind feature flag)
- [ ] Context / review provider stubs

## Phase 4 — Modules (examples)

- [ ] Reference **engineering** module (skills + tools, no proprietary data)
- [ ] Module loader validation against [docs/module-contract.md](docs/module-contract.md)
- [ ] Additional domain examples as documentation + optional sample modules

## Explicitly later

- Multi-tenancy, billing, hosted SaaS control plane
- Guaranteed compatibility with any specific IDE or vendor agent
- Copying proprietary business modules into the open repo

## How to help

Pick an [open issue](https://github.com/Fizioh/khamseen-os/issues) labeled `good first issue` or `help wanted`, or propose a contract clarification PR.
