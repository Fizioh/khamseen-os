from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_FORBIDDEN_URL_SUBSTRINGS: tuple[str, ...] = (
    "linear.app/",
    "app.notion.com/",
)
_BANNED_DEP_SUBSTRINGS: tuple[str, ...] = (
    "opencode",
    "cursor",
    "grok",
    "django",
)
_LIVE_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[0-9]{10,}-[A-Za-z0-9\-]+\b")),
    ("private_key_pem", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


def _tracked_files() -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        cleaned = line.strip()
        if cleaned:
            candidate = _REPO_ROOT / cleaned
            if candidate.is_file():
                paths.append(candidate)
    return paths


def check_license() -> list[str]:
    errors: list[str] = []
    license_path = _REPO_ROOT / "LICENSE"
    if not license_path.is_file():
        errors.append("Missing LICENSE file at repository root")
        return errors
    content = license_path.read_text(encoding="utf-8", errors="replace")
    if "Apache License" not in content or "Version 2.0" not in content:
        errors.append("LICENSE file does not contain Apache License 2.0 header")
    return errors


def check_dependency_hygiene() -> list[str]:
    errors: list[str] = []
    pyproject_path = _REPO_ROOT / "pyproject.toml"
    if not pyproject_path.is_file():
        errors.append("Missing pyproject.toml")
        return errors
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    runtime_deps = project.get("dependencies", [])
    if runtime_deps:
        errors.append(
            f"Expected zero mandatory runtime dependencies in pyproject.toml, found: {runtime_deps}"
        )
    all_deps = list(runtime_deps)
    for extra_deps in project.get("optional-dependencies", {}).values():
        all_deps.extend(extra_deps)
    for dep in all_deps:
        lowered = str(dep).lower()
        for banned in _BANNED_DEP_SUBSTRINGS:
            if banned in lowered:
                errors.append(f"Prohibited dependency '{dep}' detected in pyproject.toml")
    return errors


def check_markdown_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    md_files = [f for f in files if f.suffix.lower() == ".md"]
    for md_file in md_files:
        raw_text = md_file.read_text(encoding="utf-8", errors="replace")
        for forbidden in _FORBIDDEN_URL_SUBSTRINGS:
            if forbidden in raw_text:
                errors.append(
                    f"{md_file.relative_to(_REPO_ROOT)}: contains internal link '{forbidden}'"
                )
        stripped = _FENCED_BLOCK_RE.sub("", raw_text)
        for match in _MD_LINK_RE.finditer(stripped):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1].strip()
            if (
                not target
                or target.startswith("#")
                or target.startswith("http://")
                or target.startswith("https://")
                or target.startswith("mailto:")
            ):
                continue
            path_part = target.split("#", 1)[0].split("?", 1)[0].strip()
            if not path_part:
                continue
            resolved = (md_file.parent / path_part).resolve()
            if not resolved.exists():
                errors.append(
                    f"{md_file.relative_to(_REPO_ROOT)}: broken relative link '{target}'"
                )
    return errors


def check_secrets(files: list[Path]) -> list[str]:
    errors: list[str] = []
    allowlisted_files = {
        Path("tests/test_security_regressions.py"),
        Path("scripts/validate_repo.py"),
    }
    for file_path in files:
        rel = file_path.relative_to(_REPO_ROOT)
        if rel in allowlisted_files:
            continue
        text = file_path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in _LIVE_SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{rel}: potential secret pattern matched ({label})")
    return errors


def main() -> int:
    files = _tracked_files()
    errors: list[str] = []
    errors.extend(check_license())
    errors.extend(check_dependency_hygiene())
    errors.extend(check_markdown_links(files))
    errors.extend(check_secrets(files))

    if errors:
        print("Repository validation failed:")
        for err in errors:
            print(f" - {err}")
        return 1

    print(
        "Repository hygiene, license, dependency, secret, and markdown link checks "
        f"passed across {len(files)} tracked files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
