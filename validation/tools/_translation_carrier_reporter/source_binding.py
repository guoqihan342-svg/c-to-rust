from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import (
    ReporterError,
    behavior_fields,
    parse_contract,
    require_dict,
    require_nonempty_string,
    validate_cases,
)
from .field_add_contract import KIND as FIELD_ADD_KIND


@dataclass(frozen=True)
class StaticContext:
    repo_root: Path
    spec_path: Path
    fixture_path: Path
    source_path: Path
    spec: dict[str, Any]
    fixture: dict[str, Any]
    contract: dict[str, Any]
    cases: list[dict[str, Any]]
    claim_boundary: dict[str, Any]
    refs: dict[str, Any]


def load_static_context(spec_path: Path, repo_root: Path) -> StaticContext:
    root = repo_root.resolve(strict=True)
    resolved_spec = contained_file(root, spec_path, "slice spec")
    spec = load_json(resolved_spec)
    target_id = require_nonempty_string(spec.get("target_id"), "target_id")
    slice_id = safe_path_token(spec.get("slice_id"), "slice_id")
    source_commit = require_nonempty_string(spec.get("source_commit"), "source_commit")
    contract = parse_contract(spec)

    fixture_contract = require_dict(spec.get("fixture_contract"), "fixture_contract")
    fixture_path = contained_file(root, fixture_contract.get("path"), "fixture")
    fixture = load_json(fixture_path)
    fixture_sha = sha256_file(fixture_path)
    if fixture_contract.get("hash") != fixture_sha or spec.get("fixture_hash") != fixture_sha:
        raise ReporterError("fixture hash does not match slice spec")
    for key, expected in (
        ("target_id", target_id),
        ("slice_id", slice_id),
        ("source_commit", source_commit),
    ):
        if fixture.get(key) != expected:
            raise ReporterError(f"fixture {key} does not match slice spec")
    cases = validate_cases(fixture.get("cases"), contract)
    if fixture.get("case_count") != len(cases):
        raise ReporterError("fixture case_count drifted")
    fields = behavior_fields(contract)
    if fixture.get("compared_fields") != fields:
        raise ReporterError("fixture compared_fields do not match replay contract")
    if fixture_contract.get("behavior_fields") != fields:
        raise ReporterError("fixture_contract behavior_fields do not match replay contract")
    validate_declared_cases(fixture_contract.get("cases"), cases)

    carrier = require_dict(spec.get("translation_carrier"), "translation_carrier")
    claim_boundary = validate_carrier(spec, carrier, root, contract)
    source_root = contained_directory(root, spec.get("source_root"), "source_root")
    source_file = require_nonempty_string(spec.get("source_file"), "source_file")
    source_path = contained_file(source_root, source_file, "real source file")
    source_sha = sha256_file(source_path)
    source_hashes = spec.get("source_file_hashes")
    if not isinstance(source_hashes, dict) or source_hashes.get(source_file) != source_sha:
        raise ReporterError("real source file hash does not match slice spec")
    span_refs = validate_source_spans(source_path, source_file, spec["c_source"], carrier)

    refs = {
        "slice_spec": file_ref(root, resolved_spec),
        "fixture": file_ref(root, fixture_path),
        "real_source": {
            **file_ref(root, source_path),
            "artifact_lf_stable_sha256": sha256_lf_stable_text_file(source_path),
            **span_refs,
        },
        "translation_carrier": {
            "kind": carrier["kind"],
            "carrier_function": carrier["carrier_function"],
            "carrier_source_sha256": carrier["carrier_source_sha256"],
        },
    }
    return StaticContext(
        repo_root=root,
        spec_path=resolved_spec,
        fixture_path=fixture_path,
        source_path=source_path,
        spec=spec,
        fixture=fixture,
        contract=contract,
        cases=cases,
        claim_boundary=claim_boundary,
        refs=refs,
    )


def validate_carrier(
    spec: dict[str, Any],
    carrier: dict[str, Any],
    root: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    if carrier.get("kind") != "exact_source_fragment_wrapper":
        raise ReporterError("translation carrier kind is unsupported")
    if carrier.get("embedding_mode") != "verbatim_once":
        raise ReporterError("translation carrier must embed the source fragment once")
    if carrier.get("frontend_contract") != "live_clang_slice_source":
        raise ReporterError("translation carrier must use live clang slice source")
    if carrier.get("source_text_normalization") != "utf8_universal_newlines":
        raise ReporterError("translation carrier text normalization drifted")
    if carrier.get("source_file_hash_mode") != "raw_bytes":
        raise ReporterError("translation carrier source file hash mode drifted")
    if carrier.get("artifact_source_hash_mode") != "lf_stable_text":
        raise ReporterError("translation carrier artifact source hash mode drifted")
    if carrier.get("carrier_function") != spec.get("function_name"):
        raise ReporterError("translation carrier function does not match slice function")
    c_source = require_nonempty_string(spec.get("c_source"), "c_source")
    if carrier.get("carrier_source_sha256") != sha256_text(c_source):
        raise ReporterError("translation carrier source hash drifted")

    claim = require_dict(carrier.get("claim_boundary"), "translation carrier claim boundary")
    if claim.get("scope") != "source_fragment_only":
        raise ReporterError("translation carrier claim must be source_fragment_only")
    if claim.get("whole_function_semantics_verified") is not False:
        raise ReporterError("whole function semantics must remain unverified")
    if claim.get("external_callee_semantics_verified") is not False:
        raise ReporterError("external callee semantics must remain unverified")
    excluded = claim.get("excluded_semantics")
    if not isinstance(excluded, list) or not excluded:
        raise ReporterError("translation carrier excluded semantics must be declared")
    if contract.get("kind") == FIELD_ADD_KIND:
        validate_field_add_carrier_source(c_source, contract)
    else:
        external_name = str(contract["external_callee"]["name"])
        if f"{external_name}(" not in c_source:
            raise ReporterError("declared external callee is not present in carrier source")
    return claim


def validate_field_add_carrier_source(c_source: str, contract: dict[str, Any]) -> None:
    state = contract["state_output"]
    rhs = contract["rhs"]
    target_root = re.escape(str(state["parameter"]))
    target_field = re.escape(str(state["field_path"][0]))
    source_root = re.escape(str(rhs["parameter"]))
    pattern = re.compile(
        rf"\b{target_root}\s*->\s*{target_field}\s*\+=\s*([^;]+);"
    )
    matches = pattern.findall(c_source)
    if len(matches) != 1 or re.search(rf"\b{source_root}\b", matches[0]) is None:
        raise ReporterError(
            "carrier must contain one declared target wrapping-add expression bound to the source root"
        )


def validate_source_spans(
    source_path: Path,
    source_file: str,
    c_source: str,
    carrier: dict[str, Any],
) -> dict[str, Any]:
    real_source = require_dict(carrier.get("real_source"), "translation_carrier.real_source")
    if real_source.get("file") != source_file:
        raise ReporterError("translation carrier source file drifted")
    source_text = source_path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    function = require_dict(real_source.get("containing_function"), "containing function")
    fragment = require_dict(real_source.get("fragment"), "source fragment")
    function_text = span_text(source_text, function, "containing function", trim=True)
    fragment_text = span_text(source_text, fragment, "source fragment", trim=False)
    if not function_text.startswith(require_nonempty_string(function.get("declaration_text"), "declaration_text")):
        raise ReporterError("containing function declaration drifted")
    if fragment.get("text") != fragment_text:
        raise ReporterError("source fragment text drifted")
    if c_source.count(fragment_text) != 1:
        raise ReporterError("carrier must embed the source fragment exactly once")
    return {
        "containing_function_sha256": function["sha256"],
        "source_fragment_sha256": fragment["sha256"],
    }


def span_text(source_text: str, span: dict[str, Any], label: str, *, trim: bool) -> str:
    start = span.get("line_start")
    end = span.get("line_end")
    lines = source_text.splitlines(keepends=True)
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start or end > len(lines):
        raise ReporterError(f"{label} line range is invalid")
    expected_mode = "trimmed_normalized_span" if trim else "normalized_line_span_with_newline"
    if span.get("hash_mode") != expected_mode:
        raise ReporterError(f"{label} hash mode drifted")
    text = "".join(lines[start - 1 : end])
    if trim:
        text = text.strip()
    if span.get("sha256") != sha256_text(text):
        raise ReporterError(f"{label} hash drifted")
    return text


def validate_declared_cases(declared: Any, cases: list[dict[str, Any]]) -> None:
    if not isinstance(declared, list) or len(declared) != len(cases):
        raise ReporterError("fixture_contract case declarations drifted")
    for index, (binding, case) in enumerate(zip(declared, cases, strict=True)):
        item = require_dict(binding, f"fixture_contract.cases[{index}]")
        if item.get("id") != case.get("id") or item.get("expected_outputs") != case.get("expected_outputs"):
            raise ReporterError(f"fixture_contract case {index} does not bind the fixture")


def contained_file(root: Path, path_value: Any, label: str) -> Path:
    path = Path(require_nonempty_string(str(path_value) if path_value is not None else None, label))
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=True)
    ensure_contained(root, resolved, label)
    if not resolved.is_file():
        raise ReporterError(f"{label} is not a file")
    return resolved


def contained_directory(root: Path, path_value: Any, label: str) -> Path:
    path = Path(require_nonempty_string(str(path_value) if path_value is not None else None, label))
    candidate = path if path.is_absolute() else root / path
    resolved = candidate.resolve(strict=True)
    ensure_contained(root, resolved, label)
    if not resolved.is_dir():
        raise ReporterError(f"{label} is not a directory")
    return resolved


def ensure_contained(root: Path, path: Path, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ReporterError(f"{label} escapes repo root") from exc


def safe_path_token(value: Any, label: str) -> str:
    text = require_nonempty_string(value, label)
    if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in text):
        raise ReporterError(f"{label} is not a safe path token")
    return text


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return require_dict(value, str(path))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_lf_stable_text_file(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(content).hexdigest()


def file_ref(root: Path, path: Path) -> dict[str, Any]:
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
