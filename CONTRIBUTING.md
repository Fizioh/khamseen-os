# Contributing

Thank you for helping shape Khamseen OS. This project is in **experimental alpha**: contracts and APIs will change.

## What we need now

- Documentation clarity and honest status labels
- Contract reviews (Task/Run, modules, providers)
- Tests and CI once the core code lands
- Issue triage and reproduction steps

## Before you start

1. Read [README.md](README.md) and [docs/concepts.md](docs/concepts.md).
2. Check [existing issues](https://github.com/Fizioh/khamseen-os/issues) to avoid duplicates.
3. For large changes, open an issue first to align on scope.

## Pull requests

1. Fork and branch from `main` (`feat/...`, `docs/...`, `fix/...`).
2. Keep PRs focused; prefer multiple small PRs over one giant diff.
3. Use the PR template completely.
4. **English** for commits, PR titles, and user-facing docs in this repo.

### Documentation PRs

- Verify relative links locally.
- Keep claims aligned with [README.md#project-status](README.md#project-status).
- Do not paste private credentials, client names, or internal ticket URLs.

## Code (when present)

- Match existing style; run lint and tests from the PR description.
- Do not commit secrets (`.env`, keys, tokens).
- Add tests for behavior changes where practical.

## Good first issues

Issues labeled `good first issue` are scoped for newcomers (doc fixes, small spec clarifications). Extraction and state-machine work is usually **not** a good first issue.

## Conduct

Be direct and technical. Critique ideas and contracts, not people. Security issues: see [SECURITY.md](SECURITY.md) — do not open public issues for vulnerabilities.

## License

Contributions are accepted under the [Apache License 2.0](LICENSE). You retain copyright; you grant the project a license to use your contribution.
