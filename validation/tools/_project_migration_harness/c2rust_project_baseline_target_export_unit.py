from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Any, Mapping

from .artifacts import content_sha256
from .c2rust_project_baseline_exports import _no_mangle_exports
from .c2rust_project_baseline_rust_lexer import lex_rust, significant_indexes


def project_unit_export_inventory(
    unit_id: str, tree: Any, identity_value: Any,
) -> dict[str, Any]:
    if not _text(unit_id) or not isinstance(tree, Mapping) or not tree:
        _fail("generated_tree_invalid")
    identity = _json_value(identity_value)
    if not (_text(identity) or isinstance(identity, dict) and identity):
        _fail("unit_identity_invalid")
    declared = identity.get("unit_id") if isinstance(identity, dict) else None
    if declared is not None and declared != unit_id:
        _fail("unit_identity_invalid")
    identity_sha = content_sha256({"unit_id": unit_id, "identity": identity})
    files = []
    exports = []
    rust_file_count = 0
    for path, content in tree.items():
        normalized_path = _generated_path(path)
        data, source = _source_bytes(content, normalized_path.endswith(".rs"))
        digest = hashlib.sha256(data).hexdigest()
        files.append({
            "path": normalized_path, "sha256": digest,
            "size_bytes": len(data),
        })
        if source is None:
            continue
        rust_file_count += 1
        try:
            definitions = _no_mangle_exports(source)
        except ValueError as error:
            raise ValueError("c2rust_target_exports_rust_parse_invalid") from error
        for ordinal, item in enumerate(definitions):
            definition = {
                "symbol": item.symbol,
                "definition_kind": _definition_kind(source, item.end),
                "generated_path": normalized_path,
                "source_sha256": digest,
                "declaration_ordinal": ordinal,
                "unit_id": unit_id,
                "unit_identity_sha256": identity_sha,
            }
            exports.append({
                **definition,
                "definition_sha256": content_sha256(definition),
            })
    files.sort(key=lambda item: item["path"])
    exports.sort(key=lambda item: (item["symbol"], item["definition_sha256"]))
    tree_core = {
        "file_count": len(files), "rust_file_count": rust_file_count,
        "files": files,
    }
    return {
        "unit_id": unit_id,
        "unit_identity": identity,
        "unit_identity_sha256": identity_sha,
        "generated_tree": {
            **tree_core, "tree_sha256": content_sha256(tree_core),
        },
        "export_count": len(exports),
        "exports": exports,
    }


def baseline_unit_export_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("unit_id", "unit_key", "variant", "source", "object_target_id")
    if not isinstance(value, Mapping) or any(field not in value for field in fields):
        _fail("unit_identity_invalid")
    identity = {field: _json_value(value[field]) for field in fields}
    if not _text(identity["unit_id"]) or not _text(identity["unit_key"]):
        _fail("unit_identity_invalid")
    return identity


def _definition_kind(source: str, start: int) -> str:
    tokens = lex_rust(source[start:])
    significant = significant_indexes(tokens)
    for token_index in significant[:24]:
        text = tokens[token_index].text
        if text == "fn":
            return "function"
        if text == "static":
            return "static"
        if text in {";", "{"}:
            break
    _fail("rust_parser_drift")


def _json_value(value: Any) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            _fail("json_input_invalid")
        return {key: _json_value(value[key]) for key in sorted(value)}
    _fail("json_input_invalid")


def _generated_path(value: Any) -> str:
    if not _text(value) or "\\" in value:
        _fail("generated_path_invalid")
    path = PurePosixPath(value)
    if (
        not path.parts or path.is_absolute() or ".." in path.parts
        or path.parts[0].startswith("~") or ":" in path.parts[0]
        or path.as_posix() != value
    ):
        _fail("generated_path_invalid")
    return value


def _source_bytes(value: Any, rust_source: bool) -> tuple[bytes, str | None]:
    if isinstance(value, str):
        try:
            data = value.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("c2rust_target_exports_content_invalid") from error
        source = value if rust_source else None
    elif type(value) is bytes:
        data = value
        if rust_source:
            try:
                source = data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError(
                    "c2rust_target_exports_content_invalid"
                ) from error
        else:
            source = None
    else:
        _fail("content_invalid")
    if source is not None and "\0" in source:
        _fail("content_invalid")
    return data, source


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value


def _fail(code: str) -> None:
    raise ValueError(f"c2rust_target_exports_{code}")


__all__ = [
    "baseline_unit_export_identity", "project_unit_export_inventory",
]
