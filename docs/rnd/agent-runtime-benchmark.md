# R&D — Agent Runtime Benchmark

> Status: proposal / protocol draft. No experimental results or implementation claimed.

**Future standalone repository:** `khamseen-agent-runtime-benchmark` (not created yet; this document is a research scaffold within Khamseen OS).

## Research question
Can free/low-cost and local model-runtime combinations reliably solve real software tasks at a lower **cost per validated success** than stronger hosted baselines?

## Scope
- Runtimes: Hermes Agent as the reference runtime; other runtimes only after passing the `khamseen-os` provider conformance suite.
- Models: open-weight and low-cost models alongside a pinned control baseline (provider/model/version recorded).
- Input: versioned tasks, frozen test environments, repository SHA, budgets, and timeout per run.
- Separate **generated code**, **independent review**, **deterministic tests**, **security checks**, and **human approval**.

## Protocol
1. Select 20+ licensed, deterministic coding tasks with baseline tests and objective oracles.
2. Record prompt, settings, provider, model version, cache behavior, token usage, tool actions, and duration.
3. Execute each run in an isolated, disposable environment, without production secrets or unrestricted egress.
4. Run the same hidden/regression test suite; count only proven success, not plausible-looking patches.
5. Publish pass@1, verified success rate, security exceptions, wall-clock, estimated costs, and confidence intervals; label missing cost data UNKNOWN.
6. Repeat to measure nondeterminism; publish artifacts and raw JSON/CSV, redact secrets.

## Acceptance criteria
- One-command reproducibility on documented fixtures.
- At least two model options and one baseline, with model/version pinned.
- Explicit failure cases, max budget, timeout, and cleanup enforced.
- No fabricated model metrics or benchmark claims.
