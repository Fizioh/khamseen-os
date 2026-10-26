from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[A-Za-z0-9.\-]+)?$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_/\-]+$")


class ManifestValidationError(ValueError):
    """Raised when a domain module manifest violates the Khamseen OS module contract."""


@dataclass(frozen=True)
class SkillSpec:
    id: str
    capabilities: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    requires_human_approval: bool = False


@dataclass(frozen=True)
class ModuleManifest:
    id: str
    version: str
    chief_role: str
    capabilities: tuple[str, ...]
    tools: tuple[str, ...]
    data_scopes: tuple[str, ...]
    approval_policy: str
    skills: tuple[SkillSpec, ...] = field(default_factory=tuple)


def validate_module_manifest(
    data: dict[str, Any],
    existing_chief_roles: dict[str, str] | None = None,
) -> ModuleManifest:
    errors: list[str] = []
    required_keys = (
        "id",
        "version",
        "chief_role",
        "capabilities",
        "tools",
        "data_scopes",
        "approval_policy",
    )
    for key in required_keys:
        if key not in data:
            errors.append(f"Missing required field '{key}'")

    if errors:
        raise ManifestValidationError("; ".join(errors))

    module_id = str(data["id"]).strip()
    version = str(data["version"]).strip()
    chief_role = str(data["chief_role"]).strip()
    approval_policy = str(data["approval_policy"]).strip()

    if not module_id or not re.match(r"^[a-z][a-z0-9_\-]*$", module_id):
        errors.append(f"Invalid module id '{module_id}'")

    if not _SEMVER_RE.match(version):
        errors.append(f"Invalid semantic version '{version}'")

    if not chief_role:
        errors.append("Field 'chief_role' must be non-empty")

    if existing_chief_roles and module_id in existing_chief_roles:
        existing_chief = existing_chief_roles[module_id]
        if existing_chief != chief_role:
            errors.append(
                f"Overlapping chief_role '{chief_role}' conflicts with '{existing_chief}' for module '{module_id}'"
            )

    raw_caps = data.get("capabilities")
    if not isinstance(raw_caps, list) or not raw_caps:
        errors.append("Field 'capabilities' must be a non-empty list")
        capabilities: tuple[str, ...] = ()
    else:
        capabilities = tuple(str(c).strip() for c in raw_caps)
        for cap in capabilities:
            if not _CAPABILITY_RE.match(cap):
                errors.append(
                    f"Invalid capability '{cap}': must follow '<domain>.<action>' convention"
                )

    raw_tools = data.get("tools")
    if not isinstance(raw_tools, list) or not raw_tools:
        errors.append("Field 'tools' must be a non-empty list")
        tools: tuple[str, ...] = ()
    else:
        tools = tuple(str(t).strip() for t in raw_tools)
        for tool in tools:
            if not _TOOL_RE.match(tool):
                errors.append(f"Invalid tool '{tool}': must follow '<namespace>.<action>' convention")

    raw_scopes = data.get("data_scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        errors.append("Field 'data_scopes' must be a non-empty list")
        data_scopes: tuple[str, ...] = ()
    else:
        data_scopes = tuple(str(s).strip() for s in raw_scopes)
        for scope in data_scopes:
            if "*" in scope or not _SCOPE_RE.match(scope):
                errors.append(
                    f"Invalid or wildcard data_scope '{scope}': must follow '<resource>:<scope>'"
                )

    if not approval_policy:
        errors.append("Field 'approval_policy' must be non-empty")

    skills_list: list[SkillSpec] = []
    raw_skills = data.get("skills", [])
    if not isinstance(raw_skills, list):
        errors.append("Field 'skills' must be a list when provided")
    else:
        tool_set = set(tools)
        cap_set = set(capabilities)
        for raw_skill in raw_skills:
            if not isinstance(raw_skill, dict):
                errors.append("Each skill entry must be an object")
                continue
            skill_id = str(raw_skill.get("id", "")).strip()
            if not skill_id:
                errors.append("Skill entry missing 'id'")
            skill_caps = tuple(str(c).strip() for c in raw_skill.get("capabilities", []))
            skill_tools = tuple(str(t).strip() for t in raw_skill.get("allowed_tools", []))
            for sc in skill_caps:
                if sc not in cap_set:
                    errors.append(
                        f"Skill '{skill_id}' references undeclared capability '{sc}'"
                    )
            for st in skill_tools:
                if st not in tool_set:
                    errors.append(
                        f"Skill '{skill_id}' references unregistered tool '{st}'"
                    )
            skills_list.append(
                SkillSpec(
                    id=skill_id,
                    capabilities=skill_caps,
                    allowed_tools=skill_tools,
                    requires_human_approval=bool(raw_skill.get("requires_human_approval", False)),
                )
            )

    if errors:
        raise ManifestValidationError("; ".join(errors))

    return ModuleManifest(
        id=module_id,
        version=version,
        chief_role=chief_role,
        capabilities=capabilities,
        tools=tools,
        data_scopes=data_scopes,
        approval_policy=approval_policy,
        skills=tuple(skills_list),
    )


def load_and_validate_manifest(path: Path) -> ModuleManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ManifestValidationError("Manifest root must be a JSON object")
    return validate_module_manifest(raw)
