def c2rust_command_candidates() -> list[dict[str, Any]]:
    explicit = c2rust_explicit_command_candidate()
    names = ["c2rust-transpile", "c2rust"]
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    for name in names:
        path = shutil.which(name)
        version = c2rust_command_version(path) if path else {"version_status": "NOT_FOUND", "version": ""}
        candidates.append({"name": name, "path": path or "", "available": bool(path), **version})
    return candidates


def c2rust_explicit_command_candidate() -> dict[str, Any] | None:
    configured = os.environ.get("C2RUST_COMMAND", "").strip()
    if not configured:
        return None
    try:
        argv_prefix = shlex.split(configured, posix=(os.name != "nt"))
    except ValueError as exc:
        return {
            "name": "C2RUST_COMMAND",
            "path": "",
            "available": False,
            "source": "env:C2RUST_COMMAND",
            "configured_command": configured,
            "argv_prefix": [],
            "version_status": "ERROR",
            "version": "",
            "version_error": str(exc),
        }
    if not argv_prefix:
        return None
    executable = argv_prefix[0]
    resolved = shutil.which(executable) or (executable if Path(executable).exists() else "")
    available = bool(resolved)
    version = c2rust_command_version(argv_prefix) if available else {"version_status": "NOT_FOUND", "version": ""}
    return {
        "name": c2rust_command_name_from_argv(argv_prefix),
        "path": executable if available else "",
        "available": available,
        "source": "env:C2RUST_COMMAND",
        "configured_command": configured,
        "argv_prefix": argv_prefix,
        **version,
    }


def c2rust_command_name_from_argv(argv_prefix: list[str]) -> str:
    command_name = Path(argv_prefix[-1]).name
    if command_name.lower().endswith(".exe"):
        command_name = command_name[:-4]
    if command_name in {"c2rust", "c2rust-transpile"}:
        return command_name
    return command_name or "C2RUST_COMMAND"


def c2rust_command_version(command: str | list[str] | None) -> dict[str, str]:
    if not command:
        return {"version_status": "NOT_FOUND", "version": ""}
    argv = [command] if isinstance(command, str) else list(command)
    try:
        result = subprocess.run(
            [*argv, "--version"],
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        return {"version_status": "ERROR", "version": "", "version_error": str(exc)}
    version = (result.stdout or result.stderr).strip()
    return {
        "version_status": "OK" if result.returncode == 0 and version else "UNKNOWN",
        "version": version,
    }


def c2rust_toolchain_repair(reason: str, *, slice_spec: Path) -> dict[str, Any]:
    rerun_env = {"C2RUST_BASELINE_GENERATION": "1"}
    configured_command = os.environ.get("C2RUST_COMMAND", "").strip()
    if configured_command:
        rerun_env["C2RUST_COMMAND"] = configured_command
    return {
        "status": "required",
        "reason": reason,
        "required_commands": ["c2rust-transpile", "c2rust"],
        "required_dependencies": ["rustc", "cargo", "clang", "libclang"],
        "competition_environment": {
            "profile": "config/competition-env/environment.json",
                "proof_class": "local_or_wsl_until_competition_run",
            },
        "rerun_env": rerun_env,
        "rerun_command": [
            "python3",
            "-B",
            "-m",
            "validation.tools.auto_migrate",
            "--slice-spec",
            rel(slice_spec),
            "--out-root",
            "validation/evidence",
        ],
        "correctness_role": "candidate_context_only",
        "must_not_claim": [
            "toolchain repair proves C2Rust generated output",
            "compile-only C2Rust output proves semantic equivalence",
        ],
    }


def resolve_c2rust_reference_tree() -> tuple[Path, bool]:
    configured = os.environ.get("C2RUST_REFERENCE_TREE", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path, True
    return REPO_ROOT / "tools" / "c2rust-reference", False


def c2rust_tool_probe() -> dict[str, Any]:
    return {
        "os_name": os.name,
        "path_search": ["c2rust-transpile", "c2rust"],
        "probed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diagnostic_only": True,
        "environment_profile_hash": sha256(COMPETITION_ENVIRONMENT_PROFILE)
        if COMPETITION_ENVIRONMENT_PROFILE.exists()
        else "missing",
        "competition_environment_identity": competition_environment_identity()
        if COMPETITION_ENVIRONMENT_PROFILE.exists()
        else {"status": "missing"},
    }


def emit_route_decision(
    spec: dict[str, Any],
    evidence_dir: Path,
    translator_summary: dict[str, Any],
    c2rust_baseline: dict[str, Any],
) -> dict[str, Any]:
    """Emit the route/profile decision and candidate provenance bundle.

    The route chooses which verification profile must later pass; it does not
    accept a generated draft. The candidate set records primary, typed-IR, and
    C2Rust-baseline inputs with semantic flags pinned false so downstream
    validators can reject candidate evidence that tries to act like accepted
    evidence.
    """
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    type_map = read_json(evidence_dir / f"{prefix}-type-map.json")
    cfg = read_json(evidence_dir / f"{prefix}-cfg.json")
    pointer = read_json(evidence_dir / f"{prefix}-pointer-graph.json")
    plan = read_json(evidence_dir / f"{prefix}-auto-translation-plan.json")
    c2rust_baseline_artifact = c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline)
    candidate_generation = candidate_generation_evidence(
        spec,
        evidence_dir,
        c2rust_baseline,
        baseline_manifest_ref=c2rust_baseline_artifact,
    )
    level, rationale = route_level(spec, translator_summary, type_map, cfg, pointer, plan, candidate_generation)
    translator = route_translator(level)
    route_status = "refused" if level == "L4" else "recorded"
    candidate_generation["governance_summary"] = route_governance_summary(
        candidate_generation,
        level=level,
        route_status=route_status,
        translator=translator,
    )
    profile = validation_profile_name(level, "dev")
    source_artifacts = {
        "type_map": evidence_ref(evidence_dir / f"{prefix}-type-map.json", type_map.get("status", "recorded")),
        "cfg": evidence_ref(evidence_dir / f"{prefix}-cfg.json", cfg.get("status", "recorded")),
        "pointer_graph": evidence_ref(evidence_dir / f"{prefix}-pointer-graph.json", pointer.get("status", "recorded")),
        "c2rust_baseline": c2rust_baseline_artifact,
    }
    typed_ir_source_artifact = candidate_generation.get("typed_ir", {}).get("source_artifact")
    if isinstance(typed_ir_source_artifact, dict) and typed_ir_source_artifact.get("status") != "missing":
        source_artifacts["clang_lowering_report"] = typed_ir_source_artifact
    translation_plan_ref = evidence_ref(
        evidence_dir / f"{prefix}-auto-translation-plan.json",
        plan.get("status", "recorded"),
    )
    # The plan is later bound back to this route decision, so its content hash is not stable here.
    translation_plan_ref.pop("sha256", None)
    source_artifacts["translation_plan"] = translation_plan_ref
    decision = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "source_commit": source_commit(spec),
        "source_identity": source_identity(spec),
        "status": route_status,
        "level": level,
        "translator": translator,
        "rationale": rationale,
        "verification_profile": profile,
        "source_artifacts": source_artifacts,
        "candidate_generation": candidate_generation,
        "scalar_ub_contract": scalar_ub_contract(spec),
        "policy": {
            "goal": "dev",
            "fixed_loop_count_required": False,
            "repair_budget_source": "run_policy",
        },
        "misroute": None,
    }
    write_json(evidence_dir / f"{prefix}-route-decision.json", decision)
    return decision


def candidate_generation_evidence(
    spec: dict[str, Any],
    evidence_dir: Path,
    c2rust_baseline: dict[str, Any] | None = None,
    *,
    baseline_manifest_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    if baseline_manifest_ref is None:
        baseline_manifest_ref = c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline)
    report_path = evidence_dir / f"{prefix}-clang-lowering-report.json"
    plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
    plan = read_json(plan_path) if plan_path.exists() else {}
    primary_candidate = primary_candidate_binding(plan)
    compatibility_sources = compatibility_source_bindings(plan)
    typed_ir_candidate = typed_ir_candidate_binding(report_path)
    typed_ir_candidate["scalar_admission"] = scalar_admission_from_runtime_preconditions(
        spec,
        typed_ir_candidate.get("runtime_preconditions", []),
    )
    c2rust_candidate = c2rust_baseline_candidate_binding(
        c2rust_baseline,
        baseline_manifest_ref=baseline_manifest_ref,
    )
    return {
        "selection_policy": candidate_selection_policy(),
        "selected_candidate_id": selected_candidate_id(primary_candidate),
        "candidate_set": candidate_set_binding(
            primary_candidate,
            compatibility_sources,
            typed_ir_candidate,
            c2rust_candidate,
        ),
        "compatibility_sources": compatibility_sources,
        "primary_candidate": primary_candidate,
        "typed_ir": typed_ir_candidate,
        "c2rust_baseline": c2rust_candidate,
        "generated_draft_semantic_pass": False,
    }


def primary_candidate_binding(plan: dict[str, Any]) -> dict[str, Any]:
    source = translation_source_from_plan(plan)
    if source["selected"] == "legacy-string-translator":
        return {
            "candidate_id": "primary:unknown",
            "selected": "unknown",
            "fallback": False,
            "semantic_pass": False,
        }
    candidate_prefix = "primary"
    binding: dict[str, Any] = {
        "candidate_id": f"{candidate_prefix}:{source['selected']}",
        "selected": source["selected"],
        "fallback": bool(source.get("fallback_from")),
        "semantic_pass": False,
    }
    if source.get("fallback_from"):
        binding["fallback_from"] = source["fallback_from"]
    if source.get("fallback_reason"):
        binding["fallback_reason"] = source["fallback_reason"]
    return binding


def compatibility_source_bindings(plan: dict[str, Any]) -> list[dict[str, Any]]:
    source = translation_source_from_plan(plan)
    if source["selected"] != "legacy-string-translator":
        return []
    binding: dict[str, Any] = {
        "candidate_id": "compat:legacy-string-translator",
        "selected": "legacy-string-translator",
        "fallback": bool(source.get("fallback_from")),
        "semantic_pass": False,
        "compatibility_only": True,
        "correctness_role": "compatibility_only",
    }
    if source.get("fallback_from"):
        binding["fallback_from"] = source["fallback_from"]
    if source.get("fallback_reason"):
        binding["fallback_reason"] = source["fallback_reason"]
    return [binding]


def candidate_selection_policy() -> dict[str, Any]:
    return {
        "stage": "p0_route_governance",
        "selection_basis": "translator_artifact_primary_candidate",
        "semantic_acceptance": False,
        "full_router": False,
    }


def route_governance_summary(
    candidate_generation: dict[str, Any],
    *,
    level: str,
    route_status: str,
    translator: dict[str, Any],
) -> dict[str, Any]:
    compatibility_sources = candidate_generation.get("compatibility_sources", [])
    legacy_source = next(
        (
            source
            for source in compatibility_sources
            if isinstance(source, dict) and source.get("selected") == "legacy-string-translator"
        ),
        None,
    )
    legacy_summary: dict[str, Any] = {
        "status": "not_used",
        "selected_as_primary": False,
    }
    if legacy_source is not None:
        legacy_summary = {
            "status": "compatibility_only",
            "candidate_id": legacy_source.get("candidate_id", "compat:legacy-string-translator"),
            "selected_as_primary": False,
            "fallback": bool(legacy_source.get("fallback")),
        }
        if legacy_source.get("fallback_from"):
            legacy_summary["fallback_from"] = legacy_source["fallback_from"]
        if legacy_source.get("fallback_reason"):
            legacy_summary["fallback_reason"] = legacy_source["fallback_reason"]

    return {
        "schema_version": 1,
        "stage": "p0_route_governance",
        "route_level": level,
        "route_status": route_status,
        "candidate_generation_allowed": bool(translator.get("candidate_generation_allowed")),
        "semantic_acceptance": False,
        "full_router": False,
        "hard_gates": [
            {
                "gate_id": "generated_candidate_semantic_acceptance",
                "status": "deferred",
                "reason": "generated candidates require accepted validation evidence",
            },
            {
                "gate_id": "legacy_string_translator_primary_selection",
                "status": "forbidden",
                "reason": "legacy string translator is compatibility-only",
            },
            {
                "gate_id": "c2rust_baseline_semantic_source",
                "status": "forbidden",
                "reason": "C2Rust baseline remains candidate_context_only",
            },
        ],
        "fallback_summary": {
            "legacy_string_translator": legacy_summary,
        },
        "refusal_summary": {
            "status": "refused" if level == "L4" else "not_refused",
            "route_level": level,
        },
        "validation_gate_summary": {
            "generated_draft_semantic_pass": False,
            "required_acceptance_gates": [
                "c_oracle",
                "rust_replay",
                "schema_diff",
                "negative_diff",
                "unsafe_ledger",
                "final_verification",
            ],
            "semantic_claim_source": "accepted_evidence_binding_or_common_validation_pipeline",
        },
        "drift_inputs": [
            "route_decision.candidate_generation",
            "validation_profile.candidate_generation",
            "c2rust_baseline_manifest",
            "auto_cache_metadata.dependent_artifacts",
        ],
    }


def selected_candidate_id(primary_candidate: dict[str, Any]) -> str | None:
    if primary_candidate.get("selected") == "unknown":
        return None
    if primary_candidate.get("compatibility_only") is True:
        return None
    return str(primary_candidate.get("candidate_id"))


def candidate_set_binding(
    primary_candidate: dict[str, Any],
    compatibility_sources: list[dict[str, Any]],
    typed_ir_candidate: dict[str, Any],
    c2rust_candidate: dict[str, Any],
) -> list[dict[str, Any]]:
    selected = str(primary_candidate.get("selected", "unknown"))
    primary_status = "missing" if selected == "unknown" else "generated"
    primary = {
        "candidate_id": primary_candidate.get("candidate_id", "primary:unknown"),
        "kind": selected,
        "status": primary_status,
        "role": "compatibility_rust_draft"
        if primary_candidate.get("compatibility_only") is True
        else "primary_rust_draft",
        "semantic_pass": False,
    }
    if primary_candidate.get("compatibility_only") is True:
        primary["compatibility_only"] = True
        primary["correctness_role"] = "compatibility_only"
    if primary_candidate.get("fallback"):
        primary["fallback"] = True
    if primary_candidate.get("fallback_from"):
        primary["fallback_from"] = primary_candidate["fallback_from"]
    if primary_candidate.get("fallback_reason"):
        primary["fallback_reason"] = primary_candidate["fallback_reason"]
    candidates = []
    if selected != "unknown":
        candidates.append(primary)
    candidates.extend(compatibility_candidate_set_items(compatibility_sources))
    candidates.extend(
        [
            {
            "candidate_id": "typed-ir:clang-lowered",
            "kind": "typed-ir",
            "status": typed_ir_candidate.get("status", "missing"),
            "role": "typed_ir_candidate_signal",
            "rust_draft_generated": bool(typed_ir_candidate.get("rust_draft_generated", False)),
            "semantic_pass": False,
        },
            c2rust_candidate,
        ]
    )
    return candidates


def compatibility_candidate_set_items(compatibility_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for source in compatibility_sources:
        selected = str(source.get("selected", "unknown"))
        item = {
            "candidate_id": source.get("candidate_id", f"compat:{selected}"),
            "kind": selected,
            "status": "generated" if selected != "unknown" else "missing",
            "role": "compatibility_rust_draft",
            "semantic_pass": False,
            "compatibility_only": True,
            "correctness_role": "compatibility_only",
        }
        if source.get("fallback"):
            item["fallback"] = True
        if source.get("fallback_from"):
            item["fallback_from"] = source["fallback_from"]
        if source.get("fallback_reason"):
            item["fallback_reason"] = source["fallback_reason"]
        items.append(item)
    return items


def c2rust_baseline_candidate_binding(
    c2rust_baseline: dict[str, Any] | None,
    *,
    baseline_manifest_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = c2rust_baseline or {}
    status = str(baseline.get("status", "missing"))
    binding = {
        "candidate_id": "c2rust-baseline",
        "kind": "c2rust-baseline",
        "status": status,
        "role": "baseline_or_repair_candidate_context",
        "correctness_role": str(baseline.get("correctness_role", "candidate_context_only")),
        "reason": str(baseline.get("reason", "missing")),
        "output_ref": c2rust_baseline_output_ref(baseline, status),
        "generated_draft_semantic_pass": False,
        "semantic_pass": False,
    }
    if baseline_manifest_ref is not None:
        binding["baseline_manifest"] = baseline_manifest_ref
    return binding


def c2rust_baseline_output_ref(baseline: dict[str, Any], status: str) -> dict[str, Any] | None:
    output = baseline.get("output")
    if not isinstance(output, dict):
        return None
    path = output.get("path")
    output_sha = output.get("sha256")
    if not path or not output_sha:
        return None
    return {
        "path": str(path),
        "status": status,
        "sha256": str(output_sha),
    }


def c2rust_baseline_compile_artifact_ref(baseline: dict[str, Any]) -> dict[str, Any] | None:
    compile_status = baseline.get("compile")
    if not isinstance(compile_status, dict):
        return None
    artifact = compile_status.get("artifact")
    if not isinstance(artifact, dict):
        return None
    path = artifact.get("path")
    artifact_sha = artifact.get("sha256")
    if not path or not artifact_sha:
        return None
    return {
        "path": str(path),
        "status": str(artifact.get("status") or compile_status.get("status") or "unknown"),
        "sha256": str(artifact_sha),
    }


def c2rust_generated_crate_name(cargo_toml: Path) -> str | None:
    if not cargo_toml.exists() or not cargo_toml.is_file():
        return None
    current_section = ""
    package_name: str | None = None
    lib_name: str | None = None
    for raw_line in cargo_toml.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line.strip("[]").strip()
            continue
        match = re.fullmatch(r'name\s*=\s*"([^"]+)"', line)
        if match is None:
            continue
        if current_section == "package" and package_name is None:
            package_name = match.group(1)
        elif current_section == "lib" and lib_name is None:
            lib_name = match.group(1)
    crate_name = lib_name or package_name
    if crate_name is None:
        return None
    return safe_ident(crate_name)


def path_from_evidence_text(path_text: Any) -> Path:
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def relative_path_for_toml(path: Path, start: Path) -> str:
    try:
        return Path(os.path.relpath(path.resolve(), start=start.resolve())).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def direct_c2rust_replay_cases(spec: dict[str, Any]) -> tuple[list[dict[str, Any]], Path | None, str]:
    fixture_path_text = fixture_path(spec)
    fixture_file = path_from_evidence_text(fixture_path_text)
    if not fixture_file.exists() or not fixture_file.is_file():
        return [], None, "fixture_missing"
    payload = read_json(fixture_file)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        return [], fixture_file, "fixture_cases_missing"
    normalized: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, dict):
            return [], fixture_file, "fixture_case_not_object"
        case_id = str(raw_case.get("id") or f"case-{index}")
        crc = raw_case.get("crc")
        buf = raw_case.get("buf")
        size = raw_case.get("size")
        expected = raw_case.get("return_code")
        if not is_uint32_value(crc) or not is_uint32_value(expected):
            return [], fixture_file, "fixture_case_uint32_unsupported"
        if not is_size_value(size) or not is_byte_list(buf) or int(size) != len(buf):
            return [], fixture_file, "fixture_case_buffer_unsupported"
        normalized.append(
            {
                "id": case_id,
                "crc": int(crc),
                "buf": [int(item) for item in buf],
                "size": int(size),
                "return_code": int(expected),
            }
        )
    return normalized, fixture_file, "ok"


def rust_direct_replay_case_literal(case: dict[str, Any]) -> str:
    return (
        "        FixtureCase { "
        f"id: {rust_string_literal(case['id'])}, "
        f"crc: {int(case['crc'])}u32, "
        f"buf: {rust_byte_slice_literal(case['buf'])}, "
        f"size: {int(case['size'])}usize, "
        f"return_code: {int(case['return_code'])}u32 "
        "},\n"
    )


def direct_c2rust_replay_main_rs(crate_name: str, cases: list[dict[str, Any]]) -> str:
    case_literals = "".join(rust_direct_replay_case_literal(case) for case in cases)
    return (
        "use std::fs;\n"
        "\n"
        "struct FixtureCase {\n"
        "    id: &'static str,\n"
        "    crc: u32,\n"
        "    buf: &'static [u8],\n"
        "    size: usize,\n"
        "    return_code: u32,\n"
        "}\n"
        "\n"
        "fn json_escape(value: &str) -> String {\n"
        "    value.replace('\\\\', \"\\\\\\\\\").replace('\"', \"\\\\\\\"\")\n"
        "}\n"
        "\n"
        "fn c2rust_fdb_calc_crc32(crc: u32, buf: &[u8]) -> u32 {\n"
        "    unsafe {\n"
        f"        {crate_name}::src::fdb_utils::fdb_calc_crc32(\n"
        "            crc,\n"
        "            buf.as_ptr().cast::<core::ffi::c_void>(),\n"
        "            buf.len(),\n"
        "        )\n"
        "    }\n"
        "}\n"
        "\n"
        "fn main() {\n"
        "    let results_path = std::env::args().nth(1).expect(\"missing direct replay results path\");\n"
        "    let fixture_cases: &[FixtureCase] = &[\n"
        f"{case_literals}"
        "    ];\n"
        "    let mut all_matched = true;\n"
        "    let mut rows = Vec::new();\n"
        "    for case in fixture_cases {\n"
        "        let actual = c2rust_fdb_calc_crc32(case.crc, case.buf);\n"
        "        let matched = case.buf.len() == case.size && actual == case.return_code;\n"
        "        if !matched { all_matched = false; }\n"
        "        rows.push(format!(\n"
        "            \"{{\\\"id\\\":\\\"{}\\\",\\\"expected_return_code\\\":{},\\\"actual_return_code\\\":{},\\\"matched\\\":{}}}\",\n"
        "            json_escape(case.id),\n"
        "            case.return_code,\n"
        "            actual,\n"
        "            if matched { \"true\" } else { \"false\" }\n"
        "        ));\n"
        "    }\n"
        "    let payload = format!(\n"
        "        \"{{\\\"schema_version\\\":1,\\\"case_count\\\":{},\\\"all_matched\\\":{},\\\"cases\\\":[{}]}}\",\n"
        "        fixture_cases.len(),\n"
        "        if all_matched { \"true\" } else { \"false\" },\n"
        "        rows.join(\",\")\n"
        "    );\n"
        "    fs::write(&results_path, payload).expect(\"write direct replay results\");\n"
        "    if !all_matched { std::process::exit(1); }\n"
        "}\n"
    )


def emit_c2rust_direct_replay_artifact(
    spec: dict[str, Any],
    evidence_dir: Path,
    c2rust_baseline: dict[str, Any],
    output_ref: dict[str, Any],
    compile_artifact_ref: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    function_name = required_str(spec, "function_name")
    artifact_path = evidence_dir / f"{prefix}-c2rust-direct-replay.json"
    if function_name != "fdb_calc_crc32":
        return {
            "status": "blocked",
            "reason": "direct_c2rust_replay_unsupported_function",
        }
    output = c2rust_baseline.get("output")
    if not isinstance(output, dict):
        return {"status": "blocked", "reason": "c2rust_output_missing"}
    crate_root_text = output.get("crate_root")
    cargo_toml_text = output.get("cargo_toml")
    if not crate_root_text or not cargo_toml_text:
        return {"status": "blocked", "reason": "c2rust_generated_crate_missing"}
    crate_root = path_from_evidence_text(crate_root_text)
    cargo_toml = path_from_evidence_text(cargo_toml_text)
    crate_name = c2rust_generated_crate_name(cargo_toml)
    if crate_name is None:
        return {"status": "blocked", "reason": "c2rust_generated_crate_name_missing"}
    cases, fixture_file, case_status = direct_c2rust_replay_cases(spec)
    if case_status != "ok" or fixture_file is None:
        return {"status": "blocked", "reason": f"direct_c2rust_replay_{case_status}"}
    cargo = shutil.which("cargo")
    if cargo is None:
        return {"status": "blocked", "reason": "cargo_not_found_for_direct_c2rust_replay"}

    harness_dir = evidence_dir / f"{prefix}-c2rust-direct-replay-harness"
    src_dir = harness_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    dependency_path = relative_path_for_toml(crate_root, harness_dir)
    write_text(
        harness_dir / "Cargo.toml",
        "\n".join(
            [
                "[package]",
                f"name = {json.dumps(safe_ident(prefix + '-c2rust-direct-replay'))}",
                'version = "0.0.0"',
                'edition = "2021"',
                "publish = false",
                "",
                "[dependencies]",
                f"{crate_name} = {{ path = {json.dumps(dependency_path)} }}",
                "",
            ]
        ),
    )
    main_rs = src_dir / "main.rs"
    write_text(main_rs, direct_c2rust_replay_main_rs(crate_name, cases))
    results_path = evidence_dir / f"{prefix}-c2rust-direct-replay-results.json"
    stdout_log = evidence_dir / f"{prefix}-c2rust-direct-replay.stdout.log"
    stderr_log = evidence_dir / f"{prefix}-c2rust-direct-replay.stderr.log"
    timeout_seconds = 120
    argv = [
        cargo,
        "run",
        "--quiet",
        "--manifest-path",
        str(harness_dir / "Cargo.toml"),
        "--",
        str(results_path),
    ]
    command: dict[str, Any] = {
        "argv": argv,
        "working_directory": rel(REPO_ROOT),
        "stdout_log": rel(stdout_log),
        "stderr_log": rel(stderr_log),
        "timeout_seconds": timeout_seconds,
        "exit_status": "not_executed",
        "returncode": None,
    }
    env = dict(os.environ)
    env.update({"RUSTUP_TOOLCHAIN": "stable", "RUSTC_BOOTSTRAP": "1"})
    try:
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        write_text(stdout_log, exc.stdout or "")
        write_text(stderr_log, exc.stderr or f"direct C2Rust replay timed out after {timeout_seconds} seconds\n")
        command["exit_status"] = "timeout"
        command["returncode"] = -1
        return {"status": "failed", "reason": "direct_c2rust_replay_timeout", "command": command}
    except OSError as exc:
        write_text(stdout_log, "")
        write_text(stderr_log, f"{type(exc).__name__}: {exc}\n")
        command["exit_status"] = "error"
        command["returncode"] = -1
        return {"status": "failed", "reason": "direct_c2rust_replay_error", "command": command}

    write_text(stdout_log, completed.stdout or "")
    write_text(stderr_log, completed.stderr or "")
    command["exit_status"] = "passed" if completed.returncode == 0 else "failed"
    command["returncode"] = completed.returncode
    if not results_path.exists():
        return {"status": "failed", "reason": "direct_c2rust_replay_results_missing", "command": command}
    results = read_json(results_path)
    cases_result = results.get("cases")
    all_matched = completed.returncode == 0 and results.get("all_matched") is True and isinstance(cases_result, list)
    status = "passed" if all_matched else "failed"
    fixture_ref = {
        "path": str(fixture_path(spec)),
        "sha256": sha256(fixture_file),
        "case_count": len(cases),
    }
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "status": status,
        "observable_replay_pass": all_matched,
        "semantic_pass": False,
        "semantic_claim_source": "direct_c2rust_output_replay_observable_only",
        "generated_draft_semantic_pass": False,
        "replay_kind": "direct_c2rust_output_replay",
        "correctness_role": "direct_replay_evidence",
        "source_commit": source_commit(spec),
        "fixture": fixture_ref,
        "c2rust_output": output_ref,
        "compile_artifact": compile_artifact_ref,
        "call_binding": {
            "crate_name": crate_name,
            "crate_root_ref": evidence_ref(crate_root, "generated"),
            "cargo_toml_ref": evidence_ref(cargo_toml, "generated"),
            "module_path": "src::fdb_utils",
            "symbol": "fdb_calc_crc32",
            "abi": 'extern "C"',
            "signature": "pub unsafe extern \"C\" fn fdb_calc_crc32(crc: u32, buf: *const core::ffi::c_void, size: usize) -> u32",
            "wrapper_fn": "c2rust_fdb_calc_crc32(crc: u32, buf: &[u8]) -> u32",
            "argument_mapping": {
                "crc": "case.crc",
                "buf": "case.buf.as_ptr().cast::<core::ffi::c_void>()",
                "size": "case.buf.len()",
            },
        },
        "execution": {
            "harness_root": rel(harness_dir),
            "harness_main": evidence_ref(main_rs, "generated"),
            "command": command,
            "exit_status": command["exit_status"],
            "returncode": command["returncode"],
            "case_count": len(cases),
            "fixture_sha256": fixture_ref["sha256"],
            "stdout_ref": evidence_ref(stdout_log, "recorded"),
            "stderr_ref": evidence_ref(stderr_log, "recorded"),
            "results_ref": evidence_ref(results_path, "recorded"),
        },
        "bound_inputs": {
            "baseline_manifest": c2rust_baseline_ref(spec, evidence_dir, c2rust_baseline),
            "c2rust_output": output_ref,
            "compile_artifact": compile_artifact_ref,
            "source_files": output.get("source_files") if isinstance(output.get("source_files"), list) else [],
            "fixture": fixture_ref,
            "cargo_lock": evidence_ref(crate_root / "Cargo.lock", "present") if (crate_root / "Cargo.lock").exists() else None,
            "rust_toolchain": evidence_ref(
                REPO_ROOT / "config" / "competition-env" / "rust" / "rust-toolchain.toml",
                "present",
            ),
        },
        "results": results,
        "claim_boundary": {
            "accepted_evidence_reused": False,
            "compile_only_is_semantic_pass": False,
            "generated_draft_semantic_pass": False,
            "semantic_pass": False,
            "scope": "Direct replay of the generated C2Rust output against fixture observables; not a full semantic acceptance gate until diff, negative diff, unsafe ledger, and final verification are bound to the same output.",
        },
    }
    write_json(artifact_path, payload)
    return payload


def translation_source_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    source = plan.get("translation_source")
    if not isinstance(source, dict):
        return {"selected": "unknown"}
    selected = str(source.get("selected") or "unknown")
    normalized = {"selected": selected}
    fallback_from = source.get("fallback_from")
    fallback_reason = source.get("fallback_reason")
    if fallback_from:
        normalized["fallback_from"] = str(fallback_from)
    if fallback_reason:
        normalized["fallback_reason"] = str(fallback_reason)
    return normalized


def typed_ir_candidate_binding(report_path: Path) -> dict[str, Any]:
    source_artifact = evidence_ref(report_path, "missing")
    if not report_path.exists():
        return {
            "status": "missing",
            "source_artifact": source_artifact,
            "candidate_route": None,
            "readonly_globals": [],
            "readonly_globals_identity": readonly_globals_identity([]),
            "runtime_preconditions": [],
            "rust_draft_generated": False,
            "semantic_pass": False,
        }

    report = read_json(report_path)
    candidate = report.get("typed_ir_candidate")
    if not isinstance(candidate, dict):
        return {
            "status": "missing",
            "source_artifact": evidence_ref(report_path, str(report.get("status", "recorded"))),
            "candidate_route": None,
            "readonly_globals": [],
            "readonly_globals_identity": readonly_globals_identity([]),
            "runtime_preconditions": [],
            "rust_draft_generated": False,
            "semantic_pass": False,
            "reason": "typed_ir_candidate_missing",
        }

    readonly_globals = candidate.get("readonly_globals", [])
    if not isinstance(readonly_globals, list):
        readonly_globals = []
    runtime_preconditions = candidate.get("runtime_preconditions", [])
    if not isinstance(runtime_preconditions, list):
        runtime_preconditions = []
    binding = {
        "status": str(candidate.get("status", "unknown")),
        "source_artifact": evidence_ref(report_path, str(report.get("status", "recorded"))),
        "candidate_route": candidate.get("candidate_route"),
        "readonly_globals": readonly_globals,
        "readonly_globals_identity": readonly_globals_identity(readonly_globals),
        "runtime_preconditions": runtime_preconditions,
        "rust_draft_generated": bool(candidate.get("rust_draft_generated", False)),
        "semantic_pass": False,
    }
    if candidate.get("reason"):
        binding["reason"] = str(candidate["reason"])
    if candidate.get("unsupported_reason"):
        binding["unsupported_reason"] = str(candidate["unsupported_reason"])
    if candidate.get("typed_ir_sha256"):
        binding["typed_ir_sha256"] = str(candidate["typed_ir_sha256"])
    if candidate.get("rust_draft_sha256"):
        binding["rust_draft_sha256"] = str(candidate["rust_draft_sha256"])
    return binding


def readonly_globals_identity(readonly_globals: list[Any]) -> dict[str, Any]:
    names = [
        str(item.get("name", ""))
        for item in readonly_globals
        if isinstance(item, dict) and item.get("name")
    ]
    return {
        "count": len(readonly_globals),
        "names": names,
        "sha256": sha256_json(readonly_globals),
    }


def route_level(
    spec: dict[str, Any],
    translator_summary: dict[str, Any],
    type_map: dict[str, Any],
    cfg: dict[str, Any],
    pointer: dict[str, Any],
    plan: dict[str, Any],
    candidate_generation: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Classify the slice route from fail-closed artifact and alias risk.

    Typed-IR candidate signals may select a cheaper route for generated drafts,
    but they never override blocked artifacts, unsupported control flow, alias
    floors, or the later requirement that a validation profile produce the
    semantic-pass claim.
    """
    rationale: list[dict[str, Any]] = []
    blocked_statuses = {
        "translator": translator_summary.get("status"),
        "type_map": type_map.get("status"),
        "cfg": cfg.get("status"),
        "plan": plan.get("status"),
    }
    if cfg.get("unsupported_control_flow"):
        rationale.append({"feature": "unsupported_control_flow", "weight": "hard_refuse"})
        return "L4", rationale
    if any(value == "blocked" for value in blocked_statuses.values()):
        rationale.append({"feature": "blocked_artifact", "values": blocked_statuses, "weight": "hard_refuse"})
        return "L4", rationale
    pointer_nodes = pointer.get("pointer_nodes", [])
    typed_ir_signal = typed_ir_candidate_route_signal(candidate_generation or {}, scalar_only=not pointer_nodes)
    alias_floor = alias_route_floor(pointer)
    if alias_floor is not None:
        level, alias_rationale = alias_floor
        rationale.append(alias_rationale)
        if typed_ir_signal is not None:
            rationale.append(typed_ir_signal[1])
        return level, rationale
    if any(node.get("ownership_role") == "unknown" for node in pointer_nodes):
        rationale.append({"feature": "unknown_pointer_role", "weight": "medium"})
        if typed_ir_signal is not None:
            rationale.append(typed_ir_signal[1])
        return "L2", rationale
    if typed_ir_signal is not None:
        level, typed_ir_rationale = typed_ir_signal
        rationale.append(typed_ir_rationale)
        return level, rationale
    if not pointer_nodes:
        rationale.append({"feature": "scalar_only", "weight": "low"})
        return "L0", rationale
    rationale.append({"feature": "bounded_pointer_surface", "weight": "low"})
    return "L1", rationale


def alias_route_floor(pointer: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    alias_contract = pointer.get("alias_contract", {})
    if not isinstance(alias_contract, dict):
        alias_contract = {}
    alias_risks = pointer.get("alias_risks", [])
    if not isinstance(alias_risks, list):
        alias_risks = []
    if alias_contract.get("decision") == "blocked":
        return "L3", {"feature": "alias_blocked", "weight": "high"}
    if alias_contract.get("decision") == "requires_noalias_contract" or any(
        isinstance(risk, dict)
        and (
            risk.get("risk_level") == "unknown_alias"
            or risk.get("gate_decision") == "requires_noalias_contract"
            or risk.get("requires_noalias") is True
        )
        for risk in alias_risks
    ):
        return (
            "L2",
            {
                "feature": "alias_requires_noalias_contract",
                "risk_count": len(alias_risks),
                "weight": "medium",
            },
        )
    return None


def typed_ir_candidate_route_signal(
    candidate_generation: dict[str, Any], *, scalar_only: bool = False
) -> tuple[str, dict[str, Any]] | None:
    typed_ir = candidate_generation.get("typed_ir")
    if not isinstance(typed_ir, dict):
        return None
    status = str(typed_ir.get("status", ""))
    candidate_route = typed_ir.get("candidate_route")
    route = candidate_route.get("route") if isinstance(candidate_route, dict) else None
    token_cost = candidate_route.get("token_cost") if isinstance(candidate_route, dict) else None
    if status == "generated" and route == "GenericTypedIr" and typed_ir.get("rust_draft_generated") is True:
        scalar_admission = typed_ir.get("scalar_admission", {})
        if isinstance(scalar_admission, dict) and scalar_admission.get("status") == "unresolved":
            unresolved = scalar_admission.get("unresolved", [])
            return (
                "L1",
                {
                    "feature": "typed_ir_scalar_admission_unresolved",
                    "route": "GenericTypedIr",
                    "unresolved_count": len(unresolved) if isinstance(unresolved, list) else 0,
                    "weight": "requires_contract_or_domain_evidence",
                },
            )
        if scalar_only and token_cost == 0:
            return (
                "L0",
                {
                    "feature": "typed_ir_zero_token_deterministic",
                    "route": "GenericTypedIr",
                    "token_cost": 0,
                    "weight": "deterministic_typed_ir",
                },
            )
        return (
            "L1",
            {
                "feature": "typed_ir_candidate_generated",
                "route": "GenericTypedIr",
                "weight": "generic_typed_ir",
            },
        )
    if status == "unsupported":
        reason = str(typed_ir.get("unsupported_reason") or typed_ir.get("reason") or "typed_ir_candidate_unsupported")
        return (
            "L2",
            {
                "feature": "typed_ir_candidate_unsupported",
                "reason": reason,
                "weight": "repair_queue",
            },
        )
    return None


def route_translator(level: str) -> dict[str, Any]:
    if level == "L4":
        return {"kind": "refuse", "candidate_generation_allowed": False}
    if level in {"L0", "L1", "L2"}:
        return {"kind": "tier1", "candidate_generation_allowed": True}
    return {"kind": "agent", "candidate_generation_allowed": True}


def emit_validation_profile(
    spec: dict[str, Any],
    evidence_dir: Path,
    route_decision: dict[str, Any],
    oracle: dict[str, Any],
    rust_check: dict[str, Any],
    accepted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the profile that owns required gates for this route.

    Route status selects the profile; profile status records whether every
    required gate is present and passed. Generated candidate replay or diff
    evidence remains diagnostic unless accepted evidence is explicitly
    authoritative for the route and all profile gates are satisfied.
    """
    slice_id = required_str(spec, "slice_id")
    prefix = f"l3-{slice_id}"
    goal = route_decision.get("policy", {}).get("goal", "dev")
    level = str(route_decision.get("level", "L4"))
    profile = route_decision.get("verification_profile") or validation_profile_name(level, goal)
    required = required_gates_for_profile(level, goal)
    skipped = []
    accepted_authoritative = accepted_evidence_authoritative_route(route_decision)
    if route_decision.get("translator", {}).get("kind") == "refuse" and not accepted_authoritative:
        skipped.append({"gate": "candidate_generation", "reason": "route_refused"})
    if "compile" in required and rust_check.get("status") not in {"passed", "failed"}:
        skipped.append({"gate": "compile", "reason": rust_check.get("status", "unknown")})
    if "c_oracle_diff" in required and oracle.get("status") != "C_ORACLE_GENERATED":
        skipped.append({"gate": "c_oracle_diff", "reason": oracle.get("status", "missing")})
    for gate in required:
        if gate in {"compile", "c_oracle_diff"}:
            continue
        if gate == "rust_tests":
            test_translation = read_json(evidence_dir / f"{prefix}-test-translation-generated.json")
            if test_translation.get("status") not in {"recorded", "passed"}:
                skipped.append({"gate": gate, "reason": test_translation.get("status", "missing")})
            continue
        if gate == "unsafe_ledger":
            accepted_ledger = accepted is not None and accepted.get("reports", {}).get("unsafe_ledger", {}).get("status") == "passed"
            unsafe_ledger = evidence_dir / f"{prefix}-unsafe-ledger.json"
            generated_ledger = unsafe_ledger.exists() and read_json(unsafe_ledger).get("status") == "passed"
            if not accepted_ledger and not generated_ledger:
                skipped.append({"gate": gate, "reason": "unsafe_ledger_not_passed"})
            continue
        skipped.append({"gate": gate, "reason": "required_gate_not_available_in_dev_evidence"})
    compile_passed = rust_check.get("status") == "passed"
    oracle_passed = oracle.get("status") == "C_ORACLE_GENERATED"
    oracle_contract = oracle_boundary_contract(spec, accepted=accepted, oracle=oracle)
    if accepted is not None and oracle_contract.get("status") != "sufficient_for_semantic_pass":
        skipped.append(
            {
                "gate": "oracle_boundary_contract",
                "reason": oracle_contract.get("status", "missing"),
                "insufficient": oracle_contract.get("insufficient_reasons", []),
            }
        )
    result = "passed" if not skipped and compile_passed and oracle_passed else "blocked" if level == "L4" else "incomplete"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "source_commit": source_commit(spec),
        "source_identity": source_identity(spec),
        "status": result,
        "profile": profile,
        "route_level": level,
        "goal": goal,
        "competition_environment": competition_environment_identity(),
        "required_gates": required,
        "optional_gates": optional_gates_for_profile(level, goal),
        "skipped_gates": skipped,
        "required_gate_status": {
            "compile": rust_check.get("status"),
            "c_oracle_diff": oracle.get("status"),
        },
        "candidate_generation": route_decision.get("candidate_generation", {}),
        "scalar_ub_contract": route_decision.get("scalar_ub_contract", scalar_ub_contract(spec)),
        "oracle_boundary_contract": oracle_contract,
        "accepted_evidence_authoritative": accepted_authoritative,
        "generated_draft_semantic_pass": False,
        "loop_policy": {
            "source": "run_policy",
            "fixed_project_loop_count_required": False,
            "stress_loops": spec.get("verification_profile", {}).get("stress_loops"),
        },
        "tool_boundaries": {
            "c_ub": ["clang_diagnostics", "sanitizer_oracle", "unsupported_evidence"],
            "rust_ub": ["miri", "unsafe_ledger", "rust_verification_tools"],
        },
    }
    write_json(evidence_dir / f"{prefix}-validation-profile.json", payload)
    return payload


def validation_profile_name(level: str, goal: str) -> str:
    return f"{level}-{goal}"


def required_gates_for_profile(level: str, goal: str) -> list[str]:
    gates = ["compile", "c_oracle_diff"]
    if level in {"L1", "L2", "L3"}:
        gates.extend(["unsafe_ledger", "rust_tests"])
    if level in {"L2", "L3"}:
        gates.extend(["fuzz_property", "miri"])
    if level == "L3" and goal in {"ci-merge", "release"}:
        gates.append("kani")
    if goal == "release":
        gates.extend(["negative_diff", "evidence_cleanliness"])
    return gates


def optional_gates_for_profile(level: str, goal: str) -> list[str]:
    optional = ["negative_diff", "evidence_cleanliness"]
    if level in {"L0", "L1"}:
        optional.extend(["fuzz_property", "miri"])
    if goal != "release":
        optional.append("kani")
    return optional
