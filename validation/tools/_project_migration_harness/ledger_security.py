from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


class LedgerError(RuntimeError):
    pass


class AttemptLimitReached(LedgerError):
    pass


class LeaseConflict(LedgerError):
    pass


class StaleFence(LedgerError):
    pass


class SchemaVersionError(LedgerError):
    pass


_SECRET_NAMES = {
    "apikey", "authorization", "bearertoken", "clientsecret", "credential",
    "credentials", "password", "refreshtoken", "secret", "token",
}
_SECRET_TEXT = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:api[-_ ]?key|authorization|bearer[-_ ]?token|client[-_ ]?secret|"
    r"credential|password|refresh[-_ ]?token|secret|token)\s*[:=]\s*[^\s,;]{4,}",
    r"\bbearer\s+[a-z0-9._~+/=-]{8,}",
    r"\b(?:sk|rk|pk)-(?:proj-)?[a-z0-9_-]{12,}",
    r"\bgh[pousr]_[a-z0-9]{12,}",
    r"\bAKIA[A-Z0-9]{16}\b",
    r"\beyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\b",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@",
))
_ERROR_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
_SEMANTIC_CLAIMS = {"accepted", "gate_passed", "semantic_pass", "verified"}


def _secret_name(value: Any) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", str(value).lower())
    return compact in _SECRET_NAMES or any(
        compact.endswith(suffix)
        for suffix in ("apikey", "accesstoken", "bearertoken", "clientsecret", "credential",
                       "credentials", "password", "refreshtoken", "secret", "token")
    )


def contains_secret_text(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in _SECRET_TEXT)


def assert_no_secrets(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _secret_name(key) or contains_secret_text(str(key)):
                raise ValueError(f"secret-bearing field is not ledger-safe: {path}.{key}")
            assert_no_secrets(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            assert_no_secrets(child, f"{path}[{index}]")
    elif isinstance(value, str) and contains_secret_text(value):
        raise ValueError(f"secret-bearing value is not ledger-safe: {path}")


def assert_no_semantic_claims(value: Any, path: str = "worker_payload") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in _SEMANTIC_CLAIMS:
                raise ValueError(f"worker semantic acceptance claim is forbidden: {path}.{key}")
            assert_no_semantic_claims(child, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            assert_no_semantic_claims(child, f"{path}[{index}]")
    elif isinstance(value, str):
        normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        if normalized in _SEMANTIC_CLAIMS:
            raise ValueError(f"worker semantic acceptance claim is forbidden: {path}")


def safe_json(value: Mapping[str, Any] | None) -> str:
    payload = dict(value or {})
    assert_no_secrets(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sanitize_error_key(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("error_key must be a non-empty string when provided")
    candidate = value.strip()
    if contains_secret_text(candidate):
        return "redacted_sensitive_error"
    if _ERROR_KEY.fullmatch(candidate):
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:16]
    return f"opaque_error_{digest}"


__all__ = [
    "LedgerError", "LeaseConflict", "SchemaVersionError", "StaleFence",
    "assert_no_secrets", "assert_no_semantic_claims", "safe_json", "sanitize_error_key",
]
