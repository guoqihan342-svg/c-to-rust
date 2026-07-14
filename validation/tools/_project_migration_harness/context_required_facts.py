from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .context_contracts import canonical


REQUIRED_FACT_QUERY_POLICY = "host-required-symbol-facts-v1"
_UNRESOLVED_STATUS = "unresolved_external"
_SOURCE_FACT_KINDS = frozenset({
    "function_signature", "global_source", "header_source",
    "top_level_source",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def build_required_fact_query(
    scc_id: str,
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    requests: dict[tuple[str, str], set[str]] = {}
    for ref in refs:
        fact = facts.get(ref)
        if not isinstance(fact, Mapping):
            raise ValueError("required-fact query references a missing fact")
        kind = fact.get("kind")
        payload = fact.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("required-fact query payload is invalid")
        if kind == "external_call" and payload.get("status") == _UNRESOLVED_STATUS:
            _record_request(requests, "callable", payload.get("symbol"), ref)
        elif kind == "global_reference" and payload.get("status") == _UNRESOLVED_STATUS:
            _record_request(requests, "object", payload.get("symbol"), ref)
    records = [
        {
            "family": "symbol-declaration",
            "namespace": namespace,
            "symbol": symbol,
            "origin_fact_refs": sorted(origin_refs),
        }
        for (namespace, symbol), origin_refs in sorted(requests.items())
    ]
    payload = {
        "schema_version": 1,
        "policy": REQUIRED_FACT_QUERY_POLICY,
        "scc_id": scc_id,
        "requests": records,
    }
    return {
        **payload,
        "sha256": hashlib.sha256(canonical(payload)).hexdigest(),
    }


def required_fact_resolution(
    query: Mapping[str, Any],
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    requests = _validated_query(query)
    match_map = _matching_fact_map(requests, refs, facts)
    matches = []
    unresolved = []
    for request in requests:
        request_sha256 = hashlib.sha256(canonical(request)).hexdigest()
        fact_refs = sorted(match_map[(request["namespace"], request["symbol"])])
        match = {
            "request_sha256": request_sha256,
            "fact_refs": fact_refs,
        }
        matches.append(match)
        if not fact_refs:
            unresolved.append(request_sha256)
    match_set_sha256 = hashlib.sha256(canonical(matches)).hexdigest()
    unresolved_set_sha256 = hashlib.sha256(canonical(unresolved)).hexdigest()
    return {
        "required_fact_query_policy": REQUIRED_FACT_QUERY_POLICY,
        "required_fact_query_sha256": query.get("sha256"),
        "required_fact_query_count": len(matches),
        "required_fact_match_count": len(matches) - len(unresolved),
        "required_fact_match_set_sha256": match_set_sha256,
        "unresolved_required_fact_count": len(unresolved),
        "unresolved_required_fact_set_sha256": unresolved_set_sha256,
    }


def required_fact_binding_ready(value: Mapping[str, Any]) -> bool:
    query_count = value.get("required_fact_query_count")
    match_count = value.get("required_fact_match_count")
    unresolved_count = value.get("unresolved_required_fact_count")
    hashes = (
        value.get("required_fact_query_sha256"),
        value.get("required_fact_match_set_sha256"),
        value.get("unresolved_required_fact_set_sha256"),
    )
    return (
        value.get("required_fact_query_policy") == REQUIRED_FACT_QUERY_POLICY
        and all(isinstance(item, str) and _SHA256.fullmatch(item) for item in hashes)
        and all(
            isinstance(item, int) and not isinstance(item, bool) and item >= 0
            for item in (query_count, match_count, unresolved_count)
        )
        and query_count == match_count
        and unresolved_count == 0
    )


def _record_request(
    requests: dict[tuple[str, str], set[str]],
    namespace: str,
    symbol: Any,
    origin_ref: str,
) -> None:
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("required-fact symbol is invalid")
    requests.setdefault((namespace, symbol), set()).add(origin_ref)


def _validated_query(query: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if set(query) != {"schema_version", "policy", "scc_id", "requests", "sha256"}:
        raise ValueError("required-fact query shape is invalid")
    requests = query.get("requests")
    if (
        query.get("schema_version") != 1
        or query.get("policy") != REQUIRED_FACT_QUERY_POLICY
        or not isinstance(query.get("scc_id"), str)
        or not query["scc_id"]
        or not isinstance(requests, list)
    ):
        raise ValueError("required-fact query header is invalid")
    payload = {key: query[key] for key in (
        "schema_version", "policy", "scc_id", "requests",
    )}
    if query.get("sha256") != hashlib.sha256(canonical(payload)).hexdigest():
        raise ValueError("required-fact query SHA-256 drifted")
    keys = []
    for request in requests:
        if not isinstance(request, Mapping) or set(request) != {
            "family", "namespace", "symbol", "origin_fact_refs",
        }:
            raise ValueError("required-fact request shape is invalid")
        namespace = request.get("namespace")
        symbol = request.get("symbol")
        origins = request.get("origin_fact_refs")
        if (
            request.get("family") != "symbol-declaration"
            or namespace not in {"callable", "object"}
            or not isinstance(symbol, str) or not symbol
            or not isinstance(origins, list) or not origins
            or any(not isinstance(ref, str) or _SHA256.fullmatch(ref) is None
                   for ref in origins)
            or origins != sorted(set(origins))
        ):
            raise ValueError("required-fact request is invalid")
        keys.append((namespace, symbol))
    if keys != sorted(set(keys)):
        raise ValueError("required-fact requests are not canonical")
    return requests


def _matching_fact_map(
    requests: Sequence[Mapping[str, Any]],
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[tuple[str, str], set[str]]:
    result = {
        (str(request["namespace"]), str(request["symbol"])): set()
        for request in requests
    }
    by_symbol: dict[str, set[str]] = {}
    for namespace, symbol in result:
        by_symbol.setdefault(symbol, set()).add(namespace)
    query_symbols = set(by_symbol)
    for ref in sorted(set(refs)):
        fact = facts.get(ref)
        if not isinstance(fact, Mapping):
            raise ValueError("required-fact resolution references a missing fact")
        kind = fact.get("kind")
        payload = fact.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("required-fact resolution payload is invalid")
        structured_symbol = payload.get("symbol")
        if isinstance(structured_symbol, str) and structured_symbol in by_symbol:
            for namespace in by_symbol[structured_symbol]:
                if _structured_match(kind, payload, namespace, structured_symbol):
                    result[(namespace, structured_symbol)].add(ref)
        content = payload.get("content")
        if kind not in _SOURCE_FACT_KINDS or not isinstance(content, str):
            continue
        for symbol in set(_IDENTIFIER.findall(content)) & query_symbols:
            for namespace in by_symbol[symbol]:
                if _source_declaration_match(content, namespace, symbol):
                    result[(namespace, symbol)].add(ref)
    return result


def _structured_match(
    kind: Any, payload: Mapping[str, Any], namespace: str, symbol: str,
) -> bool:
    if payload.get("symbol") != symbol:
        return False
    if namespace == "callable":
        return kind == "function"
    return kind == "global"


def _source_declaration_match(
    content: str, namespace: str, symbol: str,
) -> bool:
    escaped = re.escape(symbol)
    if re.search(rf"(?m)^\s*#\s*define\s+{escaped}(?:\s|\()", content):
        return True
    declaration_prefix = (
        r"(?m)^\s*(?!(?:return|if|while|for|switch|sizeof)\b)"
        r"(?:(?:extern|static|inline|const|volatile|signed|unsigned|long|short)\s+)*"
        r"(?:struct\s+\w+|union\s+\w+|enum\s+\w+|[A-Za-z_]\w*)[\s*]+"
    )
    if namespace == "callable":
        return re.search(
            rf"{declaration_prefix}{escaped}\s*\([^;{{}}]*\)\s*(?:;|\{{)",
            content,
        ) is not None
    return re.search(
        rf"{declaration_prefix}[^;{{}}=]*\b{escaped}\b[^;{{}}]*;",
        content,
    ) is not None


__all__ = [
    "REQUIRED_FACT_QUERY_POLICY", "build_required_fact_query",
    "required_fact_binding_ready", "required_fact_resolution",
]
