from __future__ import annotations

import ast
import base64
import hashlib
from pathlib import Path
from typing import Iterable


MAX_SOURCE_BYTES = 2 * 1024 * 1024
SCANNED_SUFFIXES = {".json", ".md", ".py", ".toml", ".yaml", ".yml"}


def scan_identity_dispatch(
    paths: Iterable[Path],
    forbidden_identities: Iterable[str],
) -> dict[str, object]:
    identities = sorted({value.casefold() for value in forbidden_identities if value.strip()})
    variants = _variants(identities)
    findings: list[dict[str, object]] = []
    scanned = 0
    for path in sorted({value.resolve() for value in paths}, key=lambda value: value.as_posix()):
        if not path.is_file() or path.suffix.casefold() not in SCANNED_SUFFIXES:
            continue
        scanned += 1
        try:
            data = path.read_bytes()
        except OSError:
            findings.append(_finding(path, 0, "source_unreadable", None))
            continue
        if len(data) > MAX_SOURCE_BYTES:
            findings.append(_finding(path, 0, "source_too_large", None))
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            findings.append(_finding(path, 0, "source_not_parseable_utf8", None))
            continue
        lowered = text.casefold()
        for variant, identity in variants.items():
            start = lowered.find(variant)
            if start >= 0:
                findings.append(_finding(
                    path, lowered.count("\n", 0, start) + 1,
                    "forbidden_identity_text", identity,
                ))
        if path.suffix.casefold() != ".py":
            continue
        try:
            tree = ast.parse(text, filename=path.name)
        except SyntaxError:
            findings.append(_finding(path, 0, "source_not_parseable_utf8_python", None))
            continue
        for node in ast.walk(tree):
            value = _constant_text(node)
            if value is None:
                continue
            for identity in identities:
                if identity in value.casefold():
                    findings.append(_finding(
                        path, getattr(node, "lineno", 0),
                        "forbidden_identity_constant_expression", identity,
                    ))
    unique: dict[tuple[object, object], dict[str, object]] = {}
    for item in findings:
        key = (item["file"], item["identity"] or item["reason"])
        previous = unique.get(key)
        if previous is None or item["reason"] == "forbidden_identity_constant_expression":
            unique[key] = item
    findings = sorted(
        unique.values(),
        key=lambda item: (
            str(item["file"]), int(item["line"]), str(item["reason"]),
            str(item["identity"] or ""),
        ),
    )
    return {
        "schema_version": 1,
        "status": "passed" if not findings else "failed",
        "files_scanned": scanned,
        "finding_count": len(findings),
        "findings": findings,
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "note": "Static identity scanning prevents known-project dispatch but does not prove semantic generality.",
        },
    }


def _finding(path: Path, line: int, reason: str, identity: str | None) -> dict[str, object]:
    return {
        "file": path.name,
        "line": line,
        "reason": reason,
        "identity": identity,
    }


def _constant_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return (
            node.value if isinstance(node.value, str)
            else node.value.decode("latin-1")
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _constant_text(node.left)
        right = _constant_text(node.right)
        return left + right if left is not None and right is not None else None
    if isinstance(node, ast.JoinedStr):
        values = [_constant_text(value) for value in node.values]
        return "".join(values) if all(value is not None for value in values) else None
    if isinstance(node, ast.FormattedValue):
        return _constant_text(node.value)
    return None


def _variants(identities: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for identity in identities:
        encoded = identity.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        for value in (
            identity,
            encoded.hex(),
            base64.b64encode(encoded).decode("ascii").casefold(),
            digest,
            digest[:16],
        ):
            result[value] = identity
    return result


__all__ = ["scan_identity_dispatch"]
