#!/usr/bin/env python3
"""Repository-level first-party unsafe budget scanner."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCOPES = [
    Path("crates/c2r-translator/src"),
    Path("flashDB_rust/src"),
    Path("validation/l2_slices/src"),
]
DEFAULT_LEDGER = Path("validation/unsafe-budget-ledger.json")
DEFAULT_CATEGORIES = {
    "unsafe_function": 0,
    "unsafe_block": 0,
    "unsafe_impl": 0,
    "extern_c": 0,
    "repr_c": 0,
    "transmute": 0,
    "raw_pointer": 0,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-ratio", type=float, default=0.10)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    ledger_path = args.ledger
    if ledger_path is None:
        default_ledger = repo_root / DEFAULT_LEDGER
        ledger_path = default_ledger if default_ledger.exists() else None
    elif not ledger_path.is_absolute():
        ledger_path = repo_root / ledger_path
    report = build_report(repo_root, ledger_path=ledger_path, max_ratio=args.max_ratio)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "passed" else 1


def build_report(
    repo_root: Path,
    *,
    ledger_path: Path | None = None,
    max_ratio: float = 0.10,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    ledger = load_ledger(repo_root, ledger_path)
    registered_keys = registered_finding_keys(ledger)
    findings: list[dict[str, Any]] = []
    scanned_files = 0
    scanned_lines = 0
    scopes = []

    for relative_scope in DEFAULT_SCOPES:
        scope_root = repo_root / relative_scope
        scope_files = 0
        scope_lines = 0
        if scope_root.exists():
            for path in sorted(scope_root.rglob("*.rs")):
                if should_ignore_path(path.relative_to(repo_root)):
                    continue
                scope_files += 1
                scanned_files += 1
                text = path.read_text(encoding="utf-8")
                for line_no, line in enumerate(text.splitlines(), start=1):
                    scope_lines += 1
                    scanned_lines += 1
                    for finding in unsafe_findings_in_line(path.relative_to(repo_root), line_no, line):
                        finding["registered"] = finding_key(finding) in registered_keys
                        findings.append(finding)
        scopes.append(
            {
                "path": relative_scope.as_posix(),
                "exists": scope_root.exists(),
                "scanned_files": scope_files,
                "scanned_lines": scope_lines,
            }
        )

    categories = dict(DEFAULT_CATEGORIES)
    for finding in findings:
        categories[finding["category"]] = categories.get(finding["category"], 0) + 1

    unsafe_count = len(findings)
    registered_count = sum(1 for finding in findings if finding["registered"])
    unregistered_count = unsafe_count - registered_count
    unsafe_ratio = 0.0 if scanned_lines == 0 else unsafe_count / scanned_lines
    failed_gates = []
    if unsafe_ratio > max_ratio:
        failed_gates.append("unsafe_ratio")
    if unregistered_count:
        failed_gates.append("unregistered_unsafe")

    return {
        "schema_version": 1,
        "status": "passed" if not failed_gates else "failed",
        "policy": "first-party non-test Rust unsafe budget",
        "scopes": scopes,
        "ignored_path_kinds": ["tests", "benches", "target", "generated", "bindings"],
        "max_first_party_non_test_ratio": max_ratio,
        "scanned_files": scanned_files,
        "scanned_lines": scanned_lines,
        "first_party_non_test_unsafe_count": unsafe_count,
        "registered_unsafe_count": registered_count,
        "unregistered_unsafe_count": unregistered_count,
        "unsafe_ratio": round(unsafe_ratio, 6),
        "registration_status": "passed" if unregistered_count == 0 else "failed",
        "failed_gates": failed_gates,
        "categories": categories,
        "ledger": ledger_ref(repo_root, ledger_path, ledger),
        "findings": findings,
    }


def load_ledger(repo_root: Path, ledger_path: Path | None) -> dict[str, Any]:
    if ledger_path is None or not ledger_path.exists():
        return {"schema_version": 1, "registered_findings": []}
    return json.loads(ledger_path.read_text(encoding="utf-8"))


def registered_finding_keys(ledger: dict[str, Any]) -> set[tuple[str, str]]:
    keys = set()
    for item in ledger.get("registered_findings", []):
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        category = item.get("category")
        if isinstance(path, str) and isinstance(category, str):
            keys.add((path.replace("\\", "/"), category))
    return keys


def ledger_ref(repo_root: Path, ledger_path: Path | None, ledger: dict[str, Any]) -> dict[str, Any]:
    if ledger_path is None:
        return {"path": None, "status": "missing", "registered_findings": 0}
    try:
        path = ledger_path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        path = ledger_path.as_posix()
    return {
        "path": path,
        "status": "loaded" if ledger_path.exists() else "missing",
        "registered_findings": len(ledger.get("registered_findings", [])),
    }


def should_ignore_path(relative_path: Path) -> bool:
    parts = set(relative_path.parts)
    if parts & {"tests", "benches", "target", "generated", "bindings"}:
        return True
    name = relative_path.name.lower()
    return name.endswith("_test.rs") or name.endswith(".generated.rs")


def unsafe_findings_in_line(relative_path: Path, line_no: int, line: str) -> list[dict[str, Any]]:
    raw_code = strip_line_comment(line)
    code = strip_string_literals(raw_code)
    findings: list[dict[str, Any]] = []

    def add(category: str) -> None:
        findings.append(
            {
                "path": relative_path.as_posix(),
                "line": line_no,
                "category": category,
                "text": line.strip(),
            }
        )

    if re.search(r"\bunsafe\s+fn\b", code):
        add("unsafe_function")
    if re.search(r"\bunsafe\s+impl\b", code):
        add("unsafe_impl")
    if re.search(r"\bunsafe\s*\{", code):
        add("unsafe_block")
    if re.search(r"\bextern\s+\"C\"", raw_code):
        add("extern_c")
    if "#[repr(C" in code or "#[repr( C" in code:
        add("repr_c")
    if re.search(r"\btransmute\s*(::|<|\()", code):
        add("transmute")
    if re.search(r"(\*\s*(const|mut)\b|\bas\s+\*\s*(const|mut)\b)", code):
        add("raw_pointer")
    return findings


def finding_key(finding: dict[str, Any]) -> tuple[str, str]:
    return (str(finding["path"]).replace("\\", "/"), str(finding["category"]))


def strip_line_comment(line: str) -> str:
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string and line[index : index + 2] == "//":
            return line[:index]
    return line


def strip_string_literals(line: str) -> str:
    output = []
    in_string = False
    escaped = False
    for char in line:
        if escaped:
            output.append(" ")
            escaped = False
            continue
        if char == "\\" and in_string:
            output.append(" ")
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            output.append(" ")
            continue
        output.append(" " if in_string else char)
    return "".join(output)


if __name__ == "__main__":
    sys.exit(main())
