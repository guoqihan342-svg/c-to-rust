from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .context_contracts import canonical
from .context_retrieval import DEFERRED_FACT_KINDS, validate_retrieval_bundle
from .gate_diagnostics import normalize_gate_evidence

_KIND = "context-frontier-wave-selection-directives"
_POLICY = "host-context-frontier-wave-selection-v1"
_CLAIM = {"semantic_gate": False, "translation_coverage_numerator": 0}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIRECTIVE_KEYS = {
    "schema_version", "artifact_kind", "policy", "run_id", "unit_id",
    "wave_index", "status", "selection_ready", "requires_host_recompute",
    "input_bindings", "selection_constraints",
    "selection_constraint_set_sha256", "allowed_deferred_fact_refs",
    "allowed_deferred_fact_set_sha256", "required_interface_fact_refs",
    "required_interface_fact_set_sha256", "host_failure_facts",
    "host_failure_fact_set_sha256", "claim_boundary", "sha256",
}
_INPUT_KEYS = {
    "wave_selection_seed_sha256", "context_bundle_sha256",
    "expansion_query_sha256", "failure_evidence_set_sha256",
    "failed_verifier_evidence_index_sha256",
}
_HOST_PAYLOAD_KEYS = {
    "consumer_unit_id", "source_unit_id", "gate_family",
    "candidate_artifact_id", "candidate_sha256", "candidate_set_sha256",
    "failure_evidence_sha256", "diagnostics", "withheld_fields",
    "model_input_safe",
}
_INTERFACE_KINDS = {
    "function", "source_binding", "function_signature", "parser_boundary",
}

def validate_context_frontier_wave_selection(
    directives: Mapping[str, Any], *,
    directives_reference: Mapping[str, Any],
    context_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(directives, Mapping) or set(directives) != _DIRECTIVE_KEYS:
        raise ValueError("wave selection directives schema is invalid")
    result = dict(directives)
    _header(result)
    facts, visible, omitted = _context_scope(context_bundle, result["unit_id"])
    constraints, allowed_by_constraints, interfaces_by_constraints, failures = (
        _constraints(result.get("selection_constraints"), facts, visible, omitted, result["unit_id"])
    )
    inputs = _inputs(result.get("input_bindings"), constraints, failures)
    if inputs["context_bundle_sha256"] != content_sha256(context_bundle):
        raise ValueError("wave selection context bundle hash drifted")
    if result.get("selection_constraint_set_sha256") != content_sha256(constraints):
        raise ValueError("wave selection constraint set hash drifted")
    allowed = _sha_list(result.get("allowed_deferred_fact_refs"), "allowed refs")
    interfaces = _sha_list(
        result.get("required_interface_fact_refs"), "interface refs",
    )
    if allowed != sorted(allowed_by_constraints):
        raise ValueError("wave selection allowed refs do not match constraints")
    if interfaces != sorted(interfaces_by_constraints):
        raise ValueError("wave selection interface refs do not match constraints")
    if any(ref not in omitted or facts[ref]["kind"] not in DEFERRED_FACT_KINDS
           for ref in allowed):
        raise ValueError("wave selection allowed ref scope drifted")
    if any(ref not in visible or facts[ref]["kind"] not in _INTERFACE_KINDS
           for ref in interfaces):
        raise ValueError("wave selection interface ref scope drifted")
    if result.get("allowed_deferred_fact_set_sha256") != content_sha256(allowed):
        raise ValueError("wave selection allowed ref set hash drifted")
    if result.get("required_interface_fact_set_sha256") != content_sha256(interfaces):
        raise ValueError("wave selection interface ref set hash drifted")
    hosts = _host_facts(result.get("host_failure_facts"), result["unit_id"], failures)
    if result.get("host_failure_fact_set_sha256") != content_sha256(hosts):
        raise ValueError("wave selection host fact set hash drifted")
    payload = {key: value for key, value in result.items() if key != "sha256"}
    if result.get("sha256") != content_sha256(payload):
        raise ValueError("wave selection directives hash drifted")
    _cas_reference(directives_reference, result)
    return result
def _header(value: Mapping[str, Any]) -> None:
    if (
        type(value.get("schema_version")) is not int or value.get("schema_version") != 1
        or value.get("artifact_kind") != _KIND
        or value.get("policy") != _POLICY
        or not _text(value.get("run_id"))
        or not _text(value.get("unit_id"))
        or not _count(value.get("wave_index"))
        or value.get("status") != "bounded_selection_directives"
        or value.get("selection_ready") is not False
        or value.get("requires_host_recompute") is not True
        or not _claim(value.get("claim_boundary"))
        or not _sha(value.get("sha256"))
    ):
        raise ValueError("wave selection directives header is invalid")
def _claim(value: Any) -> bool:
    return (isinstance(value, Mapping) and set(value) == set(_CLAIM)
            and value.get("semantic_gate") is False
            and type(value.get("translation_coverage_numerator")) is int
            and value.get("translation_coverage_numerator") == 0)
def _inputs(value: Any, constraints: list[dict[str, Any]], failures: dict[str, str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _INPUT_KEYS:
        raise ValueError("wave selection input bindings are invalid")
    result = dict(value)
    for key in _INPUT_KEYS - {"expansion_query_sha256"}:
        if not _sha(result.get(key)):
            raise ValueError("wave selection input hash is invalid")
    query = result.get("expansion_query_sha256")
    if query is not None and not _sha(query):
        raise ValueError("wave selection expansion query hash is invalid")
    if (query is None) != (not constraints):
        raise ValueError("wave selection expansion query binding drifted")
    empty = content_sha256([])
    if ((result["failure_evidence_set_sha256"] == empty)
            != (result["failed_verifier_evidence_index_sha256"] == empty)):
        raise ValueError("wave selection failure input hashes drifted")
    if failures and result["failure_evidence_set_sha256"] == empty:
        raise ValueError("wave selection failure constraint is unbound")
    return result
def _constraints(
    value: Any, facts: Mapping[str, Mapping[str, Any]],
    visible: set[str], omitted: set[str], unit_id: str,
) -> tuple[list[dict[str, Any]], set[str], set[str], dict[str, str]]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("wave selection constraints are invalid")
    result: list[dict[str, Any]] = []
    allowed: set[str] = set()
    interfaces: set[str] = set()
    failures: dict[str, str] = {}
    request_hashes: set[str] = set()
    direct_dependencies = {
        str(facts[ref]["payload"].get("dependency_scc_id"))
        for ref in visible
        if facts[ref]["kind"] == "scc_dependency"
        and facts[ref]["payload"].get("scc_id") == unit_id
    }
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("wave selection constraint is invalid")
        family = raw.get("family")
        if family == "include-adjacency":
            refs = _sha_list(raw.get("allowed_deferred_fact_refs"), "constraint allowed refs")
            anchor = _digest(raw.get("anchor_fact_sha256"), "include anchor")
            if anchor not in visible | omitted or facts[anchor]["kind"] != "include_binding":
                raise ValueError("wave selection include anchor scope drifted")
            request = {"family": family, "anchor_fact_sha256": anchor}
            normalized = {"family": family, "request_sha256": content_sha256(request),
                          "anchor_fact_sha256": anchor, "allowed_deferred_fact_refs": refs}
            allowed.update(refs)
        elif family == "dependency-scc-interface":
            refs = _sha_list(raw.get("required_interface_fact_refs"), "constraint interface refs")
            dependency = raw.get("dependency_scc_id")
            if not _text(dependency) or dependency not in direct_dependencies:
                raise ValueError("wave selection dependency scope drifted")
            request = {"family": family, "dependency_scc_id": dependency}
            normalized = {"family": family, "request_sha256": content_sha256(request),
                          "dependency_scc_id": dependency, "required_interface_fact_refs": refs}
            interfaces.update(refs)
        elif family == "verified-failure-fact":
            evidence = _digest(raw.get("failure_evidence_sha256"), "failure evidence")
            host = _digest(raw.get("host_failure_fact_sha256"), "host failure fact")
            request = {"family": family, "failure_evidence_sha256": evidence}
            normalized = {"family": family, "request_sha256": content_sha256(request),
                          "failure_evidence_sha256": evidence,
                          "host_failure_fact_sha256": host}
            if host in failures and failures[host] != evidence:
                raise ValueError("wave selection host failure identity is ambiguous")
            failures[host] = evidence
        else:
            raise ValueError("wave selection constraint family is invalid")
        if dict(raw) != normalized or normalized["request_sha256"] in request_hashes:
            raise ValueError("wave selection constraint binding drifted")
        request_hashes.add(normalized["request_sha256"])
        result.append(normalized)
    if result != sorted(result, key=lambda item: (item["family"], item["request_sha256"])):
        raise ValueError("wave selection constraints are not canonical")
    return result, allowed, interfaces, failures
def _context_scope(
    value: Any, unit_id: str,
) -> tuple[dict[str, Mapping[str, Any]], set[str], set[str]]:
    if not isinstance(value, Mapping) or not _claim(value.get("claim_boundary")):
        raise ValueError("wave selection context bundle is invalid")
    raw_facts, pages = value.get("shared_facts"), value.get("pages")
    if not isinstance(raw_facts, Mapping) or len(raw_facts) > 100_000:
        raise ValueError("wave selection context facts are invalid")
    if not isinstance(pages, list) or len(pages) > 10_000:
        raise ValueError("wave selection context pages are invalid")
    facts: dict[str, Mapping[str, Any]] = {}
    for digest, fact in raw_facts.items():
        if (
            not _sha(digest) or not isinstance(fact, Mapping)
            or set(fact) != {"kind", "payload"} or not _text(fact.get("kind"))
            or not isinstance(fact.get("payload"), Mapping)
            or hashlib.sha256(canonical(fact)).hexdigest() != digest
        ):
            raise ValueError("wave selection context fact binding drifted")
        facts[digest] = fact
    visible: set[str] = set()
    for page in pages:
        if not isinstance(page, Mapping) or not _text(page.get("scc_id")):
            raise ValueError("wave selection context page is invalid")
        refs = _sha_list(page.get("fact_refs"), "page fact refs", canonical_order=False)
        if any(ref not in facts for ref in refs):
            raise ValueError("wave selection context page references an unknown fact")
        if page["scc_id"] == unit_id:
            visible.update(refs)
    if not visible:
        raise ValueError("wave selection target SCC has no visible context")
    retrieval = validate_retrieval_bundle(value, facts, pages)
    omitted = set(retrieval.get(unit_id, {}).get("fact_refs", []))
    return facts, visible, omitted
def _host_facts(value: Any, unit_id: str, failures: Mapping[str, str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError("wave selection host facts are invalid")
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) != {"sha256", "fact"}:
            raise ValueError("wave selection host fact record is invalid")
        digest = _digest(raw.get("sha256"), "host fact")
        fact = raw.get("fact")
        if (
            digest not in failures or not isinstance(fact, Mapping)
            or set(fact) != {"kind", "payload"}
            or fact.get("kind") != "host_verifier_failure"
            or hashlib.sha256(canonical(fact)).hexdigest() != digest
        ):
            raise ValueError("wave selection host fact binding drifted")
        payload = fact.get("payload")
        if not isinstance(payload, Mapping) or set(payload) != _HOST_PAYLOAD_KEYS:
            raise ValueError("wave selection host fact payload is invalid")
        candidate_set = payload.get("candidate_set_sha256")
        if (
            payload.get("consumer_unit_id") != unit_id
            or not _text(payload.get("source_unit_id"))
            or not _text(payload.get("candidate_artifact_id"))
            or not _sha(payload.get("candidate_sha256"))
            or (candidate_set is not None and not _sha(candidate_set))
            or payload.get("failure_evidence_sha256") != failures[digest]
            or not _text(payload.get("gate_family"))
            or payload.get("model_input_safe") is not True
        ):
            raise ValueError("wave selection host fact identity drifted")
        safe = normalize_gate_evidence(
            gate_family=payload.get("gate_family"), status="failed",
            candidate_artifact_id=payload["candidate_artifact_id"],
            candidate_sha256=payload["candidate_sha256"],
            diagnostics=payload.get("diagnostics"),
        )
        if (payload.get("diagnostics") != safe["diagnostics"]
                or payload.get("withheld_fields") != safe["withheld_fields"]):
            raise ValueError("wave selection host fact is not model-safe")
        result.append({"sha256": digest, "fact": fact})
    if [item["sha256"] for item in result] != sorted(failures):
        raise ValueError("wave selection host facts do not match constraints")
    return result
def _cas_reference(value: Any, directives: Mapping[str, Any]) -> None:
    if (not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}
            or not isinstance(value.get("path"), str)):
        raise ValueError("wave selection CAS reference is invalid")
    path = PurePosixPath(checked_relative_path(str(value.get("path", ""))))
    encoded = canonical_json_bytes(directives)
    digest = hashlib.sha256(encoded).hexdigest()
    tail = ("context", "frontier-cas", _KIND, "sha256", digest[:2], f"{digest}.json")
    matches = [index for index in range(len(path.parts) - 5)
               if tuple(path.parts[index:index + 6]) == tail]
    size = value.get("size_bytes")
    if (value.get("sha256") != digest or size != len(encoded) or len(matches) != 1):
        raise ValueError("wave selection CAS reference binding drifted")

def _sha_list(value: Any, label: str, *, canonical_order: bool = True) -> list[str]:
    if not isinstance(value, list) or len(value) > 100_000 or any(not _sha(item) for item in value):
        raise ValueError(f"wave selection {label} are invalid")
    if len(value) != len(set(value)) or (canonical_order and value != sorted(value)):
        raise ValueError(f"wave selection {label} are not canonical")
    return list(value)

def _digest(value: Any, label: str) -> str:
    if not _sha(value):
        raise ValueError(f"wave selection {label} SHA-256 is invalid")
    return value

def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

__all__ = ["validate_context_frontier_wave_selection"]
