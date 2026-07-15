from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .rust_project_ir_source_lexer import (
    Token, after_balanced, identifier, require_balanced, rust_tokens,
)


SOURCE_INTERFACE_SECTIONS = {
    "cfg-feature-extraction",
    "global-ownership",
    "initialization-destruction",
    "nested-module-multi-target",
    "public-signature",
    "shared-type-layout",
}
_ITEM_KINDS = {
    "const": "constant",
    "enum": "enum",
    "fn": "function",
    "mod": "module",
    "static": "static",
    "struct": "struct",
    "trait": "trait",
    "type": "type-alias",
    "union": "union",
}
_QUALIFIERS = {"async", "default", "unsafe"}
_SAFE_ATTRIBUTES = {
    "allow", "cold", "deny", "deprecated", "doc", "export_name",
    "forbid", "ignore", "inline", "link_name", "must_use", "no_mangle",
    "should_panic", "test", "warn",
}
_ALL_SOURCE_UNRESOLVED = set(SOURCE_INTERFACE_SECTIONS)


def derive_candidate_source_facts(source: str) -> dict[str, Any]:
    """Extract only bounded, source-recomputable project-interface facts."""
    try:
        tokens = rust_tokens(source)
        require_balanced(tokens)
    except ValueError:
        return _result([], 0, 0, _ALL_SOURCE_UNRESOLVED)
    unresolved: set[str] = set()
    public_items: list[dict[str, str]] = []
    binary_entries = 0
    test_entries = 0
    pending_attributes: list[str] = []
    index = 0
    brace_depth = 0
    while index < len(tokens):
        token = tokens[index].text
        if token == "{":
            brace_depth += 1
            index += 1
            continue
        if token == "}":
            brace_depth -= 1
            index += 1
            continue
        if token == "#" and index + 1 < len(tokens) and tokens[index + 1].text == "[":
            end, name = _attribute(tokens, index)
            if name in {"cfg", "cfg_attr"}:
                unresolved.add("cfg-feature-extraction")
            if brace_depth == 0:
                if name not in _SAFE_ATTRIBUTES and name not in {"cfg", "cfg_attr"}:
                    unresolved.update(_ALL_SOURCE_UNRESOLVED)
                pending_attributes.append(name)
            index = end
            continue
        if token == "cfg" and _follows(tokens, index, "!"):
            unresolved.add("cfg-feature-extraction")
        if token == "static":
            unresolved.update({"global-ownership", "initialization-destruction"})
        if brace_depth != 0:
            index += 1
            continue
        item = _item(tokens, index)
        if item is None:
            if token != ";":
                unresolved.update(_ALL_SOURCE_UNRESOLVED)
            if token not in {"#", ";"}:
                pending_attributes.clear()
            index += 1
            continue
        start, kind_index, kind, public = item
        end, body = _item_header_end(tokens, kind_index)
        name = _item_name(tokens, kind_index, kind)
        signature = _signature(tokens[start:end])
        if public and start + 1 < len(tokens) and tokens[start + 1].text == "(":
            unresolved.add("public-signature")
        if kind == "fn" and name is not None:
            if name == "main" and _valid_main_signature(tokens[start:end]):
                binary_entries += 1
            if "test" in pending_attributes and _valid_test_signature(tokens, kind_index, end):
                test_entries += 1
        if public:
            if name is None or kind not in _ITEM_KINDS:
                unresolved.add("public-signature")
            else:
                public_items.append({
                    "symbol": name,
                    "kind": _ITEM_KINDS[kind],
                    "signature": signature,
                })
        _classify_item(kind, unresolved)
        pending_attributes.clear()
        index = _skip_body(tokens, body) if body is not None else end + 1
    symbols = [item["symbol"] for item in public_items]
    if len(symbols) != len(set(symbols)):
        unresolved.add("public-signature")
    if binary_entries > 1 or (binary_entries and test_entries):
        unresolved.add("nested-module-multi-target")
    return _result(public_items, binary_entries, test_entries, unresolved)


def derive_bound_candidate_source_facts(
    source: str, public_symbols: Sequence[str],
) -> dict[str, Any]:
    facts = derive_candidate_source_facts(source)
    observed = [item["symbol"] for item in facts["public_items"]]
    if observed == sorted(public_symbols):
        return facts
    unresolved = set(facts["unresolved_sections"])
    unresolved.add("public-signature")
    return _result(
        facts["public_items"], facts["binary_entry_count"],
        facts["test_entry_count"], unresolved,
    )


def project_bound_public_items(
    public_symbols: Sequence[str], source_facts: Mapping[str, Any],
) -> list[dict[str, str]]:
    by_symbol = {
        str(item["symbol"]): item for item in source_facts["public_items"]
    }
    return [{
        "symbol": symbol,
        "kind": str(by_symbol.get(symbol, {}).get("kind", "host-derived-item")),
        "signature": str(by_symbol.get(symbol, {}).get(
            "signature", "unresolved-before-compiler",
        )),
    } for symbol in sorted(public_symbols)]


def _result(
    public_items: Sequence[dict[str, str]], binary_entries: int,
    test_entries: int, unresolved: set[str],
) -> dict[str, Any]:
    ordered = sorted(public_items, key=lambda item: (item["symbol"], item["signature"]))
    missing = sorted(set(unresolved) & SOURCE_INTERFACE_SECTIONS)
    return {
        "status": "partial" if missing else "ready",
        "public_items": ordered,
        "binary_entry_count": binary_entries,
        "test_entry_count": test_entries,
        "verified_sections": sorted(SOURCE_INTERFACE_SECTIONS - set(missing)),
        "unresolved_sections": missing,
    }


def _classify_item(kind: str, unresolved: set[str]) -> None:
    if kind == "extern-block":
        unresolved.update(_ALL_SOURCE_UNRESOLVED)
        return
    if kind in {"struct", "enum", "union", "trait", "type", "impl"}:
        unresolved.add("shared-type-layout")
    if kind == "impl":
        unresolved.add("public-signature")
    if kind in {"static", "const"}:
        unresolved.update({"global-ownership", "initialization-destruction"})
    if kind in {"mod", "macro_rules", "macro"}:
        unresolved.add("nested-module-multi-target")
    if kind in {"impl", "extern-block"}:
        unresolved.add("initialization-destruction")


def _item(tokens: list[Token], index: int) -> tuple[int, int, str, bool] | None:
    start = index
    public = tokens[index].text == "pub"
    if public:
        index += 1
        if index < len(tokens) and tokens[index].text == "(":
            index = after_balanced(tokens, index, "(", ")")
    while index < len(tokens):
        if tokens[index].text in _QUALIFIERS:
            index += 1
            continue
        if (
            tokens[index].text == "const"
            and index + 1 < len(tokens)
            and tokens[index + 1].text == "fn"
        ):
            index += 1
            continue
        if tokens[index].text != "extern":
            break
        extern_index = index
        index += 1
        if index < len(tokens) and tokens[index].text.startswith(
            ('"', 'r"', 'r#', 'b"', 'c"')
        ):
            index += 1
        if index < len(tokens) and tokens[index].text == "fn":
            break
        if index < len(tokens) and tokens[index].text == "{":
            return start, extern_index, "extern-block", public
        return None
    if index >= len(tokens):
        return None
    kind = tokens[index].text
    if kind == "extern" and index + 1 < len(tokens) and tokens[index + 1].text == "{":
        kind = "extern-block"
    if kind not in {*_ITEM_KINDS, "impl", "extern-block", "macro", "macro_rules", "use"}:
        return None
    return start, index, kind, public


def _item_header_end(tokens: list[Token], kind_index: int) -> tuple[int, int | None]:
    paren = bracket = 0
    for index in range(kind_index + 1, len(tokens)):
        token = tokens[index].text
        if token == "(":
            paren += 1
        elif token == ")":
            paren -= 1
        elif token == "[":
            bracket += 1
        elif token == "]":
            bracket -= 1
        elif paren == 0 and bracket == 0 and token in {"{", ";"}:
            return index, index if token == "{" else None
    raise ValueError("unterminated Rust item")


def _skip_body(tokens: list[Token], index: int) -> int:
    return after_balanced(tokens, index, "{", "}")


def _item_name(tokens: list[Token], kind_index: int, kind: str) -> str | None:
    if kind not in _ITEM_KINDS or kind_index + 1 >= len(tokens):
        return None
    value = tokens[kind_index + 1].text
    return value if identifier(value) else None


def _signature(tokens: Sequence[Token]) -> str:
    value = " ".join(token.text for token in tokens)
    if not value or len(value) > 1_024:
        raise ValueError("Rust signature is outside its bound")
    return value


def _valid_main_signature(tokens: Sequence[Token]) -> bool:
    values = [token.text for token in tokens]
    if values and values[0] == "pub":
        values = values[1:]
        if values and values[0] == "(":
            return False
    return values == ["fn", "main", "(", ")"]


def _valid_test_signature(tokens: list[Token], kind_index: int, end: int) -> bool:
    values = [token.text for token in tokens[kind_index:end]]
    return len(values) >= 4 and values[0] == "fn" and values[2:4] == ["(", ")"]


def _attribute(tokens: list[Token], index: int) -> tuple[int, str]:
    end = after_balanced(tokens, index + 1, "[", "]")
    names = [token.text for token in tokens[index + 2:end - 1] if identifier(token.text)]
    return end, names[0] if names else ""


def _follows(tokens: list[Token], index: int, value: str) -> bool:
    return index + 1 < len(tokens) and tokens[index + 1].text == value


__all__ = [
    "SOURCE_INTERFACE_SECTIONS", "derive_bound_candidate_source_facts",
    "derive_candidate_source_facts", "project_bound_public_items",
]
