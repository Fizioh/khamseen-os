# Getting Started

**Experimental alpha.** `khamseen-os` provides a minimal, dependency-light Python reliability and policy layer for autonomous AI agents, alongside a deterministic `FakeRuntime` and a documented Hermes Agent integration contract.

## Prerequisites

- Python `3.11+`
- `git`
- No API keys, cloud credentials, or external databases are required for local installation, examples, or default tests.

## Quickstart (clean clone)

```bash
git clone https://github.com/Fizioh/khamseen-os.git
cd khamseen-os
python -m venv .venv
```

Activate the virtual environment and install development dependencies:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

python -m pip install -e ".[dev]"
```

## Run the synthetic engineering workflow example

Execute the bounded engineering workflow (`REQUEST → IMPLEMENT → CHECK → REVIEW → REMEDIATE → QA → HUMAN_APPROVAL → DONE`) using `FakeRuntime`:

```bash
python examples/engineering-loop/run_example.py
python examples/engineering-loop/run_example.py --json
```

See [examples/engineering-loop/README.md](../examples/engineering-loop/README.md) for scenario details.

## Run tests and quality checks

```bash
pytest -v
ruff check src/ tests/ examples/
mypy src/
```

## Failure modes and troubleshooting

- **`ModuleNotFoundError: No module named 'khamseen_os'`**: Ensure you ran `python -m pip install -e ".[dev]"` inside your active virtual environment (or set `PYTHONPATH=src`).
- **Missing Hermes CLI during optional live tests**: Default `pytest` runs strictly offline using `FakeRuntime` and deterministic fixtures. Live Hermes CLI tests are skipped unless `KHAMSEEN_HERMES_LIVE_TEST=1` is explicitly set and `hermes` is installed on `PATH`.

## Suggested reading order

```mermaid
flowchart LR
  A[README.md] --> B[docs/concepts.md]
  B --> C[ARCHITECTURE.md]
  C --> D[docs/decisions/ADR-002-runtime-portability.md]
  D --> E[examples/engineering-loop/README.md]
  E --> F[CONTRIBUTING.md]
```
