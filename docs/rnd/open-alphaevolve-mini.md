# R&D — Open AlphaEvolve Mini

> Status: research protocol. No optimization results measured yet.

**Future standalone repository:** `khamseen-alphaevolve-mini` (not created yet).

## Research question
Can a small, auditable proposal → test → selection loop improve deterministic algorithms over a fixed baseline using low-cost/open-weight models?

## Scope / V0
- Choose a non-sensitive deterministic optimization target: bin packing or shortest-path heuristic tuning, using fixed public fixtures.
- Define baseline, hard correctness constraints, quality score, time limit and resource budget.
- Proposed mutation is code or parameters with a complete versioned provenance trail.
- Compile/execute proposals only in network-isolated, disposable sandboxes.
- Accept candidate only after correctness tests, statistical evaluation and no regressions.

## Steps
1. Establish a reproducible baseline across train/validation/holdout datasets.
2. Generate bounded proposals with a model API or local model (version and cost recorded).
3. Run correctness oracle, performance microbenchmark and adversarial edge-case suite.
4. Reject failures; archive proposed diffs, measurements and full seed.
5. Select the best candidate only on validation, report holdout untouched until final evaluation.
6. Compare improvement against random search and a no-LLM heuristic under equal compute budget.

## Acceptance criteria
- One command replays the baseline and candidate evaluation from seeded fixtures.
- Explicit budget, CPU/memory/time and step caps.
- Results cite logs and confidence intervals; no claimed discoveries until independently rerun.
- Human review before publication or execution against production systems.

## Links
- [R&D Notion hub](https://app.notion.com/p/3fc524057c2f81a081e4f3f2739f32ea)
- [R&D Linear project](https://linear.app/khamseen/project/khamseen-randd-frontier-tech-lab-2027-b15f6fbc3e25)
