"""Git, source, span, and item preflight for the finite project suite."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from validation.tools._ai_finite_cross_project_contract import (
    COMMIT_RE,
    FRESH_SOURCE_PROVENANCE_KINDS,
    PROVENANCE_KINDS,
    SHA256_RE,
    SuiteContractError,
    expect_keys,
    expect_nullable_string,
    expect_string,
    is_placeholder,
    load_json,
    matches_sha256,
    newline_variants,
    relative_parts,
    safe_relative_path,
    sha256,
    span_matches_variant,
    span_range_matches_variant,
)


GIT_TIMEOUT_SECONDS = 5
FRAGMENT_HASH_MODE = "normalized_line_span_with_newline"


def _run_git(checkout: Path, operation: str, *args: str) -> tuple[str | None, str | None]:
    env = os.environ.copy()
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(checkout), *args],
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return None, "project_source_git_unavailable"
    except subprocess.TimeoutExpired:
        return None, f"project_source_git_{operation}_timeout"
    except OSError:
        return None, f"project_source_git_{operation}_failed"
    if completed.returncode != 0:
        return None, f"project_source_git_{operation}_failed"
    return completed.stdout.strip(), None


def _normalize_repository_url(value: str) -> str:
    normalized = value.rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.rstrip("/")


def preflight_project_source(source: dict[str, str], repo_root: Path) -> list[str]:
    try:
        checkout = safe_relative_path(repo_root, source["root"], "project_sources.root")
    except OSError:
        return ["project_source_checkout_path_failed"]
    if not checkout.is_dir():
        return ["project_source_checkout_missing"]

    top_level, error = _run_git(checkout, "checkout", "rev-parse", "--show-toplevel")
    if error is not None:
        return [error]
    try:
        is_checkout_root = top_level is not None and Path(top_level).resolve() == checkout.resolve()
    except OSError:
        return ["project_source_checkout_path_failed"]
    if not is_checkout_root:
        return ["project_source_not_checkout_root"]

    reasons: list[str] = []
    head, error = _run_git(checkout, "head", "rev-parse", "HEAD")
    if error is not None:
        reasons.append(error)
    elif head != source["commit"]:
        reasons.append("project_source_head_mismatch")

    origin, error = _run_git(checkout, "origin", "remote", "get-url", "origin")
    if error is not None:
        reasons.append(error)
    elif origin is None or _normalize_repository_url(origin) != _normalize_repository_url(source["repository"]):
        reasons.append("project_source_repository_mismatch")

    status, error = _run_git(
        checkout,
        "status",
        "-c",
        "core.autocrlf=true",
        "status",
        "--porcelain=v1",
        "--untracked-files=no",
        "--ignore-submodules=none",
    )
    if error is not None:
        reasons.append(error)
    elif status:
        reasons.append("project_source_tracked_dirty")
    return reasons


def _validate_span_shape(span: Any, label: str) -> dict[str, Any] | None:
    if span is None:
        return None
    if not isinstance(span, dict):
        raise SuiteContractError(f"{label} must be an object or null")
    expect_keys(span, {"line_start", "line_end", "byte_start", "byte_end", "sha256"}, label)
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


def _spec_fragment_span(spec: dict[str, Any], source_path: str) -> dict[str, Any] | None:
    carrier = spec.get("translation_carrier")
    real_source = carrier.get("real_source") if isinstance(carrier, dict) else None
    if not isinstance(real_source, dict) or real_source.get("file") != source_path:
        return None
    fragment = real_source.get("fragment")
    if not isinstance(fragment, dict) or fragment.get("hash_mode") != FRAGMENT_HASH_MODE:
        return None
    extracted = {
        "line_start": fragment.get("line_start"),
        "line_end": fragment.get("line_end"),
        "sha256": fragment.get("sha256"),
    }
    if (
        not isinstance(extracted["line_start"], int)
        or extracted["line_start"] < 1
        or not isinstance(extracted["line_end"], int)
        or extracted["line_end"] < extracted["line_start"]
        or not isinstance(extracted["sha256"], str)
        or not SHA256_RE.fullmatch(extracted["sha256"])
    ):
        return None
    return extracted


def validate_item_shape(item: Any, index: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    label = f"items[{index}]"
    if not isinstance(item, dict):
        raise SuiteContractError(f"{label} must be an object")
    expect_keys(
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
        expect_string(item[key], f"{label}.{key}")
    provenance = item["provenance_kind"]
    if not isinstance(provenance, str) or provenance not in PROVENANCE_KINDS:
        raise SuiteContractError(f"{label}.provenance_kind is unsupported")
    if not isinstance(item["fresh_executable"], bool):
        raise SuiteContractError(f"{label}.fresh_executable must be boolean")
    if item["fresh_executable"] and provenance not in FRESH_SOURCE_PROVENANCE_KINDS:
        raise SuiteContractError(f"{label} cannot declare synthetic or unbound provenance fresh-executable")

    spec_ref = item["slice_spec"]
    fixture = item["fixture"]
    source = item["source_binding"]
    if not isinstance(spec_ref, dict) or not isinstance(fixture, dict) or not isinstance(source, dict):
        raise SuiteContractError(f"{label} bindings must be objects")
    lowered = " ".join((item["id"], item["project_id"], item["slice_id"], str(spec_ref.get("path", "")))).lower()
    if "demo" in lowered:
        raise SuiteContractError(f"{label} cannot present demo provenance as a real project")
    expect_keys(spec_ref, {"path", "sha256"}, f"{label}.slice_spec")
    expect_keys(fixture, {"path", "sha256"}, f"{label}.fixture")
    expect_keys(source, {"root", "path", "source_commit", "file_sha256", "span"}, f"{label}.source_binding")
    for binding, binding_label in ((spec_ref, "slice_spec"), (fixture, "fixture")):
        expect_string(binding["path"], f"{label}.{binding_label}.path")
        if not isinstance(binding["sha256"], str) or not SHA256_RE.fullmatch(binding["sha256"]):
            raise SuiteContractError(f"{label}.{binding_label}.sha256 must be lowercase SHA-256")
    if not spec_ref["path"].startswith("validation/slice-specs/"):
        raise SuiteContractError(f"{label}.slice_spec.path must bind the repository slice-spec catalogue")
    relative_parts(spec_ref["path"], f"{label}.slice_spec.path")
    relative_parts(fixture["path"], f"{label}.fixture.path")
    expect_nullable_string(source["root"], f"{label}.source_binding.root")
    expect_string(source["path"], f"{label}.source_binding.path")
    if not is_placeholder(source["root"]):
        relative_parts(source["root"], f"{label}.source_binding.root")
    relative_parts(source["path"], f"{label}.source_binding.path")
    commit = expect_nullable_string(source["source_commit"], f"{label}.source_binding.source_commit")
    file_hash = expect_nullable_string(source["file_sha256"], f"{label}.source_binding.file_sha256")
    if commit is not None and not COMMIT_RE.fullmatch(commit):
        raise SuiteContractError(f"{label}.source_binding.source_commit must be a pinned commit")
    if file_hash is not None and not SHA256_RE.fullmatch(file_hash):
        raise SuiteContractError(f"{label}.source_binding.file_sha256 must be lowercase SHA-256 or null")
    return item, _validate_span_shape(source["span"], f"{label}.source_binding.span")


def preflight_item(
    item: dict[str, Any],
    span: dict[str, Any] | None,
    repo_root: Path,
    project_sources: dict[str, dict[str, str]],
    project_source_reasons: dict[str, list[str]],
) -> dict[str, Any]:
    reasons: list[str] = []
    spec_ref = item["slice_spec"]
    source_ref = item["source_binding"]
    fixture_ref = item["fixture"]
    spec_path = safe_relative_path(repo_root, spec_ref["path"], f"{item['id']}.slice_spec.path")
    fixture_path = safe_relative_path(repo_root, fixture_ref["path"], f"{item['id']}.fixture.path")

    project_source = project_sources.get(item["project_id"])
    if project_source is None:
        reasons.append("project_source_registry_missing")
    else:
        if source_ref["root"] != project_source["root"]:
            reasons.append("project_source_root_binding_mismatch")
        if source_ref["source_commit"] != project_source["commit"]:
            reasons.append("project_source_commit_binding_mismatch")
        reasons.extend(project_source_reasons[item["project_id"]])

    spec: dict[str, Any] | None = None
    if not spec_path.is_file():
        reasons.append("slice_spec_missing")
    elif sha256(spec_path) != spec_ref["sha256"]:
        reasons.append("slice_spec_sha256_mismatch")
    else:
        try:
            spec = load_json(spec_path, f"slice spec {item['id']}")
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
            if item["provenance_kind"] == "real_upstream_source_fragment":
                expected_fragment = {
                    "line_start": span["line_start"],
                    "line_end": span["line_end"],
                    "sha256": span["sha256"],
                }
                if _spec_fragment_span(spec, source_ref["path"]) != expected_fragment:
                    reasons.append("source_span_binding_mismatch")
            else:
                expected = {**span, "file": source_ref["path"]}
                if expected not in _spec_spans(spec, source_ref["path"]):
                    reasons.append("source_span_binding_mismatch")
        fixture_contract = spec.get("fixture_contract")
        if not isinstance(fixture_contract, dict) or fixture_contract.get("path") != fixture_ref["path"]:
            reasons.append("fixture_binding_mismatch")

    if not fixture_path.is_file():
        reasons.append("fixture_missing")
    elif sha256(fixture_path) != fixture_ref["sha256"]:
        reasons.append("fixture_sha256_mismatch")

    root_text = source_ref["root"]
    if is_placeholder(root_text):
        reasons.append("source_root_not_pinned")
        source_root = None
    else:
        source_root = safe_relative_path(repo_root, root_text, f"{item['id']}.source_binding.root")
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
        source_path = safe_relative_path(source_root, source_ref["path"], f"{item['id']}.source_binding.path")
        if not source_path.is_file():
            reasons.append("source_file_missing")
        else:
            raw = source_path.read_bytes()
            variants = newline_variants(raw)
            if source_ref["file_sha256"] is not None and not any(
                matches_sha256(variant, source_ref["file_sha256"]) for variant in variants
            ):
                reasons.append("source_file_sha256_mismatch")
            if span is not None:
                if all(span["byte_end"] > len(variant) for variant in variants):
                    reasons.append("source_span_out_of_bounds")
                elif not any(span_range_matches_variant(variant, span) for variant in variants):
                    reasons.append("source_span_line_range_mismatch")
                elif not any(span_matches_variant(variant, span) for variant in variants):
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
