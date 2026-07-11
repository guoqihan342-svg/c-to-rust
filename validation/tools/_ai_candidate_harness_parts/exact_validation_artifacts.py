from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import re
from typing import Any

from .context_security import (
    atomic_write_json,
    canonical_json_bytes,
    redact_metadata_text,
    sensitive_key,
    sha256_path,
)


MAX_INPUT_BYTES = 512_000
MAX_JSON_BYTES = 64_000
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GATES = (
    "rustc",
    "generated_replay",
    "schema_diff",
    "negative_mutation",
    "unsafe_scan",
    "unsafe_ledger",
    "alias_contract",
    "abi_contract",
    "oracle_contract",
    "final_verification",
)
Runner = Callable[..., Mapping[str, Any]]


def persist(
    root: Path, candidate_sha: str, gates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    for index, name in enumerate(GATES, 1):
        atomic_write_json(root / f"{index:02d}-{name}.json", gates[name])
    atomic_write_json(
        root / "gate-index.json",
        {
            "schema_version": 1,
            "candidate_sha256": candidate_sha,
            "gates": {
                name: {
                    "path": f"{index:02d}-{name}.json",
                    "sha256": sha256_path(root / f"{index:02d}-{name}.json"),
                }
                for index, name in enumerate(GATES, 1)
            },
        },
    )
    return gates


def binding_failures(
    candidate_sha: str, actual_sha: str,
) -> dict[str, dict[str, Any]]:
    gates = {
        name: failed(
            candidate_sha,
            "candidate_sha256_mismatch",
            "Candidate bytes do not match the selected SHA-256.",
            expected=candidate_sha,
            actual=actual_sha,
        )
        for name in GATES
    }
    gates["final_verification"]["semantic_pass"] = False
    return gates


def gate(
    candidate_sha: str,
    status: str,
    *,
    failures: list[dict[str, Any]] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = {"candidate_sha256": candidate_sha, "status": status, **fields}
    if failures:
        payload["failures"] = failures
    return payload


def failed(
    candidate_sha: str, kind: str, message: str, **fields: Any,
) -> dict[str, Any]:
    return gate(candidate_sha, "failed", failures=[fact(kind, message)], **fields)


def fact(kind: str, message: str) -> dict[str, str]:
    return {"kind": kind, "message": message}


def new_dir(path: Path) -> Path:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError("attempt_dir must be a new independent directory")
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError("attempt_dir cannot be a filesystem root")
    resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def read_input(path: Path, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    data = path.read_bytes()
    if not data or len(data) > MAX_INPUT_BYTES or b"\0" in data:
        raise ValueError(f"{label} must be non-empty, NUL-free, and bounded")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8") from error
    return data


def make_dir(path: Path) -> Path:
    path.mkdir(exist_ok=False)
    return path


def require_sha(value: str, label: str) -> str:
    normalized = str(value).lower()
    if not SHA_RE.fullmatch(normalized):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return normalized


def valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def phase(value: Any) -> str:
    return value if value in {"compile", "run"} else "unknown"


def run(runner: Runner, **kwargs: Any) -> Mapping[str, Any]:
    try:
        result = runner(**kwargs)
    except Exception:
        return {"status": "failed", "runner_error": True}
    return result if isinstance(result, Mapping) else {"status": "failed", "malformed": True}


def execution_binding(
    result: Mapping[str, Any], candidate_sha: str, target_sha: Any,
) -> str | None:
    if result.get("candidate_sha256") != candidate_sha:
        return "candidate_sha256_mismatch"
    if result.get("target_contract_sha256") != target_sha:
        return "target_contract_sha256_mismatch"
    return None


def replay_binding(
    result: Mapping[str, Any],
    candidate_sha: str,
    test_sha: str,
    target_sha: Any,
    fixture_sha: Any,
) -> str | None:
    return (
        execution_binding(result, candidate_sha, target_sha)
        or (
            "replay_test_sha256_mismatch"
            if result.get("replay_test_sha256") != test_sha
            else None
        )
        or (
            "shared_fixture_identity_sha256_mismatch"
            if result.get("shared_fixture_identity_sha256") != fixture_sha
            else None
        )
    )


def observables(payload: Mapping[str, Any]) -> Any:
    if "observable_outputs" not in payload:
        raise ValueError("missing observable outputs")
    return safe_json(payload["observable_outputs"])


def safe_json(value: Any) -> Any:
    def visit(item: Any) -> Any:
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            if item != item or item in {float("inf"), float("-inf")}:
                raise ValueError("non-finite number")
            return item
        if isinstance(item, str):
            if redact_metadata_text(item) != item:
                raise ValueError("host-specific or sensitive text")
            return item
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, Mapping):
            output = {}
            for key, child in item.items():
                if not isinstance(key, str) or sensitive_key(key):
                    raise ValueError("unsafe key")
                output[key] = visit(child)
            return output
        raise ValueError("non-JSON value")

    safe = visit(value)
    if len(canonical_json_bytes(safe)) > MAX_JSON_BYTES:
        raise ValueError("JSON payload exceeds limit")
    return safe


def first_mismatch(
    expected: Any, actual: Any, path: str = "$",
) -> dict[str, Any] | None:
    if type(expected) is not type(actual):
        return {"path": path, "expected": expected, "actual": actual}
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return {
                "path": path,
                "expected_keys": sorted(expected),
                "actual_keys": sorted(actual),
            }
        for key in sorted(expected):
            found = first_mismatch(expected[key], actual[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return {
                "path": path,
                "expected_length": len(expected),
                "actual_length": len(actual),
            }
        for index, (left, right) in enumerate(zip(expected, actual)):
            found = first_mismatch(left, right, f"{path}[{index}]")
            if found:
                return found
        return None
    return (
        None
        if expected == actual
        else {"path": path, "expected": expected, "actual": actual}
    )


def forbidden_oracle_reference(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if (
                lowered in {"path", "report", "artifact_ref", "report_ref"}
                or lowered.endswith(("_path", "_report", "_ref"))
                or "accepted" in lowered
                or "historical" in lowered
                or forbidden_oracle_reference(child)
            ):
                return True
    elif isinstance(value, list):
        return any(forbidden_oracle_reference(child) for child in value)
    elif isinstance(value, str):
        normalized = value.replace("\\", "/").lower()
        return "validation/evidence/" in normalized or "/accepted/" in normalized
    return False
