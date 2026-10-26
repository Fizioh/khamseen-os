# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` (`0.1.0a1` experimental alpha) | Security fixes and threat-model updates |
| Future tagged releases | Will be listed here as versions are published |

`khamseen-os` is currently in **experimental alpha**.

## Threat model and security boundaries

See [docs/security/threat-model.md](docs/security/threat-model.md) for the full 12-threat analysis covering prompt injection, untrusted repository instructions, malicious skills, tool privilege escalation, secret exposure, unauthorized process/network operations, forged execution evidence, budget exhaustion, approval bypass, cross-domain data leakage, supply-chain compromise, and unsafe autonomous remediation.

**Important operational boundary:** Python policy objects in `khamseen-os` enforce deterministic workflow contracts, evidence verification, budgets, and human approval gates. **OS-level process, filesystem, network, and credential isolation must be enforced by an external secure container or sandbox runtime.**

## Reporting a vulnerability

**Do not** open a public GitHub issue for undisclosed security vulnerabilities.

Report vulnerabilities privately via GitHub Security Advisories on [Fizioh/khamseen-os](https://github.com/Fizioh/khamseen-os/security) or by contacting the repository maintainers with:

- Description and potential impact
- Steps or minimal script to reproduce
- Affected commit SHA or module
- Suggested mitigation (optional)

## Safe contribution guidelines

- Never commit API keys, tokens, customer data, or private operational URLs.
- Keep `dependencies = []` in `pyproject.toml` free of unnecessary third-party runtime packages.
- Add deterministic regression tests in `tests/test_security_regressions.py` when hardening policy or adapter boundaries.
