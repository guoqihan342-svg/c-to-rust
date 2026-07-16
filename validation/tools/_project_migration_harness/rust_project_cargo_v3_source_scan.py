from __future__ import annotations

from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_source_facts import (
    _item, _item_header_end, _skip_body, _valid_main_signature,
    _valid_test_signature,
)
from .rust_project_ir_source_lexer import (
    Token, after_balanced, identifier, require_balanced, rust_tokens,
)


_NAMED_KINDS = {
    "fn", "static", "const", "type", "struct", "enum", "union", "trait",
    "mod",
}
_SAFE_ATTRIBUTES = {
    "allow", "cold", "deny", "deprecated", "doc", "export_name",
    "forbid", "ignore", "inline", "link", "link_name", "must_use",
    "no_mangle", "path", "repr", "should_panic", "test", "warn",
}


def scan_source_unit(
    unit_id: str, source_sha256: str, source: bytes,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reasons: dict[str, set[str]] = {}
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        _reason(reasons, "rust_source_invalid_utf8", source_sha256)
        return _finish(unit_id, source_sha256, len(source), [], 0, 0, False, reasons)
    try:
        tokens = rust_tokens(text)
        require_balanced(tokens)
    except ValueError as error:
        _reason(reasons, "rust_source_parse_failed", str(error))
        return _finish(unit_id, source_sha256, len(source), [], 0, 0, False, reasons)
    names: list[str] = []
    binary_entries = test_entries = main_declarations = 0
    main_cfg_guarded = crate_cfg = False
    attributes: list[str] = []
    index = 0
    try:
        while index < len(tokens):
            if tokens[index].text == "#":
                index, name, inner = _attribute(tokens, index)
                if name == "cfg_attr":
                    _reason(reasons, "rust_source_cfg_attr_unresolved", name)
                elif name not in _SAFE_ATTRIBUTES | {"cfg", "cfg_attr"}:
                    code = (
                        "rust_source_macro_expansion_required"
                        if name == "derive" else "rust_source_unsupported_attribute"
                    )
                    _reason(reasons, code, name or "unnamed")
                if inner:
                    crate_cfg = crate_cfg or name in {"cfg", "cfg_attr"}
                else:
                    attributes.append(name)
                continue
            if tokens[index].text == ";":
                if attributes:
                    raise ValueError("attribute is not attached to an item")
                index += 1
                continue
            bang = _macro_bang(tokens, index)
            if bang is not None:
                _reason(
                    reasons, "rust_source_macro_expansion_required",
                    " ".join(token.text for token in tokens[index:bang + 1]),
                )
                index = _skip_macro(tokens, index, bang)
                attributes.clear()
                continue
            item = _item(tokens, index)
            if item is None:
                raise ValueError("top-level item kind is unresolved")
            start, kind_index, kind, _ = item
            delimiter, body = _item_header_end(tokens, kind_index)
            next_index = _skip_body(tokens, body) if body is not None else delimiter + 1
            name = _item_name(tokens, kind_index, kind)
            if kind in _NAMED_KINDS:
                if name is None:
                    raise ValueError(f"{kind} item name is unresolved")
                names.append(name)
            if kind in {"macro", "macro_rules"}:
                _reason(reasons, "rust_source_macro_expansion_required", "macro-item")
            if kind == "mod" and tokens[delimiter].text == ";":
                _reason(reasons, "rust_source_external_module_unresolved", name or "mod")
            if kind == "fn" and name == "main":
                main_declarations += 1
                guarded = crate_cfg or bool({"cfg", "cfg_attr"} & set(attributes))
                main_cfg_guarded = main_cfg_guarded or guarded
                header = [token.text for token in tokens[kind_index:delimiter]]
                if _valid_main_signature(tokens[start:delimiter]):
                    binary_entries += 1
                else:
                    _reason(
                        reasons, "rust_project_cargo_main_signature_unresolved",
                        " ".join(header),
                    )
            if "test" in attributes:
                header = [token.text for token in tokens[kind_index:delimiter]]
                if kind == "fn" and _valid_test_signature(tokens, kind_index, delimiter):
                    test_entries += 1
                else:
                    _reason(
                        reasons, "rust_project_cargo_test_signature_unresolved",
                        " ".join(header),
                    )
            attributes.clear()
            index = next_index
        if attributes:
            raise ValueError("attribute is not attached to an item")
    except ValueError as error:
        _reason(reasons, "rust_source_parse_ambiguity", str(error))
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        _reason(reasons, "rust_project_cargo_top_level_name_collision", *duplicates)
    if main_declarations > 1:
        _reason(reasons, "rust_project_cargo_multiple_main_entries", str(main_declarations))
    if main_cfg_guarded:
        _reason(reasons, "rust_project_cargo_main_cfg_unresolved", "main")
    if binary_entries and test_entries:
        _reason(
            reasons, "rust_project_cargo_main_test_entries_mixed",
            f"{binary_entries}:{test_entries}",
        )
    return _finish(
        unit_id, source_sha256, len(source), names, binary_entries, test_entries,
        main_cfg_guarded, reasons,
    )


def _finish(unit_id, digest, size, names, binaries, tests, guarded, reasons):
    unresolved = sorted(reasons)
    unit = {
        "unit_id": unit_id, "source_sha256": digest, "size_bytes": size,
        "top_level_names": sorted(set(names)), "binary_entry_count": binaries,
        "test_entry_count": tests, "main_cfg_guarded": guarded,
        "unresolved_reasons": unresolved,
    }
    blockers = [{
        "code": code, "unit_id": unit_id,
        "detail_sha256": content_sha256({
            "code": code, "details": sorted(reasons[code]),
        }),
    } for code in unresolved]
    return unit, blockers


def _attribute(tokens: list[Token], index: int) -> tuple[int, str, bool]:
    inner = index + 1 < len(tokens) and tokens[index + 1].text == "!"
    opening = index + 2 if inner else index + 1
    if opening >= len(tokens) or tokens[opening].text != "[":
        raise ValueError("attribute delimiter is unresolved")
    end = after_balanced(tokens, opening, "[", "]")
    names = [
        token.text for token in tokens[opening + 1:end - 1]
        if identifier(token.text)
    ]
    return end, names[0] if names else "", inner


def _item_name(tokens: list[Token], index: int, kind: str) -> str | None:
    if kind not in _NAMED_KINDS:
        return None
    index += 1
    if kind == "static" and index < len(tokens) and tokens[index].text == "mut":
        index += 1
    if index >= len(tokens) or tokens[index].text == "_":
        return None
    return tokens[index].text if identifier(tokens[index].text) else None


def _macro_bang(tokens: list[Token], index: int) -> int | None:
    if not identifier(tokens[index].text):
        return None
    cursor = index
    while (
        cursor + 2 < len(tokens) and tokens[cursor + 1].text == "::"
        and identifier(tokens[cursor + 2].text)
    ):
        cursor += 2
    if cursor + 1 < len(tokens) and tokens[cursor + 1].text == "!":
        return cursor + 1
    return None


def _skip_macro(tokens: list[Token], start: int, bang: int) -> int:
    cursor = bang + 1
    if tokens[start].text == "macro_rules" and cursor < len(tokens):
        cursor += 1
    if cursor >= len(tokens) or tokens[cursor].text not in {"(", "[", "{"}:
        raise ValueError("macro delimiter is unresolved")
    closing = {"(": ")", "[": "]", "{": "}"}[tokens[cursor].text]
    cursor = after_balanced(tokens, cursor, tokens[cursor].text, closing)
    return cursor + 1 if cursor < len(tokens) and tokens[cursor].text == ";" else cursor


def _reason(values: dict[str, set[str]], code: str, *details: str) -> None:
    values.setdefault(code, set()).update(details or {"unresolved"})


__all__ = ["scan_source_unit"]
