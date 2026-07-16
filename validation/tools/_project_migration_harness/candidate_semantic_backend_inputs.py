from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .candidate_semantic_plan import fixed_adapter_plan, require_semantic_family
from .candidate_semantic_schema import CONTEXT_KEYS
from .candidate_semantic_backend_contract import (
    ScalarFunction,
    ScalarType,
    SemanticBackendError,
    compile_arguments,
    parse_scalar_function,
    valid_identifier,
)
from .orchestration_facts import read_artifact_reference


@dataclass(frozen=True)
class BackendInputs:
    candidate_source: bytes
    source_path: str
    source_bytes: bytes
    function_source: bytes
    headers: tuple[tuple[str, bytes], ...]
    function: ScalarFunction
    compile_arguments: tuple[str, ...]
    compiler_basename: str
    compiler_binary_sha256: str
    compiler_binary_size_bytes: int
    sandbox_contract: dict[str, Any]
    input_sha256: str


def load_backend_inputs(
    request: Mapping[str, Any], gate_family: str, repository_root: Path,
) -> BackendInputs:
    require_semantic_family(gate_family)
    if (
        not isinstance(request, Mapping)
        or set(request) != {
            "schema_version", "artifact_kind", "bindings", "verification_plan",
        }
        or request.get("schema_version") != 1
        or request.get("artifact_kind") != "candidate-semantic-adapter-request"
        or request.get("verification_plan") != fixed_adapter_plan(gate_family)
    ):
        raise SemanticBackendError("semantic_request_contract_invalid")
    bindings = request.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != CONTEXT_KEYS:
        raise SemanticBackendError("semantic_request_bindings_invalid")
    worker_ref = bindings.get("worker_request")
    if not isinstance(worker_ref, Mapping):
        raise SemanticBackendError("semantic_worker_request_unbound")
    worker = _json_ref(repository_root, worker_ref, "semantic_worker_request_invalid")
    _validate_worker_request(worker, bindings)
    facts = _context_facts(repository_root, worker)
    node, function_source = _single_function(facts)
    source_binding = _single_fact(facts, "source_binding", "node_id", node["node_id"])
    source_ref = source_binding.get("source")
    if not isinstance(source_ref, Mapping):
        raise SemanticBackendError("semantic_c_source_binding_invalid")
    source_path = str(source_ref.get("path", ""))
    source_bytes = _read_ref(
        repository_root, source_ref, "semantic_c_source_binding_invalid",
    )
    _validate_source_span(source_bytes, source_ref, function_source)
    candidate = _read_ref(
        repository_root, bindings["candidate_source"],
        "semantic_candidate_source_invalid",
    )
    compile_raw = _json_ref(
        repository_root, bindings["compile_observation"],
        "semantic_compile_observation_invalid",
    )
    contract = _compile_contract(compile_raw, bindings)
    compile_arguments_value = compile_arguments(facts, str(node["unit_id"]))
    compiler_identity = _compiler_identity(facts, str(node["unit_id"]))
    headers = _header_sources(repository_root, facts)
    function = parse_scalar_function(
        str(node["symbol"]), function_source.decode("utf-8"),
    )
    return BackendInputs(
        candidate_source=candidate, source_path=source_path,
        source_bytes=source_bytes, function_source=function_source,
        headers=headers, function=function,
        compile_arguments=compile_arguments_value,
        compiler_basename=compiler_identity[0],
        compiler_binary_sha256=compiler_identity[1],
        compiler_binary_size_bytes=compiler_identity[2],
        sandbox_contract=contract,
        input_sha256=content_sha256({
            "request": request, "c_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        }),
    )


def _compiler_identity(
    facts: list[dict[str, Any]], unit_id: str,
) -> tuple[str, str, int]:
    fact = _single_fact(facts, "compiler_fact_binding", "unit_id", unit_id)
    basename = fact.get("compiler_basename")
    digest = fact.get("compiler_binary_sha256")
    size = fact.get("compiler_binary_size_bytes")
    if (
        fact.get("status") != "syntax_passed"
        or fact.get("syntax_passed") is not True
        or fact.get("command_started") is not True
        or fact.get("semantic_gate") is not False
        or fact.get("translation_coverage_numerator") != 0
        or not isinstance(basename, str)
        or not basename
        or any(char in basename for char in "/\\\r\n\x00")
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        or type(size) is not int
        or size < 1
    ):
        raise SemanticBackendError("semantic_original_compiler_unproven")
    return basename, digest, size


def _validate_worker_request(
    worker: Mapping[str, Any], bindings: Mapping[str, Any],
) -> None:
    if worker.get("schema_version") != 1 or worker.get("role") not in {
        "translator", "repairer",
    }:
        raise SemanticBackendError("semantic_worker_request_invalid")
    for key in ("run_id", "group_id", "unit_id"):
        if worker.get(key) != bindings.get(key):
            raise SemanticBackendError("semantic_worker_request_identity_drifted")
    base = dict(worker)
    execution = base.pop("execution_binding", None)
    claimed = base.pop("effective_input_sha256", None)
    if claimed != content_sha256(base):
        raise SemanticBackendError("semantic_worker_request_hash_drifted")
    if execution is not None and (
        not isinstance(execution, Mapping)
        or execution.get("effective_input_sha256") != claimed
    ):
        raise SemanticBackendError("semantic_worker_execution_binding_drifted")


def _context_facts(root: Path, worker: Mapping[str, Any]) -> list[dict[str, Any]]:
    context = worker.get("context")
    pages = context.get("pages") if isinstance(context, Mapping) else None
    if not isinstance(pages, list) or not pages or len(pages) > 128:
        raise SemanticBackendError("semantic_context_pages_invalid")
    result = []
    for page_ref in pages:
        if not isinstance(page_ref, Mapping):
            raise SemanticBackendError("semantic_context_page_invalid")
        data = _read_ref(root, page_ref, "semantic_context_page_invalid")
        if page_ref.get("byte_count") != len(data):
            raise SemanticBackendError("semantic_context_page_size_drifted")
        page = _canonical_json(data, "semantic_context_page_invalid")
        facts = page.get("facts")
        if not isinstance(facts, list) or len(facts) > 4096:
            raise SemanticBackendError("semantic_context_facts_invalid")
        for fact in facts:
            if not isinstance(fact, dict) or set(fact) != {"sha256", "kind", "payload"}:
                raise SemanticBackendError("semantic_context_fact_invalid")
            expected = content_sha256({"kind": fact["kind"], "payload": fact["payload"]})
            if fact["sha256"] != expected or not isinstance(fact["payload"], dict):
                raise SemanticBackendError("semantic_context_fact_hash_drifted")
            result.append(fact)
    return result


def _single_function(facts: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes]:
    chunks: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        if fact["kind"] == "function_source":
            payload = fact["payload"]
            chunks.setdefault(str(payload.get("node_id")), []).append(payload)
    if len(chunks) != 1:
        raise SemanticBackendError("semantic_scalar_lane_requires_one_function")
    node_id, values = next(iter(chunks.items()))
    node = _single_fact(facts, "function", "node_id", node_id)
    if node.get("node_kind") != "function" or not valid_identifier(node.get("symbol")):
        raise SemanticBackendError("semantic_function_identity_invalid")
    for fact in facts:
        payload = fact["payload"]
        owner = payload.get("caller_node_id", payload.get("node_id"))
        if owner == node_id and fact["kind"] in {
            "resolved_call", "external_call", "global_reference", "parser_boundary",
        }:
            raise SemanticBackendError("semantic_scalar_lane_has_dependencies")
    values.sort(key=lambda item: int(item.get("chunk_index", -1)))
    if [item.get("chunk_index") for item in values] != list(range(len(values))) or any(
        item.get("chunk_count") != len(values) or not isinstance(item.get("content"), str)
        for item in values
    ):
        raise SemanticBackendError("semantic_function_source_chunks_invalid")
    return node, "".join(str(item["content"]) for item in values).encode("utf-8")


def _single_fact(
    facts: list[dict[str, Any]], kind: str, key: str, value: str,
) -> dict[str, Any]:
    matches = [fact["payload"] for fact in facts if fact["kind"] == kind and fact["payload"].get(key) == value]
    if len(matches) != 1:
        raise SemanticBackendError(f"semantic_{kind}_fact_invalid")
    return matches[0]


def _validate_source_span(
    source: bytes, reference: Mapping[str, Any], function_source: bytes,
) -> None:
    span = reference.get("span")
    if not isinstance(span, Mapping):
        raise SemanticBackendError("semantic_c_source_span_invalid")
    start, end = span.get("byte_start"), span.get("byte_end")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise SemanticBackendError("semantic_c_source_span_invalid")
    selected = source[start:end] if 0 <= start <= end <= len(source) else b""
    if selected != function_source or hashlib.sha256(selected).hexdigest() != span.get("sha256"):
        raise SemanticBackendError("semantic_c_source_span_drifted")


def _header_sources(root: Path, facts: list[dict[str, Any]]) -> tuple[tuple[str, bytes], ...]:
    result = []
    for fact in facts:
        if fact["kind"] != "header_source_binding":
            continue
        source = fact["payload"].get("source")
        if not isinstance(source, Mapping):
            raise SemanticBackendError("semantic_header_binding_invalid")
        path = str(source.get("path", ""))
        result.append((path, _read_ref(root, source, "semantic_header_binding_invalid")))
    paths = [item[0] for item in result]
    if len(paths) != len(set(paths)):
        raise SemanticBackendError("semantic_header_binding_duplicated")
    return tuple(sorted(result))


def _compile_contract(raw: Mapping[str, Any], bindings: Mapping[str, Any]) -> dict[str, Any]:
    if any(raw.get(key) != bindings.get(key) for key in ("run_id", "unit_id", "candidate_artifact_id", "candidate_sha256", "candidate_set_sha256")):
        raise SemanticBackendError("semantic_compile_observation_binding_drifted")
    sandbox = raw.get("sandbox")
    contract = sandbox.get("contract") if isinstance(sandbox, Mapping) else None
    if (
        not isinstance(contract, dict)
        or contract.get("toolchain_sha256") != bindings.get("toolchain_sha256")
    ):
        raise SemanticBackendError("semantic_compile_sandbox_contract_missing")
    return contract


def _json_ref(root: Path, reference: Mapping[str, Any], code: str) -> dict[str, Any]:
    return _canonical_json(_read_ref(root, reference, code), code)


def _canonical_json(data: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SemanticBackendError(code) from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise SemanticBackendError(code)
    return value


def _read_ref(root: Path, reference: Mapping[str, Any], code: str) -> bytes:
    try:
        data = read_artifact_reference(root, reference)
    except (OSError, ValueError) as error:
        raise SemanticBackendError(code) from error
    size = reference.get("size_bytes", reference.get("byte_count", len(data)))
    if size != len(data):
        raise SemanticBackendError(code)
    _safe_relative(str(reference.get("path", "")))
    return data


def _safe_relative(value: str) -> None:
    if not value or "\\" in value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise SemanticBackendError("semantic_repository_path_invalid")


__all__ = [
    "BackendInputs", "ScalarFunction", "ScalarType", "SemanticBackendError",
    "load_backend_inputs",
]
