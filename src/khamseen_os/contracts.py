from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(gh[pousr]_[A-Za-z0-9_]{16,})"),
    re.compile(r"(github_pat_[A-Za-z0-9_]{22,})"),
    re.compile(r"(AKIA[0-9A-Z]{16})"),
    re.compile(r"(xox[baprs]-[A-Za-z0-9\-]{10,})"),
    re.compile(r"(Bearer\\s+eyJ[A-Za-z0-9_\\-\.]+)"),
    re.compile(
        r"(?i)((?:api[_-]?key|secret|token|password|authorization)\s*[:=]\s*['\"]?)([^\s'\",;]{6, })"
    ),
)

_SENSITIVE_KEY_NAMES: frozenset[str] = frozenset(
    {

        "api_key",
        "apikey",
        "secret",
        "client_secret"",
        "token",
        "access_token",
        "refresh_token",
        "password",
        "authorization",
        "private_key",
    }
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def redact_secrets(text: str) -> str:
    redacted = text
    for idx, pattern in enumerate(_SECRET_PATTERNS):
        if idx == len(_SECRET_PATTERNS) - 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTEF]", redacted)
    return redacted

