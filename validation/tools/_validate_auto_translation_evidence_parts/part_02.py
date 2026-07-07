def validate_c2rust_baseline_candidate_binding(
    c2rust_candidate: dict[str, Any],
    *,
    evidence_dir: Path | None,
    prefix: str | None,
    strict: bool,
) -> None:
    if strict and c2rust_candidate.get("generated_draft_semantic_pass") is not False:
        raise SystemExit(
            "route_decision.candidate_generation.c2rust_baseline.generated_draft_semantic_pass "
            "must be false"
        )
    if strict and "output_ref" not in c2rust_candidate:
        raise SystemExit("route_decision.candidate_generation.c2rust_baseline.output_ref missing")
    manifest_ref = c2rust_candidate.get("baseline_manifest")
    if manifest_ref is None:
        if strict:
            raise SystemExit("route_decision.candidate_generation.c2rust_baseline.baseline_manifest missing")
        return
    if not isinstance(manifest_ref, dict):
        raise SystemExit("route_decision.candidate_generation.c2rust_baseline.baseline_manifest must be an object")
    manifest_path = (
        evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
        if evidence_dir is not None and prefix is not None
        else resolve_ref_path(str(manifest_ref.get("path", "")))
    )
    require_ref(
        manifest_ref,
        manifest_path,
        "route_decision.candidate_generation.c2rust_baseline.baseline_manifest",
        require_sha=True,
    )
    baseline = load_json(manifest_path)
    for field in ["status", "reason", "correctness_role"]:
        if c2rust_candidate.get(field) != baseline.get(field):
            raise SystemExit(f"route_decision.candidate_generation.c2rust_baseline {field} drift")
    output_ref = c2rust_candidate.get("output_ref")
    baseline_status = str(baseline.get("status", "missing"))
    baseline_output = baseline.get("output")
    if baseline_status == "generated":
        if not isinstance(baseline_output, dict):
            raise SystemExit("c2rust_baseline generated status requires output object")
        validate_c2rust_baseline_generation_status(baseline, baseline_output, manifest_path)
        validate_c2rust_baseline_compile_status(baseline, baseline_output, manifest_path)
        expected_output = {
            "path": str(baseline_output.get("path", "")),
            "status": baseline_status,
            "sha256": str(baseline_output.get("sha256", "")),
        }
        if output_ref != expected_output:
            raise SystemExit("route_decision.candidate_generation.c2rust_baseline output_ref drift")
        require_file_ref(
            output_ref,
            "route_decision.candidate_generation.c2rust_baseline.output_ref",
            require_status=True,
        )
        return
    if output_ref is not None:
        raise SystemExit("route_decision.candidate_generation.c2rust_baseline output_ref drift")


def validate_verified_unsafe_baseline_artifact(
    evidence_dir: Path,
    prefix: str,
    verified_path: Path,
    baseline_path: Path,
) -> None:
    verified = load_json(verified_path)
    baseline = load_json(baseline_path)
    require_ref(
        verified.get("c2rust_baseline"),
        baseline_path,
        "verified_unsafe_baseline.c2rust_baseline",
        require_sha=True,
    )
    expected_output = c2rust_baseline_expected_output_ref(baseline)
    expected_compile_artifact = c2rust_baseline_expected_compile_artifact_ref(baseline)
    if expected_output is None:
        if verified.get("c2rust_output") is not None:
            raise SystemExit("verified_unsafe_baseline c2rust_output drift")
    elif verified.get("c2rust_output") != expected_output:
        raise SystemExit("verified_unsafe_baseline c2rust_output drift")
    if expected_compile_artifact is None:
        if verified.get("compile_artifact") is not None:
            raise SystemExit("verified_unsafe_baseline compile_artifact drift")
    elif verified.get("compile_artifact") != expected_compile_artifact:
        raise SystemExit("verified_unsafe_baseline compile_artifact drift")

    semantic_source = verified.get("semantic_claim_source")
    if semantic_source in FORBIDDEN_UNSAFE_SEMANTIC_CLAIM_SOURCES:
        raise SystemExit(f"verified_unsafe_baseline semantic_claim_source cannot be compile-only: {semantic_source}")
    direct = verified.get("direct_c2rust_replay")
    verified_passed = verified.get("status") == "passed" or verified.get("semantic_pass") is True
    if not isinstance(direct, dict):
        if verified_passed:
            raise SystemExit("verified_unsafe_baseline passed status requires direct_c2rust_replay")
        return

    direct_source = direct.get("semantic_claim_source") or direct.get("source")
    if direct_source in FORBIDDEN_UNSAFE_SEMANTIC_CLAIM_SOURCES:
        raise SystemExit(f"direct_c2rust_replay cannot use compile-only semantic source: {direct_source}")
    direct_status = direct.get("status")
    if direct_status != "passed":
        if verified_passed:
            raise SystemExit("verified_unsafe_baseline passed status requires passed direct_c2rust_replay")
        if direct.get("semantic_pass") is True:
            raise SystemExit("direct_c2rust_replay semantic_pass requires passed status")
        return
    if expected_output is None:
        raise SystemExit("direct_c2rust_replay requires generated c2rust_output")
    if direct.get("c2rust_output") != expected_output:
        raise SystemExit("direct_c2rust_replay c2rust_output drift")
    if expected_compile_artifact is not None and direct.get("compile_artifact") != expected_compile_artifact:
        raise SystemExit("direct_c2rust_replay compile_artifact drift")

    direct_payload = direct
    direct_artifact_ref = direct.get("artifact")
    if direct_artifact_ref is not None:
        direct_path = evidence_dir / f"{prefix}-c2rust-direct-replay.json"
        require_ref(
            direct_artifact_ref,
            direct_path,
            "verified_unsafe_baseline.direct_c2rust_replay.artifact",
            require_sha=True,
        )
        direct_payload = load_json(direct_path)
        if direct_payload.get("c2rust_output") != expected_output:
            raise SystemExit("direct_c2rust_replay c2rust_output drift")
        if expected_compile_artifact is not None and direct_payload.get("compile_artifact") != expected_compile_artifact:
            raise SystemExit("direct_c2rust_replay compile_artifact drift")
    if direct_payload.get("replay_kind") != "direct_c2rust_output_replay":
        raise SystemExit("direct_c2rust_replay must bind direct C2Rust output replay")
    if direct_payload.get("correctness_role") != "direct_replay_evidence":
        raise SystemExit("direct_c2rust_replay correctness_role must be direct_replay_evidence")
    payload_source = direct_payload.get("semantic_claim_source") or direct_payload.get("source")
    if payload_source in FORBIDDEN_UNSAFE_SEMANTIC_CLAIM_SOURCES:
        raise SystemExit(f"direct_c2rust_replay cannot use compile-only semantic source: {payload_source}")
    if direct_payload.get("semantic_pass") is True and direct_payload.get("observable_replay_pass") is not True:
        raise SystemExit("direct_c2rust_replay semantic_pass requires observable_replay_pass")
    if verified_passed:
        if semantic_source != "verified_unsafe_baseline_gates":
            raise SystemExit(
                "verified_unsafe_baseline passed status requires semantic_claim_source=verified_unsafe_baseline_gates"
            )
        if verified.get("blocked_reasons") not in (None, []):
            raise SystemExit("verified_unsafe_baseline passed status requires empty blocked_reasons")
        validate_verified_unsafe_baseline_same_output_gate_refs(
            evidence_dir,
            prefix,
            verified,
            expected_output,
            expected_compile_artifact,
            direct_artifact_ref,
        )


def validate_verified_unsafe_baseline_same_output_gate_refs(
    evidence_dir: Path,
    prefix: str,
    verified: dict[str, Any],
    expected_output: dict[str, Any] | None,
    expected_compile_artifact: dict[str, Any] | None,
    direct_artifact_ref: Any,
) -> None:
    if expected_output is None:
        raise SystemExit("verified_unsafe_baseline same_output_gate_refs require generated c2rust_output")
    if not isinstance(direct_artifact_ref, dict):
        raise SystemExit("verified_unsafe_baseline same_output_gate_refs require direct_c2rust_replay artifact")
    gate_refs = verified.get("same_output_gate_refs")
    if not isinstance(gate_refs, dict):
        raise SystemExit("verified_unsafe_baseline same_output_gate_refs missing")
    missing = sorted(set(C2RUST_VERIFIED_BASELINE_SAME_OUTPUT_GATES) - set(gate_refs))
    if missing:
        raise SystemExit(f"verified_unsafe_baseline same_output_gate_refs missing gates: {', '.join(missing)}")

    for gate, suffix in C2RUST_VERIFIED_BASELINE_SAME_OUTPUT_GATES.items():
        label = f"verified_unsafe_baseline.same_output_gate_refs.{gate}"
        gate_ref = gate_refs.get(gate)
        if not isinstance(gate_ref, dict):
            raise SystemExit(f"{label} must be an object")
        if gate_ref.get("c2rust_output") != expected_output:
            raise SystemExit(f"{label} c2rust_output drift")
        if expected_compile_artifact is not None and gate_ref.get("compile_artifact") != expected_compile_artifact:
            raise SystemExit(f"{label} compile_artifact drift")
        if gate_ref.get("binding") != "same_c2rust_output":
            raise SystemExit(f"{label} binding must be same_c2rust_output")
        expected_path = evidence_dir / f"{prefix}-{suffix}.json"
        require_ref(gate_ref, expected_path, label, require_sha=gate != "final_verification")


def c2rust_baseline_expected_output_ref(baseline: dict[str, Any]) -> dict[str, Any] | None:
    if baseline.get("status") != "generated":
        return None
    output = baseline.get("output")
    if not isinstance(output, dict):
        return None
    path = output.get("path")
    sha = output.get("sha256")
    if not isinstance(path, str) or not path or not isinstance(sha, str) or not sha:
        return None
    return {"path": path, "status": "generated", "sha256": sha}


def c2rust_baseline_expected_compile_artifact_ref(baseline: dict[str, Any]) -> dict[str, Any] | None:
    compile_status = baseline.get("compile")
    if not isinstance(compile_status, dict) or compile_status.get("status") != "passed":
        return None
    artifact = compile_status.get("artifact")
    if not isinstance(artifact, dict):
        return None
    path = artifact.get("path")
    sha = artifact.get("sha256")
    if not isinstance(path, str) or not path or not isinstance(sha, str) or not sha:
        return None
    return {"path": path, "status": "compiled", "sha256": sha}


def validate_c2rust_baseline_generation_status(
    baseline: dict[str, Any],
    baseline_output: dict[str, Any],
    manifest_path: Path,
) -> None:
    generation = baseline.get("generation")
    if not isinstance(generation, dict):
        raise SystemExit(f"c2rust_baseline generated status requires generation block in {manifest_path}")
    compile_commands = generation.get("compile_commands")
    require_file_ref(compile_commands, "c2rust_baseline.generation.compile_commands")
    command = generation.get("command")
    if not isinstance(command, dict):
        raise SystemExit(f"c2rust_baseline generated status requires generation command in {manifest_path}")
    if command.get("exit_status") != "passed" or command.get("returncode") != 0:
        raise SystemExit(f"c2rust_baseline generation command did not pass in {manifest_path}")
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
        raise SystemExit(f"c2rust_baseline generation command missing argv in {manifest_path}")
    for key in ["stdout_log", "stderr_log"]:
        log_ref = command.get(key)
        if not isinstance(log_ref, str) or not log_ref:
            raise SystemExit(f"c2rust_baseline generation command missing {key} in {manifest_path}")
        log_path = resolve_ref_path(log_ref)
        if not log_path.exists() or not log_path.is_file():
            raise SystemExit(f"c2rust_baseline generation command {key} points to missing file: {log_path}")
    generated_files = generation.get("generated_files")
    if not isinstance(generated_files, list) or not generated_files:
        raise SystemExit(f"c2rust_baseline generated status requires generated_files in {manifest_path}")
    for index, generated_file in enumerate(generated_files):
        require_file_ref(generated_file, f"c2rust_baseline.generation.generated_files[{index}]")
    if baseline_output.get("source_files") != generated_files:
        raise SystemExit(f"c2rust_baseline output.source_files drift from generation.generated_files in {manifest_path}")


def validate_c2rust_baseline_compile_status(
    baseline: dict[str, Any],
    baseline_output: dict[str, Any],
    manifest_path: Path,
) -> None:
    compile_status = baseline.get("compile")
    if not isinstance(compile_status, dict):
        raise SystemExit(f"c2rust_baseline generated status requires compile status in {manifest_path}")
    if compile_status.get("semantic_pass") is not False:
        raise SystemExit(f"c2rust_baseline compile status cannot claim semantic_pass in {manifest_path}")
    candidate_output = compile_status.get("candidate_output")
    if not isinstance(candidate_output, dict):
        raise SystemExit(f"c2rust_baseline compile status missing candidate_output in {manifest_path}")
    expected_candidate_output = {
        "path": str(baseline_output.get("path", "")),
        "status": "generated",
        "sha256": str(baseline_output.get("sha256", "")),
    }
    if candidate_output != expected_candidate_output:
        raise SystemExit(f"c2rust_baseline compile candidate_output drift in {manifest_path}")
    require_file_ref(candidate_output, "c2rust_baseline.compile.candidate_output", require_status=True)
    artifact = compile_status.get("artifact")
    if compile_status.get("status") == "passed":
        require_file_ref(artifact, "c2rust_baseline.compile.artifact", require_status=True)
    elif artifact is not None:
        raise SystemExit(f"c2rust_baseline compile artifact must be null unless compile passed in {manifest_path}")


def validate_global_dependency_requirements(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> None:
    slice_spec = load_json(slice_spec_path)
    expected = global_dependency_requirements(slice_spec)
    expected_names = [item["name"] for item in expected]

    type_map_path = evidence_dir / f"{prefix}-type-map.json"
    context_path = evidence_dir / f"{prefix}-context-pack.json"
    oracle_path = evidence_dir / f"{prefix}-c-oracle-status.json"
    pointer_path = evidence_dir / f"{prefix}-pointer-graph.json"
    cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
    slice_contract_path = evidence_dir / f"{prefix}-slice-contract.json"

    type_map = load_json(type_map_path)
    context = load_json(context_path)
    oracle = load_json(oracle_path)
    pointer = load_json(pointer_path)
    cache = load_json(cache_path)
    slice_contract = load_json(slice_contract_path)

    if not expected:
        reject_unexpected_global_requirements(
            [
                (type_map.get("global_dependencies"), type_map_path, "type_map.global_dependencies"),
                (context.get("global_dependencies"), context_path, "context_pack.global_dependencies"),
                (oracle.get("global_linkage_requirements"), oracle_path, "c_oracle.global_linkage_requirements"),
                (
                    global_dependency_requirements(slice_contract),
                    slice_contract_path,
                    "slice_contract.c_boundary.direct_dependencies",
                ),
                (context.get("source_boundary", {}).get("globals", []), context_path, "source_boundary.globals"),
                (pointer.get("source_boundary", {}).get("globals", []), pointer_path, "source_boundary.globals"),
            ]
        )
        require_empty_global_dependency_identity(cache, cache_path)
        return

    require_global_requirements(type_map.get("global_dependencies"), expected, type_map_path, "type_map.global_dependencies")
    require_global_requirements(context.get("global_dependencies"), expected, context_path, "context_pack.global_dependencies")
    require_global_requirements(
        oracle.get("global_linkage_requirements"),
        expected,
        oracle_path,
        "c_oracle.global_linkage_requirements",
    )
    require_global_requirements(
        global_dependency_requirements(slice_contract),
        expected,
        slice_contract_path,
        "slice_contract.c_boundary.direct_dependencies",
    )

    context_globals = context.get("source_boundary", {}).get("globals", [])
    pointer_globals = pointer.get("source_boundary", {}).get("globals", [])
    require_exact_names(context_globals, expected_names, context_path, "source_boundary.globals")
    require_exact_names(pointer_globals, expected_names, pointer_path, "source_boundary.globals")

    identity = cache.get("global_dependency_identity")
    if not isinstance(identity, dict):
        raise SystemExit(f"global dependency identity missing from {cache_path}")
    identity_names = identity.get("names", [])
    require_exact_names(identity_names, expected_names, cache_path, "global_dependency_identity.names")
    if "global_dependency_identity" not in cache.get("cache_input_fields", []):
        raise SystemExit(f"global dependency identity missing from cache_input_fields in {cache_path}")
    expected_identity_sha = sha256_json(expected)
    if identity.get("count") != len(expected):
        raise SystemExit(f"global dependency identity count mismatch in {cache_path}")
    if identity.get("sha256") != expected_identity_sha:
        raise SystemExit(
            f"global dependency identity sha256 mismatch in {cache_path}: {identity.get('sha256')} != {expected_identity_sha}"
        )

    harness_path = resolve_ref_path(str(oracle.get("harness_draft", "")))
    if not harness_path.exists():
        raise SystemExit(f"global dependency oracle harness draft missing: {harness_path}")
    harness_text = harness_path.read_text(encoding="utf-8")
    for name in expected_names:
        if f"global dependency: {name}" not in harness_text:
            raise SystemExit(f"global dependency {name!r} missing from oracle harness draft {harness_path}")


def global_dependency_requirements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    dependencies = payload.get("c_boundary", {}).get("direct_dependencies", [])
    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dependency in dependencies:
        if dependency.get("kind") != "global":
            continue
        name = str(dependency.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        span = dependency.get("source_span") if isinstance(dependency.get("source_span"), dict) else {
            "file": "slice-spec",
            "line_start": 1,
            "line_end": 1,
        }
        requirements.append(
            {
                "name": name,
                "kind": "global",
                "source": dependency.get("source", "slice_spec"),
                "definition_status": dependency.get("definition_status", "declared"),
                "source_span": span,
                "sha256": dependency.get("sha256") or span.get("sha256") or "",
                "linkage_requirement": "must be available to C oracle harness and Rust replay context",
                "semantic_status": "required_before_acceptance",
            }
        )
    return requirements


def require_global_requirements(value: Any, expected: list[dict[str, Any]], path: Path, label: str) -> None:
    if not isinstance(value, list):
        raise SystemExit(f"global dependency evidence missing {label} in {path}")
    by_name = {str(item.get("name")): item for item in value if isinstance(item, dict) and item.get("name")}
    expected_names = [item["name"] for item in expected]
    actual_names = [str(item.get("name")) for item in value if isinstance(item, dict) and item.get("name")]
    require_exact_names(actual_names, expected_names, path, label)
    for expected_item in expected:
        name = expected_item["name"]
        actual = by_name.get(name)
        if actual is None:
            raise SystemExit(f"global dependency {name!r} missing from {path}:{label}")
        if actual != expected_item:
            raise SystemExit(f"global dependency {name!r} drift in {path}:{label}")


def reject_unexpected_global_requirements(items: list[tuple[Any, Path, str]]) -> None:
    for value, path, label in items:
        if value is None:
            continue
        if isinstance(value, list):
            if value:
                raise SystemExit(f"unexpected global dependency evidence in {path}:{label}")
            continue
        raise SystemExit(f"unexpected global dependency evidence in {path}:{label}")


def require_empty_global_dependency_identity(cache: dict[str, Any], path: Path) -> None:
    identity = cache.get("global_dependency_identity")
    if identity is None:
        return
    expected_identity = {"sha256": sha256_json([]), "count": 0, "names": []}
    if identity != expected_identity:
        raise SystemExit(f"unexpected global dependency identity in {path}")


def require_exact_names(actual_names: Any, expected_names: list[str], path: Path, label: str) -> None:
    if not isinstance(actual_names, list):
        raise SystemExit(f"global dependency evidence missing {label} in {path}")
    if sorted(str(name) for name in actual_names) != sorted(expected_names):
        raise SystemExit(f"global dependency names drift in {path}:{label}")


def l4_refuses_candidate_generation(route: dict[str, Any]) -> bool:
    return (
        route.get("level") == "L4"
        and route.get("status") == "refused"
        and route.get("translator", {}).get("candidate_generation_allowed") is False
    )


def accepted_evidence_authoritative_artifacts_claimed(route: dict[str, Any], auto_manifest: dict[str, Any]) -> bool:
    binding = auto_manifest.get("accepted_evidence_binding", {})
    claim = auto_manifest.get("claim_boundary", {})
    return (
        l4_refuses_candidate_generation(route)
        and route.get("policy", {}).get("accepted_evidence_authoritative") is True
        and route.get("policy", {}).get("generated_draft_semantic_pass") is False
        and binding.get("status") == "accepted"
        and binding.get("generated_draft_semantic_pass") is False
        and claim.get("accepted_evidence_authoritative") is True
        and claim.get("generated_draft_semantic_pass") is False
    )


def accepted_evidence_authoritative_manifest(
    route: dict[str, Any],
    auto_manifest: dict[str, Any],
    slice_spec: dict[str, Any],
) -> bool:
    return (
        slice_spec.get("claim_boundary", {}).get("accepted_evidence_authoritative") is True
        and accepted_evidence_authoritative_artifacts_claimed(route, auto_manifest)
    )


def accepted_evidence_authoritative_semantic_pass(
    route: dict[str, Any],
    profile: dict[str, Any],
    manifest: dict[str, Any],
    final: dict[str, Any],
    slice_spec: dict[str, Any],
) -> bool:
    manifest_claim = manifest.get("claim_boundary", {})
    return (
        slice_spec.get("claim_boundary", {}).get("accepted_evidence_authoritative") is True
        and l4_refuses_candidate_generation(route)
        and route.get("policy", {}).get("accepted_evidence_authoritative") is True
        and route.get("policy", {}).get("generated_draft_semantic_pass") is False
        and profile.get("accepted_evidence_authoritative") is True
        and profile.get("generated_draft_semantic_pass") is False
        and manifest_claim.get("accepted_evidence_authoritative") is True
        and manifest_claim.get("generated_draft_semantic_pass") is False
        and final.get("accepted_evidence_authoritative") is True
        and final.get("generated_draft_semantic_pass") is False
    )


def validate_l4_refused_has_no_candidate_artifact_status(
    evidence_dir: Path,
    prefix: str,
    auto_manifest: dict[str, Any],
    auto_manifest_path: Path,
) -> None:
    documents = [
        (auto_manifest_path, auto_manifest),
        (evidence_dir / f"{prefix}-auto-translation-plan.json", load_json(evidence_dir / f"{prefix}-auto-translation-plan.json")),
        (
            evidence_dir / f"{prefix}-test-translation-generated.json",
            load_json(evidence_dir / f"{prefix}-test-translation-generated.json"),
        ),
        (evidence_dir / f"{prefix}-rust-report.json", load_json(evidence_dir / f"{prefix}-rust-report.json")),
    ]
    for label, payload in documents:
        for path in candidate_status_paths(payload):
            raise SystemExit(f"L4/refused route cannot contain candidate artifact status in {label}:{path}")

    events_path = evidence_dir / f"{prefix}-auto-translation-events.jsonl"
    for line_number, event in enumerate(load_jsonl(events_path), start=1):
        if event.get("event_kind") == "rust_draft_generated" and event.get("status") != "blocked":
            raise SystemExit(
                f"L4/refused route cannot contain candidate artifact status in {events_path}:line {line_number}"
            )
        for path in candidate_status_paths(event):
            raise SystemExit(
                f"L4/refused route cannot contain candidate artifact status in {events_path}:line {line_number}{path}"
            )


def candidate_status_paths(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        if value.get("status") in L4_REFUSED_FORBIDDEN_ARTIFACT_STATUSES:
            hits.append(f"{path}.status")
        for key, child in value.items():
            hits.extend(candidate_status_paths(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(candidate_status_paths(child, f"{path}[{index}]"))
    return hits


def validate_l4_refused_repair_playbook(evidence_dir: Path, prefix: str) -> None:
    blocked_path = evidence_dir / f"{prefix}-self-healing-blocked-repairs.json"
    blocked = load_json(blocked_path)
    repairs = blocked.get("blocked_repairs", [])
    if not repairs:
        return
    if not isinstance(repairs, list):
        raise SystemExit(f"repair playbook requires blocked_repairs list in {blocked_path}")
    required = [
        "ir_feature_gap",
        "oracle_fixture_gap",
        "candidate_routes",
        "smallest_next_test",
        "human_intervention_point",
    ]
    for index, repair in enumerate(repairs):
        if not isinstance(repair, dict):
            raise SystemExit(f"repair playbook item {index} must be an object in {blocked_path}")
        for field in required:
            if field not in repair:
                raise SystemExit(f"repair playbook missing {field} in {blocked_path}:blocked_repairs[{index}]")
        if not isinstance(repair.get("ir_feature_gap"), dict) or not repair["ir_feature_gap"].get("kind"):
            raise SystemExit(f"repair playbook missing ir_feature_gap.kind in {blocked_path}:blocked_repairs[{index}]")
        if not isinstance(repair.get("oracle_fixture_gap"), dict) or not repair["oracle_fixture_gap"].get("status"):
            raise SystemExit(f"repair playbook missing oracle_fixture_gap.status in {blocked_path}:blocked_repairs[{index}]")
        candidate_routes = repair.get("candidate_routes")
        if not isinstance(candidate_routes, list) or not candidate_routes:
            raise SystemExit(f"repair playbook missing candidate_routes in {blocked_path}:blocked_repairs[{index}]")
        route_names = {
            str(route.get("route"))
            for route in candidate_routes
            if isinstance(route, dict) and route.get("route")
        }
        if not {"typed_ir", "c2rust", "llm", "manual"}.issubset(route_names):
            raise SystemExit(
                f"repair playbook candidate_routes must include typed_ir/c2rust/llm/manual in "
                f"{blocked_path}:blocked_repairs[{index}]"
            )
        if not isinstance(repair.get("smallest_next_test"), dict) or not repair["smallest_next_test"].get("kind"):
            raise SystemExit(f"repair playbook missing smallest_next_test.kind in {blocked_path}:blocked_repairs[{index}]")
        intervention = repair.get("human_intervention_point")
        if not isinstance(intervention, str) or not intervention.strip():
            raise SystemExit(
                f"repair playbook missing human_intervention_point in {blocked_path}:blocked_repairs[{index}]"
            )


def ref_expects_existing_artifact(ref: Any) -> bool:
    return isinstance(ref, dict) and str(ref.get("status", "")) != "missing"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def require_ref(ref: Any, expected_path: Path, label: str, *, require_sha: bool = False) -> None:
    if not isinstance(ref, dict) or not ref.get("path"):
        raise SystemExit(f"{label} missing path reference")
    resolved = resolve_ref_path(str(ref["path"]))
    if not resolved.exists():
        raise SystemExit(f"{label} points to missing evidence: {resolved}")
    if resolved.resolve() != expected_path.resolve():
        raise SystemExit(f"{label} path mismatch: {resolved} != {expected_path}")
    ref_sha = ref.get("sha256")
    if require_sha and (not isinstance(ref_sha, str) or not ref_sha):
        raise SystemExit(f"{label} missing sha256")
    if ref_sha and ref_sha != sha256(expected_path):
        raise SystemExit(f"{label} sha256 mismatch: {ref_sha} != {sha256(expected_path)}")
    payload = load_json(expected_path)
    if ref.get("status") and payload.get("status") and ref["status"] != payload["status"]:
        raise SystemExit(f"{label} status mismatch: {ref['status']} != {payload['status']}")


def require_file_ref(ref: Any, label: str, *, require_status: bool = False) -> Path:
    if not isinstance(ref, dict) or not ref.get("path"):
        raise SystemExit(f"{label} missing path reference")
    resolved = resolve_ref_path(str(ref["path"]))
    if not resolved.exists() or not resolved.is_file():
        raise SystemExit(f"{label} points to missing file: {resolved}")
    ref_sha = ref.get("sha256")
    if not isinstance(ref_sha, str) or not ref_sha:
        raise SystemExit(f"{label} missing sha256")
    actual_sha = sha256(resolved)
    if ref_sha != actual_sha:
        raise SystemExit(f"{label} sha256 mismatch: {ref_sha} != {actual_sha}")
    if require_status and (not isinstance(ref.get("status"), str) or not ref.get("status")):
        raise SystemExit(f"{label} missing status")
    return resolved


def resolve_ref_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def validate_semantic_pass(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> dict[str, Any]:
    """Validate the accepted-evidence path that is allowed to claim semantics.

    This is the semantic-pass boundary: manifest, route, validation profile,
    C oracle, Rust report, schema diff, negative diff, unsafe evidence, version
    binding, and final verification all have to agree. Generated draft success
    remains explicitly false even in the returned summary.
    """
    slice_spec = load_json(slice_spec_path)
    manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise SystemExit(f"semantic pass requires manifest.status=passed: {manifest_path}")

    evidence = manifest.get("evidence", {})
    reports = {
        "c2rust_baseline": load_ref(evidence, "c2rust_baseline"),
        "route_decision": load_ref(evidence, "route_decision"),
        "validation_profile": load_ref(evidence, "validation_profile"),
        "c_oracle": load_ref(evidence, "c_oracle"),
        "rust_report": load_ref(evidence, "rust_report"),
        "schema_diff": load_ref(evidence, "schema_diff"),
        "negative_diff": load_ref(evidence, "negative_diff"),
        "unsafe_scan": load_ref(evidence, "unsafe_scan"),
        "unsafe_ledger": load_ref(evidence, "unsafe_ledger"),
        "final_verification": load_ref(evidence, "final_verification"),
        "version_or_config_binding": load_ref(evidence, "version_or_config_binding"),
    }

    if reports["c2rust_baseline"].get("correctness_role") != "candidate_context_only":
        raise SystemExit("semantic pass requires C2Rust baseline to remain candidate_context_only")
    if reports["route_decision"].get("level") == "L4" and not accepted_evidence_authoritative_semantic_pass(
        reports["route_decision"],
        reports["validation_profile"],
        manifest,
        reports["final_verification"],
        slice_spec,
    ):
        raise SystemExit("semantic pass cannot accept L4 refused route")
    require_status(reports["validation_profile"], "validation_profile", {"passed"})
    if reports["validation_profile"].get("skipped_gates"):
        raise SystemExit("semantic pass requires validation_profile.skipped_gates=[]")
    require_status(reports["c_oracle"], "c_oracle", {"C_ORACLE_GENERATED", "passed"})
    if reports["c_oracle"].get("toolchain_status") != "C_ORACLE_GENERATED":
        raise SystemExit("semantic pass requires c_oracle.toolchain_status=C_ORACLE_GENERATED")
    if is_promoted_accepted_oracle_wrapper(reports["c_oracle"]):
        validate_accepted_c_oracle_file_binding(evidence_dir, prefix, reports["c_oracle"])
    require_status(reports["rust_report"], "rust_report", {"passed"})
    require_status(reports["schema_diff"], "schema_diff", {"passed"})
    schema_compared_fields = validate_passed_schema_diff_report(reports["schema_diff"], slice_spec)
    validate_passed_negative_diff_report(reports["negative_diff"], schema_compared_fields)
    require_status(reports["unsafe_scan"], "unsafe_scan", {"passed"})
    require_status(reports["unsafe_ledger"], "unsafe_ledger", {"passed"})
    validate_verified_unsafe_baseline_source(reports["unsafe_scan"], "unsafe_scan", "accepted_unsafe_scan")
    validate_verified_unsafe_baseline_source(reports["unsafe_ledger"], "unsafe_ledger", "accepted_unsafe_ledger")
    require_status(reports["final_verification"], "final_verification", {"passed"})
    if not reports["final_verification"].get("semantic_pass"):
        raise SystemExit("semantic pass requires final_verification.semantic_pass=true")
    require_status(reports["version_or_config_binding"], "version_or_config_binding", {"recorded", "passed"})
    validate_semantic_oracle_boundary_contract(
        reports["validation_profile"].get("oracle_boundary_contract"),
        reports["final_verification"].get("oracle_boundary_contract"),
        slice_spec,
    )

    expected_commit = source_commit(slice_spec)
    for label, report in reports.items():
        report_commit = report.get("source_commit")
        if report_commit and report_commit != expected_commit:
            raise SystemExit(f"semantic pass source_commit mismatch in {label}: {report_commit} != {expected_commit}")

    fixture = reports["final_verification"].get("fixture", {})
    fixture_path = fixture.get("path") or fixture_path_from_spec(slice_spec)
    fixture_file = REPO_ROOT / fixture_path
    if fixture_file.exists() and fixture.get("sha256"):
        actual = sha256(fixture_file)
        if fixture["sha256"] != actual:
            raise SystemExit(f"semantic pass fixture sha256 mismatch: {fixture['sha256']} != {actual}")

    validate_external_direct_callee_context(slice_spec, evidence_dir, prefix, manifest, reports["final_verification"])

    return {
        "status": "passed",
        "semantic_pass": True,
        "semantic_claim_source": "accepted_evidence_binding",
        "generated_draft_semantic_pass": False,
        "manifest": rel(manifest_path),
        "source_commit": expected_commit,
        "fixture_path": fixture_path,
        "fixture_sha256": fixture.get("sha256"),
        "checked": sorted(reports),
    }


def validate_verified_unsafe_baseline_source(report: dict[str, Any], label: str, accepted_ref_key: str) -> None:
    source = report.get("semantic_claim_source")
    if source is None:
        if isinstance(report.get(accepted_ref_key), dict):
            return
        if isinstance(report.get("verified_unsafe_baseline"), dict):
            return
        return
    if source in FORBIDDEN_UNSAFE_SEMANTIC_CLAIM_SOURCES:
        raise SystemExit(f"semantic pass rejects {label}.semantic_claim_source={source}")
    if source not in ALLOWED_UNSAFE_SEMANTIC_CLAIM_SOURCES:
        allowed = sorted(ALLOWED_UNSAFE_SEMANTIC_CLAIM_SOURCES)
        raise SystemExit(f"semantic pass requires {label}.semantic_claim_source in {allowed}, got {source!r}")
    if source == "accepted_evidence_binding" and not isinstance(report.get(accepted_ref_key), dict):
        raise SystemExit(f"semantic pass requires {label}.{accepted_ref_key} for accepted_evidence_binding")
    if source == "verified_unsafe_baseline_gates" and not isinstance(report.get("verified_unsafe_baseline"), dict):
        raise SystemExit(f"semantic pass requires {label}.verified_unsafe_baseline for verified_unsafe_baseline_gates")


def validate_semantic_oracle_boundary_contract(
    profile_contract: Any,
    final_contract: Any,
    slice_spec: dict[str, Any],
) -> None:
    if not isinstance(profile_contract, dict):
        raise SystemExit("semantic pass oracle boundary contract missing from validation_profile")
    if not isinstance(final_contract, dict):
        raise SystemExit("semantic pass oracle boundary contract missing from final_verification")
    if final_contract != profile_contract:
        raise SystemExit("semantic pass oracle boundary contract drift between validation_profile and final_verification")
    if profile_contract.get("status") != "sufficient_for_semantic_pass":
        raise SystemExit("semantic pass oracle boundary contract must be sufficient_for_semantic_pass")

    observable_outputs = require_string_list(
        profile_contract.get("observable_outputs"),
        "semantic pass oracle boundary contract observable_outputs missing",
    )
    expected_outputs = behavior_fields_from_spec(slice_spec)
    if expected_outputs and not set(expected_outputs).issubset(set(observable_outputs)):
        raise SystemExit("semantic pass oracle boundary contract observable_outputs missing behavior fields")

    fixture = require_dict(
        profile_contract.get("fixture_representativeness"),
        "semantic pass oracle boundary contract fixture_representativeness missing",
    )
    declared_case_count = fixture.get("declared_case_count")
    accepted_case_count = fixture.get("accepted_oracle_case_count")
    if not positive_int_like(declared_case_count):
        raise SystemExit("semantic pass oracle boundary contract declared_case_count missing")
    if not positive_int_like(accepted_case_count):
        raise SystemExit("semantic pass oracle boundary contract accepted_oracle_case_count missing")
    if accepted_case_count < declared_case_count:
        raise SystemExit("semantic pass oracle boundary contract accepted_oracle_case_count below declared")

    compiler = require_dict(profile_contract.get("compiler"), "semantic pass oracle boundary contract compiler missing")
    if missing_boundary_value(compiler.get("command_source")):
        raise SystemExit("semantic pass oracle boundary contract compiler command_source missing")

    target = require_dict(profile_contract.get("target"), "semantic pass oracle boundary contract target missing")
    if missing_boundary_value(target.get("triple_or_abi")):
        raise SystemExit("semantic pass oracle boundary contract target.triple_or_abi missing")
    if missing_boundary_value(target.get("endianness")) or target.get("endianness") not in {"little", "big"}:
        raise SystemExit("semantic pass oracle boundary contract target.endianness missing")
    for key in ["int_width", "long_width", "pointer_width", "word_size_bits"]:
        if missing_boundary_value(target.get(key)):
            raise SystemExit(f"semantic pass oracle boundary contract target.{key} missing")
        if not positive_int_like(target.get(key)):
            raise SystemExit(f"semantic pass oracle boundary contract target.{key} invalid")
    for key in [
        "char_width",
        "short_width",
        "long_long_width",
        "int_align",
        "char_align",
        "short_align",
        "long_align",
        "long_long_align",
        "pointer_align",
    ]:
        if not missing_boundary_value(target.get(key)) and not positive_int_like(target.get(key)):
            raise SystemExit(f"semantic pass oracle boundary contract target.{key} invalid")
    if (
        not missing_boundary_value(target.get("plain_char_signed"))
        and not isinstance(target.get("plain_char_signed"), bool)
    ):
        raise SystemExit("semantic pass oracle boundary contract target.plain_char_signed invalid")

    sanitizer = require_dict(
        profile_contract.get("sanitizer_diagnostics"),
        "semantic pass oracle boundary contract sanitizer_diagnostics missing",
    )
    if missing_boundary_value(sanitizer.get("sanitizer_status"), allow_not_run=True):
        raise SystemExit("semantic pass oracle boundary contract sanitizer_status missing")

    ub = require_dict(
        profile_contract.get("ub_and_implementation_defined"),
        "semantic pass oracle boundary contract ub_and_implementation_defined missing",
    )
    if not isinstance(ub.get("known_ub"), list):
        raise SystemExit("semantic pass oracle boundary contract known_ub missing")
    if not isinstance(ub.get("implementation_defined_behavior"), list):
        raise SystemExit("semantic pass oracle boundary contract implementation_defined_behavior missing")

    platform = require_dict(
        profile_contract.get("platform_model"),
        "semantic pass oracle boundary contract platform_model missing",
    )
    for key in ["hardware_dependency_status", "rtos_dependency_status", "volatile_dependency_status"]:
        if missing_boundary_value(platform.get(key)) or platform.get(key) == "unmodeled":
            raise SystemExit(f"semantic pass oracle boundary contract platform_model.{key} missing")


def require_dict(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(message)
    return value


def missing_boundary_value(value: Any, allow_not_run: bool = False) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        if allow_not_run and value == "not_run":
            return False
        return value.strip() in {"", "unknown", "not_recorded", "missing"}
    return False


def positive_int_like(value: Any) -> bool:
    return isinstance(value, int) and value > 0


def validate_accepted_c_oracle_file_binding(evidence_dir: Path, prefix: str, c_oracle: dict[str, Any]) -> None:
    accepted = c_oracle.get("accepted_oracle")
    if not isinstance(accepted, dict):
        raise SystemExit("semantic pass accepted c_oracle reference missing")

    accepted_path = accepted.get("path")
    if not isinstance(accepted_path, str) or not accepted_path:
        raise SystemExit("semantic pass accepted c_oracle accepted_oracle.path missing")
    accepted_sha = accepted.get("sha256")
    if not isinstance(accepted_sha, str) or not accepted_sha:
        raise SystemExit("semantic pass accepted c_oracle accepted_oracle.sha256 missing")
    if accepted.get("status") != "passed":
        raise SystemExit("semantic pass accepted c_oracle accepted_oracle.status must be passed")

    auto_manifest_path = evidence_dir / f"{prefix}-auto-translation-manifest.json"
    auto_manifest = load_json(auto_manifest_path)
    binding = auto_manifest.get("accepted_evidence_binding")
    if not isinstance(binding, dict):
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding missing")
    paths = binding.get("paths")
    if not isinstance(paths, dict):
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.paths missing")
    path_sha256 = binding.get("path_sha256")
    if not isinstance(path_sha256, dict):
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.path_sha256 missing")

    binding_path = paths.get("c_oracle")
    if not isinstance(binding_path, str) or not binding_path:
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.paths.c_oracle missing")
    binding_sha = path_sha256.get("c_oracle")
    if not isinstance(binding_sha, str) or not binding_sha:
        raise SystemExit("semantic pass accepted c_oracle accepted_evidence_binding.path_sha256.c_oracle missing")

    accepted_resolved = resolve_ref_path(accepted_path)
    binding_resolved = resolve_ref_path(binding_path)
    if not accepted_resolved.exists():
        raise SystemExit(f"semantic pass accepted c_oracle points to missing evidence: {accepted_resolved}")
    if not binding_resolved.exists():
        raise SystemExit(f"semantic pass accepted c_oracle binding points to missing evidence: {binding_resolved}")
    if accepted_resolved.resolve() != binding_resolved.resolve():
        raise SystemExit(
            f"semantic pass accepted c_oracle path mismatch: {accepted_resolved} != {binding_resolved}"
        )

    actual_sha = sha256(accepted_resolved)
    if accepted_sha != actual_sha:
        raise SystemExit(f"semantic pass accepted c_oracle accepted_oracle.sha256 mismatch: {accepted_sha} != {actual_sha}")
    if binding_sha != actual_sha:
        raise SystemExit(
            "semantic pass accepted c_oracle accepted_evidence_binding.path_sha256.c_oracle mismatch: "
            f"{binding_sha} != {actual_sha}"
        )


def validate_external_direct_callee_context(
    slice_spec: dict[str, Any],
    evidence_dir: Path,
    prefix: str,
    manifest: dict[str, Any],
    final_verification: dict[str, Any],
) -> None:
    """Validate compile-only boundaries for external direct callees.

    Declared active callees must bind slice-spec signatures, real source files,
    context-pack descriptors, and translation-plan call edges. These stubs are
    allowed to support compilation context, but they must not claim verified
    semantics or silently widen the final verification scope.
    """
    declared = slice_spec.get("c_boundary", {}).get("external_direct_callees", [])
    if not declared:
        return

    declared_by_name = {str(item.get("name")): item for item in declared if item.get("name")}
    signatures = {
        str(item.get("id") or item.get("function")): item
        for item in slice_spec.get("c_boundary", {}).get("signatures", [])
        if item.get("id") or item.get("function")
    }
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    context_path = evidence_dir / f"{prefix}-context-pack.json"
    plan = load_json(plan_path)
    context = load_json(context_path)
    plan_callees = {
        str(item.get("name")): item
        for item in plan.get("translation_summary", {}).get("external_direct_callees", [])
        if item.get("name")
    }
    context_callees = {
        str(item.get("name")): item
        for item in context.get("external_direct_callees", [])
        if item.get("name")
    }
    plan_blocks = {
        str(item.get("name")): item
        for item in plan.get("translation_summary", {}).get("external_direct_callee_blocks", [])
        if item.get("name")
    }
    context_blocks = {
        str(item.get("name")): item
        for item in context.get("external_direct_callee_blocks", [])
        if item.get("name")
    }
    bindings: dict[str, list[dict[str, Any]]] = {}
    for item in context.get("signature_bindings", []):
        if item.get("callee"):
            bindings.setdefault(str(item.get("callee")), []).append(item)
    source_bindings: dict[str, list[dict[str, Any]]] = {}
    for item in context.get("callee_sources", []):
        if item.get("callee"):
            source_bindings.setdefault(str(item.get("callee")), []).append(item)
    call_bindings = [
        item
        for item in context.get("call_edge_to_callee_binding", [])
        if item.get("callee") in declared_by_name
    ]
    plan_call_edges = [
        item
        for item in plan.get("translation_summary", {}).get("call_expressions", [])
        if item.get("callee") in declared_by_name
    ]
    context_call_edges = [
        item
        for item in context.get("direct_call_edges", [])
        if item.get("callee") in declared_by_name
    ]
    contracts: dict[str, dict[str, Any]] = {}
    blocked_contracts: dict[str, dict[str, Any]] = {}
    active_names = {
        str(item.get("callee") or item.get("name"))
        for item in (
            plan_call_edges
            + context_call_edges
            + call_bindings
            + list(plan_callees.values())
            + list(context_callees.values())
            + list(plan_blocks.values())
            + list(context_blocks.values())
        )
        if item.get("callee") or item.get("name")
    }

    for name, declared_callee in declared_by_name.items():
        if name not in active_names:
            continue
        signature_ref = str(declared_callee.get("signature_ref") or "")
        if signature_ref not in signatures:
            raise SystemExit(f"external callee {name} signature_ref missing from slice spec signatures")
        if not declared_callee.get("source_files"):
            raise SystemExit(f"external callee {name} requires real source_files in slice spec")
        signature = signatures[signature_ref]
        contract = external_callee_expected_contract(name, declared_callee, signature)
        if name in plan_blocks or name in context_blocks:
            validate_external_callee_block_binding(
                name,
                plan_blocks.get(name),
                context_blocks.get(name),
            )
            blocked_contracts[name] = {
                **contract,
                "blocked_reason": str((plan_blocks.get(name) or context_blocks.get(name) or {}).get("reason") or ""),
            }
            if any(item.get("callee") == name for item in call_bindings):
                raise SystemExit(f"external callee {name} blocked call-site cannot have compile_only binding")
            continue
        plan_callee = plan_callees.get(name)
        if plan_callee is None:
            raise SystemExit(f"external callee {name} missing from translation plan")
        context_callee = context_callees.get(name)
        if context_callee is None:
            raise SystemExit(f"external callee {name} missing from context pack")
        if plan_callee.get("signature_ref") != signature_ref:
            raise SystemExit(f"external callee {name} signature_ref mismatch in translation plan")
        if context_callee.get("signature_ref") != signature_ref:
            raise SystemExit(f"external callee {name} signature_ref mismatch in context pack")
        validate_external_callee_signature_descriptor(name, signature, plan_callee, "translation plan")
        validate_external_callee_signature_descriptor(name, signature, context_callee, "context pack")
        stub_kind = str(plan_callee.get("stub_kind") or "")
        if stub_kind != str(context_callee.get("stub_kind") or ""):
            raise SystemExit(f"external callee {name} stub_kind mismatch between translation plan and context pack")
        contract["stub_kind"] = stub_kind
        contracts[name] = contract
        validate_external_callee_descriptor_binding(name, contract, plan_callee, "translation plan")
        validate_external_callee_descriptor_binding(name, contract, context_callee, "context pack")
        if stub_kind not in {"compile_only", "accepted_named_slice_evidence"}:
            raise SystemExit(f"external callee {name} has unsupported stub_kind={stub_kind}")
        if stub_kind == "accepted_named_slice_evidence":
            validate_external_callee_accepted_named_slice_evidence(name, plan_callee, context_callee)
        if plan_callee.get("semantics_verified") or context_callee.get("semantics_verified"):
            raise SystemExit(f"external callee {name} context must not claim semantics_verified")
        if len(bindings.get(name, [])) != 1:
            raise SystemExit(f"external callee {name} missing signature binding in context pack")
        validate_external_callee_signature_binding(name, signature_ref, bindings[name][0])
        if not source_bindings.get(name):
            raise SystemExit(f"external callee {name} missing callee source binding in context pack")
        validate_external_callee_source_bindings(name, contract, source_bindings[name])

    recorded_plan_call_edges = [edge for edge in plan_call_edges if edge.get("callee") in contracts]
    recorded_context_call_edges = [edge for edge in context_call_edges if edge.get("callee") in contracts]
    if recorded_plan_call_edges and not call_bindings:
        raise SystemExit("external callee context requires call_edge_to_callee_binding entries")
    if recorded_plan_call_edges or recorded_context_call_edges or call_bindings:
        validate_external_callee_call_site_bindings(
            contracts,
            recorded_plan_call_edges,
            recorded_context_call_edges,
            call_bindings,
        )
    validate_external_callee_blocked_call_sites(blocked_contracts, plan_call_edges, context_call_edges)

    claim_scope = manifest.get("claim_boundary", {}).get("external_callee_scope", {})
    final_scope = final_verification.get("external_callee_scope", claim_scope)
    expected_scope_stub_kind = external_callee_scope_stub_kind(contracts.values())
    for label, scope in [("manifest", claim_scope), ("final_verification", final_scope)]:
        if scope.get("stub_kind") != expected_scope_stub_kind:
            raise SystemExit(f"external callee {label} scope must record stub_kind={expected_scope_stub_kind}")
        if scope.get("semantics_verified"):
            raise SystemExit(f"external callee {label} scope must keep semantics_verified=false")
