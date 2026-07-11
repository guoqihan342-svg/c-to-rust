"""JSON, path, and policy contracts for the finite cross-project suite."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_SUITE = "validation/ai-finite-cross-project-suite.json"
MAX_JSON_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_PROJECTS = {"flashdb", "zlib-ng", "libuv"}
PROVENANCE_KINDS = {
    "real_upstream_source_slice",
    "real_upstream_source_fragment",
    "real_project_synthetic_carrier",
    "real_project_unbound_slice",
}
FRESH_SOURCE_PROVENANCE_KINDS = {
    "real_upstream_source_slice",
    "real_upstream_source_fragment",
}
FORBIDDEN_ROUTING_INPUTS = {
    "function_name",
    "project_id",
    "project_name",
    "slice_id",
    "target_id",
}


class SuiteContractError(ValueError):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SuiteContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SuiteContractError(f"{label} is unreadable: {exc.strerror}") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise SuiteContractError(f"{label} exceeds {MAX_JSON_BYTES} bytes")
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SuiteContractError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SuiteContractError(f"{label} must be a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def newline_variants(raw: bytes) -> tuple[bytes, ...]:
    normalized_lf = raw.replace(b"\r\n", b"\n")
    normalized_crlf = normalized_lf.replace(b"\n", b"\r\n")
    return tuple(dict.fromkeys((raw, normalized_lf, normalized_crlf)))


def matches_sha256(raw: bytes, expected: str) -> bool:
    return hashlib.sha256(raw).hexdigest() == expected


def line_span_byte_range(raw: bytes, line_start: int, line_end: int) -> tuple[int, set[int]] | None:
    if not raw:
        return None
    line_starts = [0]
    line_starts.extend(index + 1 for index, byte in enumerate(raw) if byte == 0x0A and index + 1 < len(raw))
    if line_end > len(line_starts):
        return None
    byte_start = line_starts[line_start - 1]
    final_line_start = line_starts[line_end - 1]
    newline_at = raw.find(b"\n", final_line_start)
    if newline_at < 0:
        return byte_start, {len(raw)}
    byte_end_without_newline = newline_at
    if newline_at > final_line_start and raw[newline_at - 1] == 0x0D:
        byte_end_without_newline -= 1
    return byte_start, {byte_end_without_newline, newline_at + 1}


def span_range_matches_variant(raw: bytes, span: dict[str, Any]) -> bool:
    expected = line_span_byte_range(raw, span["line_start"], span["line_end"])
    if expected is None:
        return False
    byte_start, allowed_byte_ends = expected
    return span["byte_start"] == byte_start and span["byte_end"] in allowed_byte_ends


def span_matches_variant(raw: bytes, span: dict[str, Any]) -> bool:
    return span_range_matches_variant(raw, span) and matches_sha256(
        raw[span["byte_start"] : span["byte_end"]], span["sha256"]
    )


def expect_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SuiteContractError(f"{label} keys mismatch: missing={missing}, extra={extra}")


def expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise SuiteContractError(f"{label} must be a non-empty bounded string")
    return value


def expect_nullable_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return expect_string(value, label)


def relative_parts(raw: str, label: str) -> tuple[str, ...]:
    text = expect_string(raw, label)
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or text.startswith("~")
        or any(part in {"", ".", ".."} for part in path.parts)
        or re.match(r"^[A-Za-z]:", text)
    ):
        raise SuiteContractError(f"{label} must be a safe POSIX repo-relative path")
    return path.parts


def safe_relative_path(repo_root: Path, raw: str, label: str) -> Path:
    parts = relative_parts(raw, label)
    root = repo_root.resolve()
    candidate = (root / Path(*parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SuiteContractError(f"{label} escapes the repository") from exc
    return candidate


def is_placeholder(value: str | None) -> bool:
    return value is None or (value.startswith("<") and value.endswith(">"))


def validate_policy(suite: dict[str, Any]) -> None:
    expect_keys(
        suite,
        {
            "schema_version",
            "suite_id",
            "purpose",
            "limits",
            "required_real_projects",
            "project_sources",
            "translation_policy",
            "items",
        },
        "suite",
    )
    if suite["schema_version"] != 1:
        raise SuiteContractError("suite.schema_version must be 1")
    if suite["purpose"] != "preflight-only":
        raise SuiteContractError("suite purpose must remain preflight-only")
    expect_string(suite["suite_id"], "suite.suite_id")

    limits = suite["limits"]
    if not isinstance(limits, dict):
        raise SuiteContractError("suite.limits must be an object")
    expect_keys(
        limits,
        {"max_items", "minimum_real_projects", "minimum_construct_families"},
        "suite.limits",
    )
    if limits != {
        "max_items": 20,
        "minimum_real_projects": 3,
        "minimum_construct_families": 10,
    }:
        raise SuiteContractError("suite limits must remain 20/3/10")

    projects = suite["required_real_projects"]
    if not isinstance(projects, list) or any(not isinstance(v, str) for v in projects):
        raise SuiteContractError("required_real_projects must be a string list")
    if len(projects) != len(set(projects)) or not REQUIRED_PROJECTS.issubset(projects):
        raise SuiteContractError("required_real_projects must uniquely include FlashDB, zlib-ng, and libuv")

    policy = suite["translation_policy"]
    if not isinstance(policy, dict):
        raise SuiteContractError("translation_policy must be an object")
    expect_keys(
        policy,
        {
            "ai_primary",
            "project_name_is_routing_input",
            "forbidden_routing_inputs",
            "allowed_routing_inputs",
            "semantic_gate",
            "translation_coverage_numerator",
        },
        "translation_policy",
    )
    if policy["ai_primary"] is not True or policy["project_name_is_routing_input"] is not False:
        raise SuiteContractError("AI must be primary and project names must not drive translation")
    forbidden = policy["forbidden_routing_inputs"]
    allowed = policy["allowed_routing_inputs"]
    if not isinstance(forbidden, list) or set(forbidden) != FORBIDDEN_ROUTING_INPUTS:
        raise SuiteContractError("forbidden_routing_inputs must preserve the anti-hardcoding set")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(v, str) for v in allowed):
        raise SuiteContractError("allowed_routing_inputs must be a non-empty string list")
    if set(allowed) & FORBIDDEN_ROUTING_INPUTS:
        raise SuiteContractError("project/name metadata cannot appear in allowed_routing_inputs")
    if policy["semantic_gate"] is not False or policy["translation_coverage_numerator"] != 0:
        raise SuiteContractError("preflight must not claim semantic acceptance or translation coverage")


def validate_project_sources(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict) or set(value) != REQUIRED_PROJECTS:
        raise SuiteContractError("project_sources must exactly contain flashdb, zlib-ng, and libuv")
    result: dict[str, dict[str, str]] = {}
    for project_id in sorted(REQUIRED_PROJECTS):
        source = value[project_id]
        label = f"project_sources.{project_id}"
        if not isinstance(source, dict):
            raise SuiteContractError(f"{label} must be an object")
        expect_keys(source, {"repository", "root", "commit"}, label)
        repository = expect_string(source["repository"], f"{label}.repository")
        root = expect_string(source["root"], f"{label}.root")
        commit = expect_string(source["commit"], f"{label}.commit")
        relative_parts(root, f"{label}.root")
        if not COMMIT_RE.fullmatch(commit):
            raise SuiteContractError(f"{label}.commit must be a pinned commit")
        result[project_id] = {"repository": repository, "root": root, "commit": commit}
    return result
