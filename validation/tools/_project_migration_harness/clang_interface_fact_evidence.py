"""Bounded, fail-closed extraction of top-level Clang AST interface facts."""
from __future__ import annotations
import hashlib, json, math, re
from collections.abc import Mapping
from typing import Any, NoReturn
MAX_AST_BYTES, MAX_AST_NODES, MAX_AST_DEPTH = 16 * 1024 * 1024, 100_000, 128
_SHA256, _IDENT = re.compile(r"[0-9a-f]{64}\Z"), re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_KINDS = {"FunctionDecl": "function", "VarDecl": "global", "RecordDecl": "record"}
_VOLATILE = {"id", "loc", "range", "previousDecl"}
class ClangInterfaceFactError(ValueError): """The input cannot support bounded facts."""
def build_clang_interface_fact_evidence(raw_ast: bytes, allowed_sources: Mapping[str, str],
    compile_context_sha256: str, target_abi_sha256: str) -> dict[str, Any]:
    """Parse source-bound declarations without making a closure claim."""
    sources = _sources(allowed_sources)
    compile_sha = _digest(compile_context_sha256, "compile_context_sha256_invalid")
    abi_sha = _digest(target_abi_sha256, "target_abi_sha256_invalid")
    root = _load(raw_ast)
    if root.get("kind") != "TranslationUnitDecl": _fail("translation_unit_required")
    inner = root.get("inner", [])
    if not isinstance(inner, list): _fail("translation_unit_inner_invalid")
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        "function": {}, "global": {}, "record": {}}
    blockers: list[dict[str, Any]] = []
    current_file: str | None = None
    source_map = {item["path"]: item["sha256"] for item in sources}
    for node in inner:
        if not isinstance(node, Mapping):
            blockers.append({"code": "top_level_node_invalid"})
            continue
        current_file = _file_hint(node) or current_file
        declaration_kind = node.get("kind")
        fact_kind = _KINDS.get(declaration_kind)
        if fact_kind is None: continue
        if any(node.get(key) not in (None, False) for key in ("isImplicit", "isInvalidDecl")):
            blockers.append(_block("implicit_or_invalid_declaration", str(declaration_kind), _subject(node))); continue
        subject = _subject(node)
        span, code = _span(node, current_file, source_map)
        if code:
            blockers.append(_block(code, str(declaration_kind), subject))
            continue
        fact, codes = _extract(fact_kind, node, span)
        blockers.extend(_block(item, str(declaration_kind), subject) for item in codes)
        if fact is not None: grouped[fact_kind].setdefault(fact["name"], []).append(fact)
    functions = _merge("function", grouped["function"], blockers)
    globals_ = _merge("global", grouped["global"], blockers)
    records = _merge("record", grouped["record"], blockers)
    report: dict[str, Any] = {
        "schema_version": 1, "status": "parsed_with_blockers" if blockers else "parsed",
        "parser": "clang_ast_top_level_interface_v1", "limits": {
            "max_bytes": MAX_AST_BYTES, "max_nodes": MAX_AST_NODES, "max_depth": MAX_AST_DEPTH},
        "input_bindings": {
            "raw_ast_sha256": hashlib.sha256(raw_ast).hexdigest(),
            "raw_ast_size_bytes": len(raw_ast), "allowed_source_set_sha256": _hash(sources),
            "allowed_sources": sources, "compile_context_sha256": compile_sha,
            "target_abi_sha256": abi_sha,
        },
        "functions": functions, "globals": globals_, "records": records,
        "initialization_facts": _initialization(functions, globals_),
        "blockers": _canonical_items(blockers), "section_closure": False,
        "semantic_gate": False, "translation_coverage_numerator": 0,
    }
    report["evidence_sha256"] = _hash(report)
    return report
def validate_clang_interface_fact_evidence(evidence: Mapping[str, Any], raw_ast: bytes,
    allowed_sources: Mapping[str, str], compile_context_sha256: str,
    target_abi_sha256: str) -> None:
    expected = build_clang_interface_fact_evidence(
        raw_ast, allowed_sources, compile_context_sha256, target_abi_sha256)
    try:
        matches = _canonical(dict(evidence)) == _canonical(expected)
    except (TypeError, ValueError):
        matches = False
    if not matches: _fail("interface_fact_evidence_mismatch")
def _load(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes: _fail("ast_bytes_required")
    if len(raw) > MAX_AST_BYTES: _fail("ast_byte_limit_exceeded")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result: _fail("ast_duplicate_key")
            if any(0xD800 <= ord(char) <= 0xDFFF for char in key): _fail("ast_unicode_scalar_invalid")
            result[key] = value
        return result
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda _value: _fail("ast_non_finite_number"))
    except UnicodeDecodeError as exc:
        raise ClangInterfaceFactError("ast_utf8_invalid") from exc
    except RecursionError as exc:
        raise ClangInterfaceFactError("ast_depth_limit_exceeded") from exc
    except json.JSONDecodeError as exc:
        raise ClangInterfaceFactError("ast_json_invalid") from exc
    if not isinstance(value, dict): _fail("ast_object_required")
    _bounded(value)
    return value
def _bounded(value: Any) -> None:
    stack, nodes = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        if depth > MAX_AST_DEPTH: _fail("ast_depth_limit_exceeded")
        if isinstance(item, Mapping):
            nodes += int(isinstance(item.get("kind"), str))
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item): _fail("ast_non_finite_number")
        elif isinstance(item, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in item): _fail("ast_unicode_scalar_invalid")
        if nodes > MAX_AST_NODES: _fail("ast_node_limit_exceeded")
def _sources(value: Mapping[str, str]) -> list[dict[str, str]]:
    if not isinstance(value, Mapping) or not value: _fail("allowed_sources_invalid")
    result = []
    for path, digest in value.items():
        invalid = (not isinstance(path, str) or not path or "\\" in path
                   or path.startswith("/") or ":" in path.split("/")[0]
                   or any(part in {"", ".", ".."} for part in path.split("/")))
        if invalid: _fail("allowed_source_path_invalid")
        result.append({"path": path,
                       "sha256": _digest(digest, "allowed_source_sha256_invalid")})
    return sorted(result, key=lambda item: item["path"])
def _file_hint(node: Mapping[str, Any]) -> str | None:
    locations = [node.get("loc")]
    range_ = node.get("range")
    if isinstance(range_, Mapping):
        locations += [range_.get("begin"), range_.get("end")]
    for location in locations:
        if isinstance(location, Mapping) and isinstance(location.get("file"), str):
            return str(location["file"])
    return None
def _span(node: Mapping[str, Any], inherited: str | None,
          sources: Mapping[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    range_, loc = node.get("range"), node.get("loc")
    if not isinstance(range_, Mapping) or not isinstance(loc, Mapping):
        return None, "source_location_unproven"
    begin, end = range_.get("begin"), range_.get("end")
    if not isinstance(begin, Mapping) or not isinstance(end, Mapping):
        return None, "source_location_unproven"
    locations = (loc, begin, end)
    if any("spellingLoc" in item or "expansionLoc" in item for item in locations):
        return None, "macro_source_location_unsupported"
    explicit = {item["file"] for item in locations if isinstance(item.get("file"), str)}
    if len(explicit) > 1: return None, "source_span_cross_file"
    path = next(iter(explicit), inherited)
    if path not in sources: return None, "source_path_not_allowed"
    start, finish, token = begin.get("offset"), end.get("offset"), end.get("tokLen")
    if not all(type(item) is int and item >= 0 for item in (start, finish, token)):
        return None, "source_offsets_unproven"
    finish += token
    if finish < start: return None, "source_span_invalid"
    return {"path": path, "sha256": sources[path],
            "byte_start": start, "byte_end": finish}, None
def _extract(kind: str, node: Mapping[str, Any],
             span: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    name = _subject(node)
    if name is None: return None, ["anonymous_declaration_unsupported"]
    linkage = _linkage(node) if kind != "record" else None
    if kind != "record" and linkage is None: return None, ["linkage_unproven"]
    if kind == "function":
        qual_type, inner = _qual_type(node), node.get("inner", [])
        if qual_type is None or not isinstance(inner, list):
            return None, ["function_type_unproven"]
        params = [_qual_type(item) for item in inner
                  if isinstance(item, Mapping) and item.get("kind") == "ParmVarDecl"]
        if any(item is None for item in params): return None, ["parameter_type_unproven"]
        variadic = node.get("variadic", False)
        if type(variadic) is not bool:
            return None, ["variadic_fact_unproven"]
        attrs = sorted({str(item["kind"]).removesuffix("Attr").lower()
                        for item in inner if isinstance(item, Mapping)
                        and item.get("kind") in {"ConstructorAttr", "DestructorAttr"}})
        return {"name": name, "linkage": linkage, "qual_type": qual_type,
                "parameter_types": params, "variadic": variadic,
                "initialization_attributes": attrs, "source_spans": [span]}, []
    if kind == "global":
        qual_type, tls = _qual_type(node), node.get("tls", "none")
        initializer, code = _initializer(node)
        if qual_type is None: return None, ["global_type_unproven"]
        if code: return None, [code]
        if tls not in {"none", "static", "dynamic"}: return None, ["tls_fact_unproven"]
        return {"name": name, "linkage": linkage, "qual_type": qual_type,
                "initializer": initializer, "tls": tls, "source_spans": [span]}, []
    tag, complete, inner = node.get("tagUsed"), node.get("completeDefinition", False), node.get("inner", [])
    if tag == "union": return None, ["union_record_unsupported"]
    if tag != "struct" or type(complete) is not bool:
        return None, ["record_tag_or_completeness_unproven"]
    if not isinstance(inner, list): return None, ["record_fields_unproven"]
    fields = []
    for field in (item for item in inner if isinstance(item, Mapping)
                  and item.get("kind") == "FieldDecl"):
        field_name, field_type = _subject(field), _qual_type(field)
        bitfield = field.get("isBitfield", False)
        if field_name is None or field_type is None or type(bitfield) is not bool:
            return None, ["record_fields_unproven"]
        fields.append({"name": field_name, "qual_type": field_type,
                       "bitfield": bitfield})
    if not complete and fields: return None, ["record_completeness_conflict"]
    return {"name": name, "tag": tag, "complete": complete,
            "fields": fields, "source_spans": [span]}, []
def _initializer(node: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    marker, inner = node.get("init"), node.get("inner", [])
    if not isinstance(inner, list): return None, "initializer_unproven"
    expressions = [item for item in inner if isinstance(item, Mapping)
                   and isinstance(item.get("kind"), str)
                   and not str(item["kind"]).endswith("Attr")]
    if marker is None: return (None, None) if not expressions else (None, "initializer_unproven")
    if not isinstance(marker, str) or not marker or len(expressions) != 1:
        return None, "initializer_unproven"
    expression = expressions[0]
    result = {"form": marker, "root_kind": expression["kind"],
              "semantic_sha256": _hash(_semantic(expression))}
    if isinstance(expression.get("value"), (str, int, bool)): result["value"] = expression["value"]
    return result, None
def _merge(kind: str, groups: Mapping[str, list[dict[str, Any]]],
           blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for name, declarations in sorted(groups.items()):
        spans = _canonical_items([span for item in declarations for span in item["source_spans"]])
        varying = {"source_spans"}
        varying |= ({"initialization_attributes"} if kind == "function" else
                    {"initializer"} if kind == "global" else {"complete", "fields"})
        bases = {_canonical({key: value for key, value in item.items() if key not in varying})
                 for item in declarations}
        if len(bases) != 1:
            blockers.append({"code": "declaration_conflict", "fact_kind": kind, "name": name})
            continue
        merged = {key: value for key, value in declarations[0].items() if key not in varying}
        if kind == "function":
            merged["initialization_attributes"] = sorted({attr for item in declarations
                                                            for attr in item["initialization_attributes"]})
        elif kind == "global":
            values = _canonical_items([item["initializer"] for item in declarations
                                       if item["initializer"] is not None])
            if len(values) > 1:
                blockers.append({"code": "declaration_conflict", "fact_kind": kind, "name": name})
                continue
            merged["initializer"] = values[0] if values else None
        else:
            definitions = _canonical_items([item["fields"] for item in declarations if item["complete"]])
            if len(definitions) > 1:
                blockers.append({"code": "declaration_conflict", "fact_kind": kind, "name": name})
                continue
            merged["complete"], merged["fields"] = bool(definitions), definitions[0] if definitions else []
            if not definitions:
                blockers.append({"code": "record_definition_missing", "fact_kind": kind, "name": name})
        merged["source_spans"] = spans
        result.append(merged)
    return result
def _initialization(functions: list[dict[str, Any]],
                    globals_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts = [{"kind": "global_initializer", "name": item["name"],
              "initializer": item["initializer"], "source_spans": item["source_spans"]}
             for item in globals_ if item["initializer"] is not None]
    for function in functions:
        facts += [{"kind": attr, "name": function["name"], "linkage": function["linkage"],
                   "source_spans": function["source_spans"]}
                  for attr in function["initialization_attributes"]]
    return sorted(facts, key=_canonical)

def _subject(node: Mapping[str, Any]) -> str | None:
    name = node.get("name"); return name if isinstance(name, str) and _IDENT.fullmatch(name) else None
def _qual_type(node: Mapping[str, Any]) -> str | None:
    type_ = node.get("type")
    value = type_.get("qualType") if isinstance(type_, Mapping) else None
    return " ".join(value.split()) if isinstance(value, str) and value.strip() else None

def _linkage(node: Mapping[str, Any]) -> str | None:
    storage = node.get("storageClass"); return "internal" if storage == "static" else "external" if storage in {None, "extern"} else None

def _semantic(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _semantic(item) for key, item in sorted(value.items())
                if key not in _VOLATILE and not key.endswith("Id")}
    return [_semantic(item) for item in value] if isinstance(value, list) else value

def _block(code: str, declaration_kind: str, name: str | None) -> dict[str, Any]:
    result = {"code": code, "declaration_kind": declaration_kind}
    if name is not None:
        result["name"] = name
    return result

def _canonical_items(items: list[Any]) -> list[Any]:
    return [json.loads(item) for item in sorted({_canonical(value) for value in items})]

def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None: _fail(code)
    return value

def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))

def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()

def _fail(code: str) -> NoReturn:
    raise ClangInterfaceFactError(code)

parse_clang_interface_fact_evidence = build_clang_interface_fact_evidence
__all__ = ["ClangInterfaceFactError", "MAX_AST_BYTES", "MAX_AST_DEPTH", "MAX_AST_NODES",
           "build_clang_interface_fact_evidence", "parse_clang_interface_fact_evidence",
           "validate_clang_interface_fact_evidence"]
