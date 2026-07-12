from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


MAX_FIXTURE_BYTES = 4 * 1024 * 1024


def _fixture_binding(spec: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    fixture_contract = spec.get("fixture_contract")
    if not isinstance(fixture_contract, dict):
        raise ValueError("fixture_contract is required")
    declared_cases = fixture_contract.get("cases")
    if not isinstance(declared_cases, list) or not declared_cases:
        raise ValueError("fixture_contract cases are required")
    explicit_cases = all(
        isinstance(item, dict)
        and isinstance(item.get("inputs"), dict)
        and isinstance(item.get("expected_outputs"), dict)
        for item in declared_cases
    )
    fixture_ref = fixture_contract.get("path") or fixture_contract.get("input")
    inline_cases = explicit_cases and (
        fixture_ref is None
        or all(item.get("input_ref") == "inline" for item in declared_cases)
    )
    if explicit_cases and not inline_cases:
        inline_cases = not _resolve_json_ref_path(fixture_ref, repo_root).is_file()
    if inline_cases:
        path = None
        payload = None
        data = json.dumps(
            {
                "cases": [
                    {
                        "id": item.get("id"),
                        "inputs": item["inputs"],
                        "expected_outputs": item["expected_outputs"],
                    }
                    for item in declared_cases
                ]
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    else:
        path, payload, data = _read_json_ref(fixture_ref, repo_root)
    cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(declared_cases):
        if not isinstance(raw_case, dict):
            raise ValueError("fixture case must be an object")
        case_id = str(raw_case.get("id") or f"case-{index}")
        input_ref = str(raw_case.get("input_ref") or f"cases[{index}]")
        case_index, input_section = (
            (index, None) if input_ref == "inline" else _case_ref_selector(input_ref)
        )
        input_payload = raw_case.get("inputs")
        if not isinstance(input_payload, dict):
            input_payload = _case_payload(payload, case_index, input_section)
        expected = raw_case.get("expected_outputs")
        if not isinstance(expected, dict) or not expected:
            expected_ref = raw_case.get("expected_ref") or fixture_ref
            _, expected_payload, _ = _read_json_ref(expected_ref, repo_root)
            expected = _case_payload(expected_payload, case_index)
            if isinstance(expected.get("expected_outputs"), dict):
                expected = expected["expected_outputs"]
        if not isinstance(input_payload, dict) or not isinstance(expected, dict):
            raise ValueError(f"fixture case {case_id} cannot be resolved")
        cases.append({"id": case_id, "inputs": input_payload, "expected": expected})
    return {
        "path": "inline" if path is None else path.relative_to(repo_root).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "cases": cases,
    }


def _read_json_ref(value: Any, repo_root: Path) -> tuple[Path, Any, bytes]:
    resolved = _resolve_json_ref_path(value, repo_root)
    if not resolved.is_file():
        raise ValueError("fixture reference is missing")
    data = resolved.read_bytes()
    if len(data) > MAX_FIXTURE_BYTES:
        raise ValueError("fixture reference is too large")
    try:
        return resolved, json.loads(data.decode("utf-8-sig")), data
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("fixture reference is not valid UTF-8 JSON") from exc


def _resolve_json_ref_path(value: Any, repo_root: Path) -> Path:
    if not isinstance(value, str) or not value or value == "inline":
        raise ValueError("fixture reference must be a repository-relative JSON path")
    path = Path(value.split("#", 1)[0])
    if path.is_absolute():
        raise ValueError("fixture reference must be repository-relative")
    unresolved = repo_root / path
    current = repo_root
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            current = current.parent
            continue
        current = current / part
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or is_junction():
            raise ValueError("fixture reference must not traverse symbolic links")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("fixture reference escapes repository root") from exc
    return resolved


def _case_ref_selector(value: str) -> tuple[int, str | None]:
    match = re.fullmatch(r"cases\[(\d+)\](?:\.(inputs|expected_outputs))?", value)
    if not match:
        raise ValueError(
            "fixture input_ref must use cases[n] with an optional bounded section"
        )
    return int(match.group(1)), match.group(2)


def _case_payload(
    payload: Any, index: int, section: str | None = None
) -> dict[str, Any]:
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if (
        not isinstance(cases, list)
        or index >= len(cases)
        or not isinstance(cases[index], dict)
    ):
        raise ValueError("fixture case reference is out of range")
    case = cases[index]
    if section is None:
        return case
    selected = case.get(section)
    if not isinstance(selected, dict):
        raise ValueError("fixture case section is missing")
    return selected
