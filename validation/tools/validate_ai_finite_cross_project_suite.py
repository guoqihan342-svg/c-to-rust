#!/usr/bin/env python3
"""Validate the bounded, real-project AI translation preflight suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_SUITE = "validation/ai-finite-cross-project-suite.json"
MAX_JSON_BYTES = 2 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_PROJECTS = {"flashdb", "zlib-ng", "libuv"}
PROVENANCE_KINDS = {
    "real_upstream_source_slice",
    "real_project_synthetic_carrier",
    "real_project_unbound_slice",
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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SuiteContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SuiteContractError(f"{label} is unreadable: {exc.strerror}") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise SuiteContractError(f"{label} exceeds {MAX_JSON_BYTES} bytes")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SuiteContractError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SuiteContractError(f"{label} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expect_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SuiteContractError(f"{label} keys mismatch: missing={missing}, extra={extra}")


def _expect_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise SuiteContractError(f"{label} must be a non-empty bounded string")
    return value


def _expect_nullable_string(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _expect_string(value, label)


def _relative_parts(raw: str, label: str) -> tuple[str, ...]:
    text = _expect_string(raw, label)
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


def _safe_relative_path(repo_root: Path, raw: str, label: str) -> Path:
    parts = _relative_parts(raw, label)
    root = repo_root.resolve()
    candidate = (root / Path(*parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SuiteContractError(f"{label} escapes the repository") from exc
    return candidate


def _is_placeholder(value: str | None) -> bool:
    return value is None or (value.startswith("<") and value.endswith(">"))


def _validate_policy(suite: dict[str, Any]) -> None:
    _expect_keys(
        suite,
        {
            "schema_version",
            "suite_id",
            "purpose",
            "limits",
            "required_real_projects",
            "translation_policy",
            "items",
        },
        "suite",
    )
    if suite["schema_version"] != 1:
        raise SuiteContractError("suite.schema_version must be 1")
    if suite["purpose"] != "preflight-only":
        raise SuiteContractError("suite purpose must remain preflight-only")
    _expect_string(suite["suite_id"], "suite.suite_id")

    limits = suite["limits"]
    if not isinstance(limits, dict):
        raise SuiteContractError("suite.limits must be an object")
    _expect_keys(
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
    _expect_keys(
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


def _validate_span_shape(span: Any, label: str) -> dict[str, Any] | None:
    if span is None:
        return None
    if not isinstance(span, dict):
        raise SuiteContractError(f"{label} must be an object or null")
    _expect_keys(
        span,
        {"line_start", "line_end", "byte_start", "byte_end", "sha256"},
        label,
    )
    for key in ("line_start", "line_end", "byte_start", "byte_end"):
        if not isinstance(span[key], int) or span[key] < (1 if key.startswith("line_") else 0):
            raise SuiteContractError(f"{label}.{key} is invalid")
    if span["line_end"] < span["line_start"] or span["byte_end"] <= span["byte_start"]:
        raise SuiteContractError(f"{label} has an inverted range")
    if not isinstance(span["sha256"], str) or not SHA256_RE.fullmatch(span["sha256"]):
        raise SuiteContractError(f"{label}.sha256 must be lowercase SHA-256")
    return span


def _spec_source_hash(spec: dict[str, Any], source_path: str) -> str | None:
    source = spec.get("source")
    if isinstance(source, dict):
        hashes = source.get("source_file_hashes")
        if isinstance(hashes, dict) and isinstance(hashes.get(source_path), str):
            return hashes[source_path]
    boundary = spec.get("c_boundary")
    if isinstance(boundary, dict) and isinstance(boundary.get("files"), list):
        for item in boundary["files"]:
            if isinstance(item, dict) and item.get("role") == "source" and item.get("path") == source_path:
                return item.get("sha256") if isinstance(item.get("sha256"), str) else None
    return None


def _spec_spans(spec: dict[str, Any], source_path: str) -> list[dict[str, Any]]:
    boundary = spec.get("c_boundary")
    signatures = boundary.get("signatures") if isinstance(boundary, dict) else None
    result: list[dict[str, Any]] = []
    if isinstance(signatures, list):
        for signature in signatures:
            span = signature.get("source_span") if isinstance(signature, dict) else None
            if isinstance(span, dict) and span.get("file") == source_path:
                result.append(span)
    return result


def _validate_item_shape(item: Any, index: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    label = f"items[{index}]"
    if not isinstance(item, dict):
        raise SuiteContractError(f"{label} must be an object")
    _expect_keys(
        item,
        {
            "id",
            "project_id",
            "slice_id",
            "provenance_kind",
            "construct_family",
            "slice_spec",
            "source_binding",
            "fixture",
            "fresh_executable",
        },
        label,
    )
    for key in ("id", "project_id", "slice_id", "construct_family"):
        _expect_string(item[key], f"{label}.{key}")
    provenance = item["provenance_kind"]
    if not isinstance(provenance, str) or provenance not in PROVENANCE_KINDS:
        raise SuiteContractError(f"{label}.provenance_kind is unsupported")
    if not isinstance(item["fresh_executable"], bool):
        raise SuiteContractError(f"{label}.fresh_executable must be boolean")
    if item["fresh_executable"] and provenance != "real_upstream_source_slice":
        raise SuiteContractError(f"{label} cannot declare synthetic or unbound provenance fresh-executable")

    spec_ref = item["slice_spec"]
    fixture = item["fixture"]
    source = item["source_binding"]
    if not isinstance(spec_ref, dict) or not isinstance(fixture, dict) or not isinstance(source, dict):
        raise SuiteContractError(f"{label} bindings must be objects")
    lowered = " ".join(
        (item["id"], item["project_id"], item["slice_id"], str(spec_ref.get("path", "")))
    ).lower()
    if "demo" in lowered:
        raise SuiteContractError(f"{label} cannot present demo provenance as a real project")
    _expect_keys(spec_ref, {"path", "sha256"}, f"{label}.slice_spec")
    _expect_keys(fixture, {"path", "sha256"}, f"{label}.fixture")
    _expect_keys(
        source,
        {"root", "path", "source_commit", "file_sha256", "span"},
        f"{label}.source_binding",
    )
    for binding, binding_label in ((spec_ref, "slice_spec"), (fixture, "fixture")):
        _expect_string(binding["path"], f"{label}.{binding_label}.path")
        if not isinstance(binding["sha256"], str) or not SHA256_RE.fullmatch(binding["sha256"]):
            raise SuiteContractError(f"{label}.{binding_label}.sha256 must be lowercase SHA-256")
    if not spec_ref["path"].startswith("validation/slice-specs/"):
        raise SuiteContractError(f"{label}.slice_spec.path must bind the repository slice-spec catalogue")
    _relative_parts(spec_ref["path"], f"{label}.slice_spec.path")
    _relative_parts(fixture["path"], f"{label}.fixture.path")
    _expect_nullable_string(source["root"], f"{label}.source_binding.root")
    _expect_string(source["path"], f"{label}.source_binding.path")
    if not _is_placeholder(source["root"]):
        _relative_parts(source["root"], f"{label}.source_binding.root")
    _relative_parts(source["path"], f"{label}.source_binding.path")
    commit = _expect_nullable_string(source["source_commit"], f"{label}.source_binding.source_commit")
    file_hash = _expect_nullable_string(source["file_sha256"], f"{label}.source_binding.file_sha256")
    if commit is not None and not COMMIT_RE.fullmatch(commit):
        raise SuiteContractError(f"{label}.source_binding.source_commit must be a pinned commit")
    if file_hash is not None and not SHA256_RE.fullmatch(file_hash):
        raise SuiteContractError(f"{label}.source_binding.file_sha256 must be lowercase SHA-256 or null")
    return item, _validate_span_shape(source["span"], f"{label}.source_binding.span")


def _preflight_item(item: dict[str, Any], span: dict[str, Any] | None, repo_root: Path) -> dict[str, Any]:
    reasons: list[str] = []
    spec_ref = item["slice_spec"]
    source_ref = item["source_binding"]
    fixture_ref = item["fixture"]
    spec_path = _safe_relative_path(repo_root, spec_ref["path"], f"{item['id']}.slice_spec.path")
    fixture_path = _safe_relative_path(repo_root, fixture_ref["path"], f"{item['id']}.fixture.path")

    spec: dict[str, Any] | None = None
    if not spec_path.is_file():
        reasons.append("slice_spec_missing")
    elif _sha256(spec_path) != spec_ref["sha256"]:
        reasons.append("slice_spec_sha256_mismatch")
    else:
        try:
            spec = _load_json(spec_path, f"slice spec {item['id']}")
        except SuiteContractError:
            reasons.append("slice_spec_invalid")

    if spec is not None:
        if spec.get("target_id") != item["project_id"]:
            reasons.append("slice_spec_project_mismatch")
        if spec.get("slice_id") != item["slice_id"]:
            reasons.append("slice_spec_id_mismatch")
        spec_source = spec.get("source")
        if not isinstance(spec_source, dict):
            reasons.append("slice_spec_source_missing")
        else:
            if spec_source.get("source_root") != source_ref["root"]:
                reasons.append("source_root_binding_mismatch")
            if spec_source.get("source_commit") != source_ref["source_commit"]:
                reasons.append("source_commit_binding_mismatch")
        if _spec_source_hash(spec, source_ref["path"]) != source_ref["file_sha256"]:
            reasons.append("source_file_hash_binding_mismatch")
        if span is not None:
            expected = {**span, "file": source_ref["path"]}
            if expected not in _spec_spans(spec, source_ref["path"]):
                reasons.append("source_span_binding_mismatch")
        fixture_contract = spec.get("fixture_contract")
        if not isinstance(fixture_contract, dict) or fixture_contract.get("path") != fixture_ref["path"]:
            reasons.append("fixture_binding_mismatch")

    if not fixture_path.is_file():
        reasons.append("fixture_missing")
    elif _sha256(fixture_path) != fixture_ref["sha256"]:
        reasons.append("fixture_sha256_mismatch")

    root_text = source_ref["root"]
    if _is_placeholder(root_text):
        reasons.append("source_root_not_pinned")
        source_root = None
    else:
        source_root = _safe_relative_path(repo_root, root_text, f"{item['id']}.source_binding.root")
        if not source_root.is_dir():
            reasons.append("source_root_missing")
            source_root = None

    if source_ref["source_commit"] is None:
        reasons.append("source_commit_missing")
    if source_ref["file_sha256"] is None:
        reasons.append("source_file_hash_missing")
    if span is None:
        reasons.append("source_span_missing")
    if not item["fresh_executable"]:
        reasons.append("fresh_execution_not_declared")

    if source_root is not None:
        source_path = _safe_relative_path(source_root, source_ref["path"], f"{item['id']}.source_binding.path")
        if not source_path.is_file():
            reasons.append("source_file_missing")
        else:
            if source_ref["file_sha256"] is not None and _sha256(source_path) != source_ref["file_sha256"]:
                reasons.append("source_file_sha256_mismatch")
            if span is not None:
                raw = source_path.read_bytes()
                if span["byte_end"] > len(raw):
                    reasons.append("source_span_out_of_bounds")
                elif hashlib.sha256(raw[span["byte_start"] : span["byte_end"]]).hexdigest() != span["sha256"]:
                    reasons.append("source_span_sha256_mismatch")

    deduped_reasons = list(dict.fromkeys(reasons))
    return {
        "id": item["id"],
        "project_id": item["project_id"],
        "slice_id": item["slice_id"],
        "construct_family": item["construct_family"],
        "provenance_kind": item["provenance_kind"],
        "fresh_executable": item["fresh_executable"],
        "status": "ready" if not deduped_reasons else "blocked",
        "blocked_reasons": deduped_reasons,
    }


def validate_suite(suite_path: Path | str, repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    path = Path(suite_path)
    if not path.is_absolute():
        path = root / path
    suite = _load_json(path, "AI finite cross-project suite")
    _validate_policy(suite)

    items = suite["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise SuiteContractError("suite.items must contain 1..20 entries")
    shaped = [_validate_item_shape(item, index) for index, item in enumerate(items)]
    ids = [item["id"] for item, _ in shaped]
    families = [item["construct_family"] for item, _ in shaped]
    projects = {item["project_id"] for item, _ in shaped}
    if len(ids) != len(set(ids)):
        raise SuiteContractError("suite item ids must be unique")
    if len(families) != len(set(families)):
        raise SuiteContractError("construct_family must be unique; duplicate families cannot inflate coverage")
    if len(families) < 10:
        raise SuiteContractError("suite must contain at least 10 distinct construct families")
    if len(projects) < 3 or not REQUIRED_PROJECTS.issubset(projects):
        raise SuiteContractError("suite must include real FlashDB, zlib-ng, and libuv entries")

    results = [_preflight_item(item, span, root) for item, span in shaped]
    ready = sum(item["status"] == "ready" for item in results)
    blocked = len(results) - ready
    provenance_counts = {
        kind: sum(item["provenance_kind"] == kind for item, _ in shaped)
        for kind in sorted(PROVENANCE_KINDS)
    }
    return {
        "schema_version": 1,
        "suite_id": suite["suite_id"],
        "contract_status": "passed",
        "status": "ready" if blocked == 0 else "blocked",
        "purpose": "preflight-only",
        "summary": {
            "items_total": len(results),
            "ready": ready,
            "blocked": blocked,
            "real_projects": len(projects),
            "construct_families": len(set(families)),
            "provenance_counts": provenance_counts,
            "model_invocations": 0,
            "translations_executed": 0,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        "items": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--require-all-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_suite(args.suite)
    except SuiteContractError as exc:
        print(json.dumps({"contract_status": "failed", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    if args.require_all_ready and report["status"] != "ready":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
