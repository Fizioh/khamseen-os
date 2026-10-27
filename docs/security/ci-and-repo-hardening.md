# CI and Repository Security Baseline

This document records the supply-chain, CI/CD, and repository hardening controls enforced on `Fizioh/khamseen-os`.

## 1. Untrusted pull request execution boundary

Public pull requests can propose changes to `pyproject.toml`, `src/`, `tests/`, or `.github/workflows/`. Therefore, all CI execution of PR code is treated as **untrusted code execution**:

1. **Ephemeral GitHub-hosted runners only**:
   - Workflows run exclusively on ephemeral `ubuntu-latest` GitHub-hosted virtual machines.
   - `self-hosted` runners (or any runner connected to internal VPS, production networks, or developer workstations) are strictly prohibited and blocked by `scripts/validate_repo.py`.
2. **Least-privilege `GITHUB_TOKEN`**:
   - Repository default workflow permissions are set to `read` (`can_approve_pull_request_reviews: false`).
   - `.github/workflows/ci.yml` explicitly sets `permissions: contents: read`.
   - `actions/checkout` is configured with `persist-credentials: false` so git credentials do not persist on disk during `pip install` or `pytest`.
3. **No privileged PR triggers or comment-triggered agents**:
   - `pull_request_target`, `workflow_run`, and `issue_comment` triggers are prohibited and rejected by `check_workflow_security()` in `scripts/validate_repo.py`.
   - No GitHub Action or bot in this repository automatically invokes Hermes Agent, Cursor, or any LLM with repository secrets in response to PR comments or issue bodies.
4. **Immutable 40-char SHA pinning**:
   - GitHub API action permissions enforce `sha_pinning_required: true`.
   - Every external GitHub Action in `.github/workflows/*.yml` is pinned to a full 40-character commit SHA and verified by `scripts/validate_repo.py`.

## 2. Repository security settings checklist

| Control | Status | Verification source |
|---------|--------|---------------------|
| Default `GITHUB_TOKEN` permissions = `read` | ✅ Enabled | `GET /repos/Fizioh/khamseen-os/actions/permissions/workflow` |
| Actions cannot approve PR reviews | ✅ Enabled | `can_approve_pull_request_reviews: false` |
| Require actions pinned to full commit SHA | ✅ Enabled | `sha_pinning_required: true` (`PUT /repos/Fizioh/khamseen-os/actions/permissions`) |
| Private vulnerability reporting | ✅ Enabled | `PUT /repos/Fizioh/khamseen-os/private-vulnerability-reporting` |
| Dependabot vulnerability alerts | ✅ Enabled | `PUT /repos/Fizioh/khamseen-os/vulnerability-alerts` |
| Dependabot version updates (`pip` & `github-actions`) | ✅ Configured | `.github/dependabot.yml` |
| Code owners for `.github/`, `pyproject.toml`, `src/`, `scripts/` | ✅ Configured | `.github/CODEOWNERS` (`@Fizioh`) |
| GitGuardian secret scanning check | ✅ Active on PRs | GitHub Check Run (`GitGuardian Security Checks`) |
| Zero mandatory runtime dependencies | ✅ Enforced in CI | `pyproject.toml` (`dependencies = []`) + `scripts/validate_repo.py` |
| Branch protection on `main` (require PR review + status checks) | ✅ Enforced | Configured on `main` branch protection rules |
