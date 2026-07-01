#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
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
