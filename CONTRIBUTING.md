# Contributing to Khamseen OS

Thank you for contributing to Khamseen OS. This project is an **open-source reliability and policy layer for autonomous AI agents** in **experimental alpha**.

All contributions can be developed, tested, and verified locally using only Python 3.11+ and the public repository — **no private repository access, paid API keys, or vendor subscriptions are required**.

## Development setup

```bash
git clone https://github.com/Fizioh/khamseen-os.git
cd khamseen-os
python -m venv .venv

# Activate virtual environment:
# Linux / macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[dev]"
```

## Required local verification commands

Before opening a pull request, run the exact quality checks enforced by GitHub Actions CI:

```bash
ruff check src/ tests/ examples/ scripts/
mypy src/
pytest -v
python examples/engineering-loop/run_example.py
python scripts/validate_repo.py
```

## Git workflow and pull request standards

1. **Branching**: Fork and branch from `main` using descriptive names linked to the GitHub issue (`feat/<issue>-short-slug`, `fix/<issue>-short-slug`, `docs/<issue>-short-slug`, `test/<issue>-short-slug`).
2. **Atomic commits**: Make small, logical commits using **Conventional Commits** (`feat(core): ...`, `fix(policy): ...`, `test(conformance): ...`, `docs(security): ...`). Every commit must leave tests and linters passing.
3. **Focused pull requests**:
   - Reference the corresponding GitHub issue (`Closes #X`).
   - Complete the PR template with summary, scope, verification commands run, and known limitations.
   - Use **English** for code, comments, commit messages, issue discussions, and documentation.
4. **Guardrails**:
   - Do not add third-party runtime dependencies to `[project].dependencies` in `pyproject.toml` without an accepted ADR.
   - Never introduce Cursor, Grok, OpenCode, or subscription-specific dependencies.
   - Never commit secrets, API keys, or internal URLs.

## Finding a Good First Issue

Issues labeled [`good first issue`](https://github.com/Fizioh/khamseen-os/labels/good%20first%20issue) are self-contained and include:
- Exact file paths to inspect or modify.
- Clear acceptance criteria.
- Exact `pytest` / verification commands to run locally.
- Estimated difficulty and assurance that no external credentials or private access are needed.

### Maintainer review and acknowledgement workflow

- Maintainers review focused PRs against CI checks and acceptance criteria.
- Once merged, external contributors are recognized in the release notes and the [README Community acknowledgements](README.md#community-acknowledgements) section.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'khamseen_os'`**: Run `python -m pip install -e ".[dev]"` inside your virtual environment.
- **`Repository validation failed` in `scripts/validate_repo.py`**: Check for broken relative Markdown links, accidental secret-like strings (`sk-...`, `ghp_...`), or unintended entries in `[project].dependencies`.

## Conduct and security

Be direct, constructive, and technical. For security vulnerabilities, follow [SECURITY.md](SECURITY.md) rather than opening a public issue.

## License

Contributions are licensed under the [Apache License 2.0](LICENSE).
