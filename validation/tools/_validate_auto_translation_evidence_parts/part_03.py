def validate_external_direct_callee_context_for_default_checks(
    evidence_dir: Path,
    prefix: str,
    slice_spec_path: Path,
) -> None:
    slice_spec = load_json(slice_spec_path)
    if not slice_spec.get("c_boundary", {}).get("external_direct_callees"):
        return
    manifest = load_json(evidence_dir / f"{prefix}-evidence-manifest.json")
    final_verification = {}
    final_ref = manifest.get("evidence", {}).get("final_verification")
    if isinstance(final_ref, dict) and final_ref.get("path") and str(final_ref.get("status", "")) != "missing":
        final_verification = load_ref(manifest.get("evidence", {}), "final_verification")
    validate_external_direct_callee_context(slice_spec, evidence_dir, prefix, manifest, final_verification)


def validate_external_callee_signature_descriptor(
    name: str,
    signature: dict[str, Any],
    descriptor: dict[str, Any],
    label: str,
) -> None:
    signature_function = str(signature.get("function") or "")
    if signature_function and signature_function != name:
        raise SystemExit(
            f"external callee signature function mismatch for {name}: {signature_function}"
        )
    expected_shape = external_callee_signature_shape(signature)
    actual_shape = external_callee_signature_shape(descriptor)
    if actual_shape != expected_shape:
        raise SystemExit(
            f"external callee signature shape mismatch for {name} in {label}"
        )


def external_callee_expected_contract(
    name: str,
    declared_callee: dict[str, Any],
    signature: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "signature_ref": str(declared_callee.get("signature_ref") or signature.get("id") or name),
        "source_ref": str(declared_callee.get("source_ref") or signature.get("source_ref") or ""),
        "definition_status": str(
            declared_callee.get("definition_status") or signature.get("definition_status") or ""
        ),
        "source_files": external_callee_source_file_counter(declared_callee.get("source_files") or []),
    }


def external_callee_scope_stub_kind(contracts: Iterable[dict[str, Any]]) -> str:
    kinds = {str(contract.get("stub_kind") or "compile_only") for contract in contracts}
    if not kinds:
        return "none"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed_context"


def validate_external_callee_accepted_named_slice_evidence(
    name: str,
    plan_callee: dict[str, Any],
    context_callee: dict[str, Any],
) -> None:
    plan_binding = plan_callee.get("accepted_named_slice_evidence")
    context_binding = context_callee.get("accepted_named_slice_evidence")
    if not isinstance(plan_binding, dict) or not isinstance(context_binding, dict):
        raise SystemExit(f"external callee {name} accepted named-slice evidence binding missing")
    if plan_binding != context_binding:
        raise SystemExit(f"external callee {name} accepted named-slice evidence binding drift")
    final_path_text = str(plan_binding.get("final_verification_path") or "")
    final_sha = str(plan_binding.get("final_verification_sha256") or "")
    if not final_path_text or not final_sha:
        raise SystemExit(f"external callee {name} accepted named-slice final verification ref missing")
    final_path = resolve_ref_path(final_path_text)
    if not final_path.exists():
        raise SystemExit(f"external callee {name} accepted named-slice final verification missing: {final_path}")
    actual_sha = sha256(final_path)
    if actual_sha != final_sha:
        raise SystemExit(
            f"external callee {name} accepted named-slice final verification sha mismatch: {final_sha} != {actual_sha}"
        )
    final = load_json(final_path)
    if final.get("target_id") != plan_binding.get("target_id"):
        raise SystemExit(f"external callee {name} accepted named-slice target_id mismatch")
    if final.get("slice_id") != plan_binding.get("slice_id"):
        raise SystemExit(f"external callee {name} accepted named-slice slice_id mismatch")
    if final.get("semantic_pass") is not True or plan_binding.get("semantic_pass") is not True:
        raise SystemExit(f"external callee {name} accepted named-slice evidence must have semantic_pass=true")
    if (
        final.get("accepted_evidence_authoritative") is not True
        or plan_binding.get("accepted_evidence_authoritative") is not True
    ):
        raise SystemExit(
            f"external callee {name} accepted named-slice evidence must be accepted_evidence_authoritative"
        )
    if final.get("generated_draft_semantic_pass") is True or plan_binding.get("generated_draft_semantic_pass") is True:
        raise SystemExit(
            f"external callee {name} accepted named-slice evidence must not accept generated draft semantics"
        )


def validate_external_callee_descriptor_binding(
    name: str,
    contract: dict[str, Any],
    descriptor: dict[str, Any],
    label: str,
) -> None:
    expected_source_ref = str(contract.get("source_ref") or "")
    if expected_source_ref and descriptor.get("source_ref") != expected_source_ref:
        raise SystemExit(f"external callee source binding mismatch for {name} in {label}")
    expected_definition_status = str(contract.get("definition_status") or "")
    if expected_definition_status and descriptor.get("definition_status") != expected_definition_status:
        raise SystemExit(f"external callee source binding mismatch for {name} in {label}")
    expected_sources = contract.get("source_files")
    actual_sources = external_callee_source_file_counter(descriptor.get("source_files") or [])
    if expected_sources != actual_sources:
        raise SystemExit(f"external callee source binding mismatch for {name} in {label}")


def validate_external_callee_source_bindings(
    name: str,
    contract: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> None:
    expected_sources = contract.get("source_files")
    actual_sources = external_callee_source_file_counter(bindings)
    if expected_sources != actual_sources:
        raise SystemExit(f"external callee source binding mismatch for {name}")


def external_callee_source_file_counter(sources: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter(
        (
            str(source.get("path") or ""),
            str(source.get("sha256") or ""),
        )
        for source in sources
        if isinstance(source, dict)
    )


def validate_external_callee_signature_binding(
    name: str,
    signature_ref: str,
    binding: dict[str, Any],
) -> None:
    if binding.get("signature_ref") != signature_ref:
        raise SystemExit(f"external callee signature binding mismatch for {name}")
    if binding.get("stub_kind") not in {"compile_only", "accepted_named_slice_evidence"}:
        raise SystemExit(
            f"external callee signature binding for {name} must record supported stub_kind"
        )
    if binding.get("semantics_verified"):
        raise SystemExit(
            f"external callee signature binding for {name} must keep semantics_verified=false"
        )


def validate_external_callee_block_binding(
    name: str,
    plan_block: dict[str, Any] | None,
    context_block: dict[str, Any] | None,
) -> None:
    if plan_block is None:
        raise SystemExit(f"external callee {name} missing blocked entry in translation plan")
    if context_block is None:
        raise SystemExit(f"external callee {name} missing blocked entry in context pack")
    if plan_block.get("reason") != context_block.get("reason"):
        raise SystemExit(f"external callee {name} blocked reason mismatch")
    if plan_block.get("stub_kind") != "none" or context_block.get("stub_kind") != "none":
        raise SystemExit(f"external callee {name} blocked entry must record stub_kind=none")
    if plan_block.get("semantics_verified") or context_block.get("semantics_verified"):
        raise SystemExit(f"external callee {name} blocked entry must keep semantics_verified=false")


def external_callee_signature_shape(payload: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return_type = str(payload.get("return_type") or payload.get("returns") or "")
    parameters = tuple(
        (
            str(param.get("name") or f"arg{index + 1}"),
            str(param.get("c_type") or param.get("type") or ""),
        )
        for index, param in enumerate(payload.get("parameters") or [])
        if isinstance(param, dict)
    )
    return return_type, parameters


def validate_external_callee_call_site_bindings(
    contracts: dict[str, dict[str, Any]],
    plan_call_edges: list[dict[str, Any]],
    context_call_edges: list[dict[str, Any]],
    call_bindings: list[dict[str, Any]],
) -> None:
    expected = external_call_site_counter(plan_call_edges)
    context_edges = external_call_site_counter(context_call_edges)
    bindings = external_call_site_counter(call_bindings)
    if expected != context_edges:
        raise SystemExit(
            "external callee call-site binding mismatch between translation plan and context pack direct_call_edges"
        )
    if expected != bindings:
        raise SystemExit(
            "external callee call-site binding mismatch between direct calls and call_edge_to_callee_binding"
        )

    for label, edges in [
        ("translation plan", plan_call_edges),
        ("context pack direct_call_edges", context_call_edges),
        ("context pack call_edge_to_callee_binding", call_bindings),
    ]:
        for edge in edges:
            callee = str(edge.get("callee") or "")
            contract = contracts.get(callee)
            if contract is None:
                continue
            expected_signature = str(contract.get("signature_ref") or "")
            actual_signature = external_call_site_signature_ref(edge)
            if actual_signature != expected_signature:
                raise SystemExit(
                    f"external callee call-site binding signature mismatch for {callee} in {label}"
                )
            if label == "context pack call_edge_to_callee_binding":
                expected_stub_kind = str(contract.get("stub_kind") or "compile_only")
                if edge.get("stub_kind") != expected_stub_kind:
                    raise SystemExit(
                        f"external callee call-site binding for {callee} must record stub_kind={expected_stub_kind}"
                    )
                if edge.get("semantics_verified"):
                    raise SystemExit(
                        f"external callee call-site binding for {callee} must keep semantics_verified=false"
                    )
            else:
                validate_external_callee_call_site_metadata(callee, contract, edge, label)


def validate_external_callee_blocked_call_sites(
    blocked_contracts: dict[str, dict[str, Any]],
    plan_call_edges: list[dict[str, Any]],
    context_call_edges: list[dict[str, Any]],
) -> None:
    if not blocked_contracts:
        return
    plan_blocked_edges = [edge for edge in plan_call_edges if edge.get("callee") in blocked_contracts]
    context_blocked_edges = [edge for edge in context_call_edges if edge.get("callee") in blocked_contracts]
    if external_call_site_counter(plan_blocked_edges) != external_call_site_counter(context_blocked_edges):
        raise SystemExit(
            "external callee blocked call-site mismatch between translation plan and context pack direct_call_edges"
        )
    for label, edges in [
        ("translation plan", plan_blocked_edges),
        ("context pack direct_call_edges", context_blocked_edges),
    ]:
        for edge in edges:
            callee = str(edge.get("callee") or "")
            contract = blocked_contracts.get(callee)
            if contract is None:
                continue
            if edge.get("callee_scope") != "external_direct_callee":
                raise SystemExit(f"external callee blocked call-site metadata mismatch for {callee} in {label}")
            if edge.get("stub_status") != "blocked":
                raise SystemExit(f"external callee blocked call-site metadata mismatch for {callee} in {label}")
            expected_reason = str(contract.get("blocked_reason") or "")
            if expected_reason and edge.get("blocked_reason") != expected_reason:
                raise SystemExit(f"external callee blocked call-site metadata mismatch for {callee} in {label}")


def validate_external_callee_call_site_metadata(
    callee: str,
    contract: dict[str, Any],
    edge: dict[str, Any],
    label: str,
) -> None:
    if edge.get("callee_scope") != "external_direct_callee":
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")
    if edge.get("stub_status") != "compile_only":
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")
    expected_source_ref = str(contract.get("source_ref") or "")
    if expected_source_ref and edge.get("callee_source_ref") != expected_source_ref:
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")
    expected_definition_status = str(contract.get("definition_status") or "")
    if expected_definition_status and edge.get("definition_status") != expected_definition_status:
        raise SystemExit(f"external callee call-site metadata mismatch for {callee} in {label}")


def external_call_site_counter(edges: list[dict[str, Any]]) -> Counter[tuple[str, str, str, str]]:
    return Counter(external_call_site_key(edge) for edge in edges)


def external_call_site_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("callee") or ""),
        str(edge.get("source_expression") or ""),
        str(edge.get("statement_context") or ""),
        external_call_site_signature_ref(edge),
    )


def external_call_site_signature_ref(edge: dict[str, Any]) -> str:
    return str(edge.get("signature_ref") or edge.get("callee_signature_id") or "")


def load_ref(evidence: dict[str, Any], key: str) -> dict[str, Any]:
    ref = evidence.get(key, {})
    path = ref.get("path")
    if not path:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.path")
    status = ref.get("status")
    if not isinstance(status, str) or not status:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.status")
    ref_sha = ref.get("sha256")
    if not isinstance(ref_sha, str) or not ref_sha:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.sha256")
    resolved = resolve_ref_path(str(path))
    if not resolved.exists():
        raise SystemExit(f"semantic pass requires existing evidence.{key}: {resolved}")
    actual_sha = sha256(resolved)
    if ref_sha != actual_sha:
        raise SystemExit(f"semantic pass manifest evidence.{key}.sha256 mismatch: {ref_sha} != {actual_sha}")
    payload = load_json(resolved)
    payload_status = payload.get("status")
    if not isinstance(payload_status, str) or not payload_status:
        raise SystemExit(f"semantic pass manifest evidence.{key} payload status missing")
    if status != payload_status:
        raise SystemExit(f"semantic pass manifest evidence.{key}.status mismatch: {status} != {payload_status}")
    return payload


def require_status(report: dict[str, Any], label: str, allowed: set[str]) -> None:
    status = str(report.get("status", ""))
    if status not in allowed:
        raise SystemExit(f"semantic pass requires {label}.status in {sorted(allowed)}, got {status!r}")


def mutation_detected(report: dict[str, Any]) -> bool:
    return bool(report.get("mutation_detected") or report.get("detected"))


def source_commit(slice_spec: dict[str, Any]) -> str:
    return slice_spec.get("source_commit") or slice_spec.get("source", {}).get("source_commit") or "UNKNOWN0"


def fixture_path_from_spec(slice_spec: dict[str, Any]) -> str:
    fixture = slice_spec.get("fixture_contract", {})
    return fixture.get("path") or fixture.get("input") or "unknown-fixture"


def behavior_fields_from_spec(slice_spec: dict[str, Any]) -> list[str]:
    fixture = slice_spec.get("fixture_contract", {})
    fields = fixture.get("observable_outputs") or fixture.get("behavior_fields") or []
    return [str(item) for item in fields]


def c_function_prototype(slice_spec: dict[str, Any]) -> str:
    function_name = slice_spec.get("function_name") or ""
    signatures = slice_spec.get("c_boundary", {}).get("signatures", [])
    signature = next(
        (item for item in signatures if isinstance(item, dict) and item.get("function") == function_name),
        {},
    )
    return_type = signature.get("return_type") or "int"
    parameters = signature.get("parameters") or []
    if not parameters:
        parameter_text = "void"
    else:
        parameter_text = ", ".join(c_parameter_declaration(item) for item in parameters if isinstance(item, dict))
    return f"{return_type} {function_name}({parameter_text});"


def c_parameter_declaration(parameter: dict[str, Any]) -> str:
    name = str(parameter.get("name") or "arg")
    c_type = str(parameter.get("c_type") or "int").strip()
    if c_type.endswith("*"):
        return f"{c_type[:-1].rstrip()} *{name}"
    return f"{c_type} {name}"


def sha256(path: Path) -> str:
    return judge_validator.sha256_file(path)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def artifact_cache_identity(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": artifact.get("status", "unknown"),
        "sha256": sha256_json(artifact),
    }


def oracle_boundary_contract_identity(profile: dict[str, Any]) -> dict[str, Any]:
    contract = profile.get("oracle_boundary_contract")
    if not isinstance(contract, dict):
        return {"status": "missing", "sha256": "missing"}
    return {
        "status": contract.get("status", "unknown"),
        "sha256": sha256_json(contract),
    }


def resolve_slice_spec(target_id: str, slice_id: str) -> Path:
    spec_dir = REPO_ROOT / "validation" / "slice-specs"
    candidates = [
        spec_dir / f"{target_id}-{slice_id}.json",
        spec_dir / f"{target_id.split('-')[0]}-{slice_id}.json",
    ]
    candidates.extend(spec_dir.glob(f"*-{slice_id}.json"))
    candidates.extend(spec_dir.glob(f"*{slice_id}*.json"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"no slice spec found for target_id={target_id!r}, slice_id={slice_id!r}; pass --slice-spec explicitly"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
