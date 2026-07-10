#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLASSIFIERS = {
    "api_update": {"E0061", "E0277", "E0560", "E0599", "E0603"},
    "type_mismatch": {"E0282", "E0283", "E0308", "E0609"},
    "borrow_checker": {"E0382", "E0499", "E0502", "E0505", "E0597", "E0716"},
    "module_path": {"E0425", "E0432", "E0433", "E0583"},
}

BLOCKED_CONDITIONS = [
    "new first-party non-test unsafe",
    "public API change outside impact set",
    "C oracle contract change",
    "golden fixture outcome change",
    "accepted behavior-field difference",
    "new error category introduced by repair",
    "same root cause exceeds retry limit",
]

PATCH_PLAN_REQUIRED_FIELDS = [
    "id",
    "files",
    "spans",
    "reason",
    "expected_error_delta",
    "risk",
    "rollback_id",
    "forbidden_changes",
    "ai_used",
    "verification_commands",
]

DEFAULT_RETRY_LIMIT = 5
CRC32_REQUIRED_TYPE_ALIASES = ("size_t", "uint8_t", "uint32_t")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if not path.exists():
        return messages
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            messages.append(value)
    return messages


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"C2Rust baseline must be inside repository root: {path}") from exc


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _balanced_item_end(text: str, opening: int, opening_char: str, closing_char: str) -> int:
    depth = 0
    for index in range(opening, len(text)):
        char = text[index]
        if char == opening_char:
            depth += 1
        elif char == closing_char:
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError(f"unterminated C2Rust item starting at byte {opening}")


def _extract_crc32_static(text: str, name: str) -> tuple[str, int, int]:
    match = re.search(rf"(?m)^static mut {re.escape(name)}\s*:", text)
    if match is None:
        raise ValueError(f"C2Rust mutable static not found: {name}")
    equals = text.find("=", match.end())
    opening = text.find("[", equals + 1)
    if equals < 0 or opening < 0:
        raise ValueError(f"C2Rust mutable static initializer not found: {name}")
    closing = _balanced_item_end(text, opening, "[", "]")
    semicolon = text.find(";", closing)
    if semicolon < 0:
        raise ValueError(f"C2Rust mutable static terminator not found: {name}")
    end = semicolon + 1
    return text[match.start() : end], match.start(), end


def _extract_c2rust_function(text: str, function_name: str) -> tuple[str, int, int]:
    match = re.search(
        rf'(?m)^(?:#\[no_mangle\]\r?\n)?pub unsafe extern "C" fn {re.escape(function_name)}\s*\(',
        text,
    )
    if match is None:
        raise ValueError(f"C2Rust function not found: {function_name}")
    opening = text.find("{", match.end())
    if opening < 0:
        raise ValueError(f"C2Rust function body not found: {function_name}")
    end = _balanced_item_end(text, opening, "{", "}")
    return text[match.start() : end], match.start(), end


def _required_type_aliases(text: str) -> list[str]:
    aliases: list[str] = []
    for name in CRC32_REQUIRED_TYPE_ALIASES:
        match = re.search(rf"(?m)^pub type {re.escape(name)}\s*=\s*[^;]+;", text)
        if match is None:
            raise ValueError(f"C2Rust type alias not found: {name}")
        aliases.append(match.group(0))
    return aliases


def _table_initializer(static_item: str) -> str:
    equals = static_item.find("=")
    opening = static_item.find("[", equals + 1)
    closing = _balanced_item_end(static_item, opening, "[", "]")
    return static_item[opening:closing]


def scan_c2rust_crc32_unsafe_sites(
    rust: str,
    *,
    function_name: str = "fdb_calc_crc32",
    readonly_static: str = "crc32_table",
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    if re.search(rf"(?m)^static mut {re.escape(readonly_static)}\s*:", rust):
        findings.append(
            {
                "kind": "mutable_static",
                "symbol": readonly_static,
                "reason": "C2Rust emitted a mutable static for a read-only lookup table",
            }
        )
    raw_boundary = re.search(
        rf'pub unsafe extern "C" fn {re.escape(function_name)}\s*\((?P<parameters>.*?)\)\s*->',
        rust,
        re.DOTALL,
    )
    if raw_boundary is not None:
        parameters = raw_boundary.group("parameters")
        if "*const ::core::ffi::c_void" in parameters and re.search(r"\bsize\s*:\s*size_t\b", parameters):
            findings.append(
                {
                    "kind": "raw_pointer_len_boundary",
                    "symbol": function_name,
                    "reason": "C2Rust emitted an unsafe raw pointer plus length boundary",
                }
            )
    return {
        "scan_method": "bounded_c2rust_crc32_function_contract",
        "first_party_non_test_unsafe_count": len(findings),
        "findings": findings,
    }


def extract_c2rust_function_baseline(
    source_path: Path,
    *,
    function_name: str,
    readonly_static: str,
    repo_root: Path,
) -> dict[str, Any]:
    source_path = source_path.resolve()
    source = source_path.read_text(encoding="utf-8")
    static_item, static_start, static_end = _extract_crc32_static(source, readonly_static)
    function_item, function_start, function_end = _extract_c2rust_function(source, function_name)
    aliases = _required_type_aliases(source)
    rust = "\n".join([*aliases, "", static_item, "", function_item, ""])
    initializer = _table_initializer(static_item)
    return {
        "schema_version": 1,
        "candidate_source": "c2rust-function-level-baseline",
        "function_name": function_name,
        "readonly_static": readonly_static,
        "source": {
            "path": _repo_relative(source_path, repo_root),
            "sha256": sha256_file(source_path),
        },
        "source_spans": {
            "readonly_static": {
                "line_start": _line_number(source, static_start),
                "line_end": _line_number(source, static_end - 1),
            },
            "function": {
                "line_start": _line_number(source, function_start),
                "line_end": _line_number(source, function_end - 1),
            },
        },
        "dependencies": {
            "type_aliases": list(CRC32_REQUIRED_TYPE_ALIASES),
            "readonly_static": readonly_static,
        },
        "items": {
            "type_aliases": aliases,
            "readonly_static": static_item,
            "function": function_item,
        },
        "rust": rust,
        "rust_sha256": sha256_text(rust),
        "algorithm_invariants": {
            "table_initializer_sha256": sha256_text(initializer),
            "lookup_expression": "crc32_table[((crc ^ byte) & 0xff) as usize] ^ (crc >> 8)",
        },
        "unsafe_scan": scan_c2rust_crc32_unsafe_sites(
            rust,
            function_name=function_name,
            readonly_static=readonly_static,
        ),
        "semantic_pass": False,
    }


def _crc32_safe_function(function_item: str) -> str:
    initial_crc = re.search(r"(?m)^\s*(crc = crc \^ !\(0 as uint32_t\);)\s*$", function_item)
    lookup = re.search(
        r"(?ms)^\s*(crc = crc32_table\[\(\(crc \^ \*c2rust_fresh1 as uint32_t\).*?;)\s*$",
        function_item,
    )
    final_crc = re.search(r"(?m)^\s*(return crc \^ !\(0 as uint32_t\);)\s*$", function_item)
    if initial_crc is None or lookup is None or final_crc is None:
        raise ValueError("unsupported C2Rust fdb_calc_crc32 function shape")
    safe_lookup = lookup.group(1).replace("*c2rust_fresh1", "*byte")
    safe_lookup = "\n".join(f"        {line.strip()}" for line in safe_lookup.splitlines())
    return (
        "pub fn fdb_calc_crc32(mut crc: uint32_t, buf: &[uint8_t]) -> uint32_t {\n"
        f"    {initial_crc.group(1)}\n"
        "    for byte in buf {\n"
        f"{safe_lookup}\n"
        "    }\n"
        f"    {final_crc.group(1)}\n"
        "}"
    )


def transform_c2rust_crc32_baseline(extraction: dict[str, Any]) -> dict[str, Any]:
    if extraction.get("function_name") != "fdb_calc_crc32" or extraction.get("readonly_static") != "crc32_table":
        raise ValueError("only the bounded C2Rust fdb_calc_crc32 transform is supported")
    items = extraction.get("items")
    if not isinstance(items, dict):
        raise ValueError("C2Rust extraction items are missing")
    aliases = items.get("type_aliases")
    static_item = items.get("readonly_static")
    function_item = items.get("function")
    if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
        raise ValueError("C2Rust extraction type aliases are invalid")
    if not isinstance(static_item, str) or not isinstance(function_item, str):
        raise ValueError("C2Rust extraction function/static items are invalid")

    safe_static, replacement_count = re.subn(
        r"\bstatic mut crc32_table\b",
        "static crc32_table",
        static_item,
        count=1,
    )
    if replacement_count != 1:
        raise ValueError("C2Rust crc32_table mutable static transform did not match exactly once")
    safe_function = _crc32_safe_function(function_item)
    rust = "\n".join([*aliases, "", safe_static, "", safe_function, ""])
    unsafe_scan = scan_c2rust_crc32_unsafe_sites(rust)
    if unsafe_scan["first_party_non_test_unsafe_count"] != 0 or "unsafe" in rust:
        raise ValueError("C2Rust crc32 safety transform left unsafe code")

    source = extraction.get("source")
    if not isinstance(source, dict):
        raise ValueError("C2Rust extraction source provenance is missing")
    transformed_sha = sha256_text(rust)
    return {
        "schema_version": 1,
        "candidate_source": "c2rust-function-level-safety-transform",
        "source": dict(source),
        "baseline": {
            "sha256": extraction.get("rust_sha256"),
            "source_output": dict(source),
        },
        "rust": rust,
        "rust_sha256": transformed_sha,
        "algorithm_invariants": {
            "table_initializer_sha256": sha256_text(_table_initializer(safe_static)),
            "lookup_expression": extraction.get("algorithm_invariants", {}).get("lookup_expression"),
        },
        "unsafe_scan": unsafe_scan,
        "repair_round": {
            "round": 1,
            "status": "candidate_transformed",
            "input_baseline": {
                **dict(source),
                "function_level_sha256": extraction.get("rust_sha256"),
            },
            "changes": [
                {
                    "transform": "static_mut_to_immutable",
                    "symbol": "crc32_table",
                },
                {
                    "transform": "raw_pointer_len_to_slice",
                    "symbol": "fdb_calc_crc32",
                },
            ],
            "transformed_baseline_sha256": transformed_sha,
            "semantic_pass": False,
        },
        "semantic_pass": False,
    }


def rustc_code(message: dict[str, Any]) -> str | None:
    code = message.get("code")
    if isinstance(code, dict):
        value = code.get("code")
        if isinstance(value, str):
            return value
    return None


def root_cause_key(code: str | None) -> str:
    if not code:
        return "rustc_unknown"
    for key, codes in CLASSIFIERS.items():
        if code in codes:
            return key
    return f"rustc_{code.lower()}"


def span_payload(span: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": span.get("file_name"),
        "line_start": span.get("line_start"),
        "line_end": span.get("line_end"),
        "column_start": span.get("column_start"),
        "column_end": span.get("column_end"),
        "label": span.get("label"),
    }


def primary_span(spans: list[dict[str, Any]]) -> dict[str, Any] | None:
    for span in spans:
        if span.get("is_primary"):
            return span_payload(span)
    if spans:
        return span_payload(spans[0])
    return None


def suggested_replacements(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for span in spans:
        replacement = span.get("suggested_replacement")
        if replacement:
            payload = span_payload(span)
            payload["suggested_replacement"] = replacement
            payload["suggestion_applicability"] = span.get("suggestion_applicability")
            out.append(payload)
    return out


def rustc_error_events(
    messages: list[dict[str, Any]],
    *,
    command: str,
    cwd: str,
    slice_id: str,
    repo_commit: str,
    source_commit: str,
    input_hash: str,
    created_at: str,
    rerun_command: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message in messages:
        if message.get("reason") != "compiler-message":
            continue
        inner = message.get("message")
        if not isinstance(inner, dict) or inner.get("level") != "error":
            continue
        spans = inner.get("spans") if isinstance(inner.get("spans"), list) else []
        code = rustc_code(inner)
        primary = primary_span(spans)
        related = [span_payload(span) for span in spans if not span.get("is_primary")]
        affected_items = sorted(
            {
                span.get("file_name")
                for span in spans
                if isinstance(span.get("file_name"), str) and span.get("file_name")
            }
        )
        rows.append(
            {
                "event_id": f"rustc-{len(rows) + 1:06d}",
                "event_type": "rustc_error",
                "schema_version": 1,
                "slice_id": slice_id,
                "command": command,
                "cwd": cwd,
                "code": code,
                "primary_file": primary.get("file") if primary else None,
                "primary_span": primary,
                "related_spans": related,
                "rendered_message": inner.get("rendered") or inner.get("message"),
                "root_cause_key": root_cause_key(code),
                "affected_items": affected_items,
                "suggested_replacements": suggested_replacements(spans),
                "rerun_command": rerun_command,
                "source_commit": source_commit,
                "repo_commit": repo_commit,
                "input_hash": input_hash,
                "created_at": created_at,
            }
        )
    return rows


def policy_payload(args: argparse.Namespace, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "level": "L3",
        "target_id": "flashdb",
        "slice_id": args.slice_id,
        "status": "recorded",
        "created_at_utc": created_at,
        "rule_first_classifiers": {key: sorted(codes) for key, codes in CLASSIFIERS.items()},
        "retry_limit_per_root_cause": args.retry_limit,
        "rollback_id": args.rollback_id,
        "patch_plan_required_fields": PATCH_PLAN_REQUIRED_FIELDS,
        "blocked_conditions": BLOCKED_CONDITIONS,
        "rerun_order": [
            "cargo check --message-format=json",
            "targeted Rust tests",
            "cargo test",
            "replay/diff",
            "unsafe scan",
            "performance smoke",
        ],
        "automatic_patch_policy": {
            "rule_based_before_ai": True,
            "ai_candidates_require_patch_plan": True,
            "patch_files_must_be_in_impact_set": True,
            "semantic_diff_failure_cannot_be_fixed_by_weakening_tests": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--rust-check", required=True, type=Path)
    parser.add_argument("--error-events", required=True, type=Path)
    parser.add_argument("--patches", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--slice-id", default="kvdb-lifecycle")
    parser.add_argument("--repo-commit", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--rollback-id", required=True)
    parser.add_argument("--command", default="cargo check --message-format=json")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--retry-limit", default=DEFAULT_RETRY_LIMIT, type=int)
    args = parser.parse_args()

    created_at = utc_now()
    input_hash = sha256_file(args.input)
    messages = read_jsonl(args.input)
    errors = rustc_error_events(
        messages,
        command=args.command,
        cwd=args.cwd,
        slice_id=args.slice_id,
        repo_commit=args.repo_commit,
        source_commit=args.source_commit,
        input_hash=input_hash,
        created_at=created_at,
        rerun_command=args.command,
    )
    warnings = [
        value
        for value in messages
        if value.get("reason") == "compiler-message"
        and isinstance(value.get("message"), dict)
        and value["message"].get("level") == "warning"
    ]
    build_finished = next(
        (
            value
            for value in reversed(messages)
            if value.get("reason") == "build-finished"
        ),
        {},
    )
    status = "passed" if args.exit_code == 0 and not errors else "failed"
    report = {
        "schema_version": 1,
        "level": "L3",
        "target_id": "flashdb",
        "slice_id": args.slice_id,
        "status": status,
        "command": args.command,
        "cwd": args.cwd,
        "exit_code": args.exit_code,
        "repo_commit": args.repo_commit,
        "source_commit": args.source_commit,
        "input_path": str(args.input),
        "input_sha256": input_hash,
        "message_count": len(messages),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "build_success": build_finished.get("success"),
        "error_events_path": str(args.error_events),
        "patch_events_path": str(args.patches),
        "policy_path": str(args.policy),
        "automatic_patch_attempt_count": 0,
        "created_at_utc": created_at,
    }
    write_json(args.rust_check, report)
    write_jsonl(args.error_events, errors)
    write_jsonl(args.patches, [])
    write_json(args.policy, policy_payload(args, created_at))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
