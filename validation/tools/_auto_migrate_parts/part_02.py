def resolve_c_compiler(requested: str) -> dict[str, Any]:
    candidates = [requested]
    requested_name = Path(requested).name.lower()
    if requested_name in {"cc", "cc.exe"}:
        candidates.extend(["gcc", "clang"])

    seen: set[str] = set()
    ordered_candidates = []
    for candidate in candidates:
        if candidate not in seen:
            ordered_candidates.append(candidate)
            seen.add(candidate)

    for candidate in ordered_candidates:
        path = shutil.which(candidate)
        if path is not None:
            return {
                "path": path,
                "name": candidate,
                "candidates": ordered_candidates,
                "adapter": "local",
                "launcher": None,
            }

    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl is not None:
        for candidate in ordered_candidates:
            path = wsl_command_output(wsl, f"command -v {shlex.quote(candidate)}")
            if path:
                return {
                    "path": path,
                    "name": candidate,
                    "candidates": ordered_candidates,
                    "adapter": "wsl",
                    "launcher": wsl,
                }
    return {
        "path": None,
        "name": None,
        "candidates": ordered_candidates,
        "adapter": "local",
        "launcher": None,
    }


def c_oracle_compile_execution_argv(
    argv: list[str],
    evidence_dir: Path,
    compiler_resolution: dict[str, Any],
) -> list[str]:
    compiler_path = str(compiler_resolution["path"])
    resolved_args = c_oracle_compile_execution_args_with_resolved_paths(argv, evidence_dir)
    if compiler_resolution.get("adapter") != "wsl":
        return [compiler_path, *resolved_args[1:]]

    launcher = str(compiler_resolution["launcher"])
    wsl_cwd = wsl_path(evidence_dir, launcher)
    converted_args = [compiler_path]
    for arg in resolved_args[1:]:
        converted_args.append(wsl_compile_arg(arg, launcher))
    shell_command = f"cd {shlex.quote(wsl_cwd)} && {' '.join(shlex.quote(item) for item in converted_args)}"
    return [launcher, "-e", "sh", "-lc", shell_command]


def c_oracle_compile_execution_args_with_resolved_paths(argv: list[str], evidence_dir: Path) -> list[str]:
    evidence_dir = c_oracle_absolute_evidence_dir(evidence_dir)
    resolved: list[str] = []
    output_next = False
    for arg in argv:
        if output_next:
            resolved.append(c_oracle_resolve_output_path(arg, evidence_dir))
            output_next = False
            continue
        if arg == "-o":
            resolved.append(arg)
            output_next = True
            continue
        if arg.startswith("-I") and len(arg) > 2:
            resolved.append("-I" + c_oracle_resolve_input_path(arg[2:], evidence_dir, force=True))
            continue
        resolved.append(c_oracle_resolve_input_path(arg, evidence_dir))
    return resolved


def c_oracle_resolve_input_path(arg: str, evidence_dir: Path, force: bool = False) -> str:
    evidence_dir = c_oracle_absolute_evidence_dir(evidence_dir)
    if not force and not c_oracle_arg_looks_like_path(arg):
        return arg
    if path_is_absolute(arg):
        return arg
    evidence_candidate = evidence_dir / arg
    if evidence_candidate.exists():
        return str(evidence_candidate)
    repo_candidate = REPO_ROOT / arg
    if repo_candidate.exists() or "/" in arg or "\\" in arg:
        return str(repo_candidate)
    return arg


def c_oracle_resolve_output_path(arg: str, evidence_dir: Path) -> str:
    evidence_dir = c_oracle_absolute_evidence_dir(evidence_dir)
    if path_is_absolute(arg):
        return arg
    return str(evidence_dir / arg)


def c_oracle_absolute_evidence_dir(evidence_dir: Path) -> Path:
    if evidence_dir.is_absolute():
        return evidence_dir
    return REPO_ROOT / evidence_dir


def c_oracle_arg_looks_like_path(arg: str) -> bool:
    if not arg or arg.startswith("-"):
        return False
    return (
        "/" in arg
        or "\\" in arg
        or Path(arg).suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".o", ".a", ".so", ".dylib", ".dll"}
    )


def wsl_compile_arg(arg: str, launcher: str) -> str:
    if arg.startswith("-I") and len(arg) > 2:
        return "-I" + wsl_maybe_path(arg[2:], launcher)
    return wsl_maybe_path(arg, launcher)


def wsl_maybe_path(value: str, launcher: str) -> str:
    if path_is_absolute(value):
        return wsl_path(Path(value), launcher)
    return value


def wsl_path(path: Path, launcher: str) -> str:
    result = subprocess.run(
        [launcher, "-e", "wslpath", "-a", str(path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(truncate_text(result.stderr or result.stdout or f"wslpath failed for {path}"))
    converted = result.stdout.strip()
    if not converted:
        raise RuntimeError(f"wslpath returned no path for {path}")
    return converted


def wsl_command_output(launcher: str, command: str) -> str | None:
    try:
        result = subprocess.run(
            [launcher, "-e", "sh", "-lc", command],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    first_line = result.stdout.strip().splitlines()
    return first_line[0] if first_line else None


def c_oracle_harness_execution(
    argv: list[str],
    evidence_dir: Path,
    spec: dict[str, Any] | None = None,
    fixture_binding: dict[str, Any] | None = None,
    compiler_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timeout_seconds = 30
    executable_path = c_oracle_output_executable(argv, evidence_dir)
    base = {
        "argv": [rel(executable_path)] if executable_path is not None else [],
        "working_directory": rel(evidence_dir),
        "executable_path": rel(executable_path) if executable_path is not None else "missing",
        "timeout_seconds": timeout_seconds,
        "semantic_pass": False,
    }
    if executable_path is None:
        payload = {
            **base,
            "status": "executable_missing_not_oracle",
            "attempted": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "diagnostics": ["C oracle harness output path is missing; no oracle evidence accepted."],
        }
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload
    if not executable_path.exists():
        payload = {
            **base,
            "status": "executable_missing_not_oracle",
            "attempted": False,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "diagnostics": [
                "C oracle harness executable is missing after compile success; no oracle evidence accepted."
            ],
        }
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload

    execution_argv = [str(executable_path)]
    execution_cwd: Path | None = evidence_dir
    adapter = None
    if compiler_resolution and compiler_resolution.get("adapter") == "wsl":
        adapter = "wsl"
        launcher = str(compiler_resolution["launcher"])
        try:
            wsl_cwd = wsl_path(evidence_dir, launcher)
            wsl_executable = wsl_path(executable_path, launcher)
            execution_argv = [
                launcher,
                "-e",
                "sh",
                "-lc",
                f"cd {shlex.quote(wsl_cwd)} && {shlex.quote(wsl_executable)}",
            ]
            execution_cwd = None
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            payload = {
                **base,
                "status": "execution_error_not_oracle",
                "attempted": False,
                "returncode": None,
                "stdout": "",
                "stderr": truncate_text(str(exc)),
                "diagnostics": ["C oracle harness execution could not start; no oracle evidence accepted."],
                "toolchain_adapter": adapter,
            }
            payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
            return payload

    try:
        result = subprocess.run(
            execution_argv,
            cwd=execution_cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        payload = {
            **base,
            "status": "execution_timeout_not_oracle",
            "attempted": True,
            "returncode": None,
            "stdout": truncate_text(exc.stdout or ""),
            "stderr": truncate_text(exc.stderr or f"harness execution timed out after {timeout_seconds} seconds"),
            "diagnostics": ["C oracle harness execution timed out; no oracle evidence accepted."],
        }
        if adapter:
            payload["toolchain_adapter"] = adapter
            payload["execution_argv"] = execution_argv
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload
    except OSError as exc:
        payload = {
            **base,
            "status": "execution_error_not_oracle",
            "attempted": False,
            "returncode": None,
            "stdout": "",
            "stderr": truncate_text(str(exc)),
            "diagnostics": ["C oracle harness execution could not start; no oracle evidence accepted."],
        }
        if adapter:
            payload["toolchain_adapter"] = adapter
            payload["execution_argv"] = execution_argv
        payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, payload)
        return payload

    exited_zero = result.returncode == 0
    raw_payload = {
        **base,
        "status": "exited_zero_not_oracle" if exited_zero else "exited_nonzero_not_oracle",
        "attempted": True,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "diagnostics": [
            "C oracle harness executed, but execution output has not passed oracle diff gates."
        ],
    }
    if adapter:
        raw_payload["toolchain_adapter"] = adapter
        raw_payload["execution_argv"] = execution_argv
    payload = {
        **raw_payload,
        "stdout": truncate_text(result.stdout),
        "stderr": truncate_text(result.stderr),
    }
    payload["output_gate"] = c_oracle_harness_output_gate(spec, fixture_binding, raw_payload)
    return payload


def c_oracle_harness_output_gate(
    spec: dict[str, Any] | None,
    fixture_binding: dict[str, Any] | None,
    harness_execution: dict[str, Any],
) -> dict[str, Any]:
    expected_fragments = c_oracle_expected_stdout_fragments(spec, fixture_binding)
    base = {
        "schema_version": 1,
        "gate": "c_oracle_harness_output",
        "semantic_pass": False,
        "compared_fields": behavior_fields(spec) if spec is not None else [],
        "fixture_expected_output_status": str(
            fixture_binding.get("expected_output_status", "missing_or_empty")
            if isinstance(fixture_binding, dict)
            else "missing_or_empty"
        ),
        "expected_stdout_fragments": expected_fragments,
        "matched_stdout_fragments": [],
        "missing_stdout_fragments": expected_fragments,
        "boundary": "Harness stdout markers are diagnostic only until accepted oracle diff gates pass.",
    }
    if harness_execution.get("status") != "exited_zero_not_oracle" or harness_execution.get("returncode") != 0:
        return {
            **base,
            "status": "not_run_not_oracle",
            "diagnostics": ["C oracle harness output gate did not run because harness execution did not exit zero."],
        }
    if not expected_fragments:
        return {
            **base,
            "status": "unsupported_not_oracle",
            "diagnostics": ["C oracle harness output gate has no supported fixture stdout markers to compare."],
        }

    stdout = str(harness_execution.get("stdout") or "")
    matched = [fragment for fragment in expected_fragments if fragment in stdout]
    missing = [fragment for fragment in expected_fragments if fragment not in stdout]
    if not missing:
        return {
            **base,
            "status": "matched_not_oracle",
            "matched_stdout_fragments": matched,
            "missing_stdout_fragments": [],
            "diagnostics": [
                "C oracle harness stdout matched draft fixture markers, but oracle diff gates are still required."
            ],
        }
    return {
        **base,
        "status": "mismatch_not_oracle",
        "matched_stdout_fragments": matched,
        "missing_stdout_fragments": missing,
        "diagnostics": ["C oracle harness stdout did not match all draft fixture markers; no oracle evidence accepted."],
    }


def c_oracle_expected_stdout_fragments(
    spec: dict[str, Any] | None,
    fixture_binding: dict[str, Any] | None,
) -> list[str]:
    if spec is None or fixture_binding is None:
        return []
    fields = behavior_fields(spec)
    fragments: list[str] = []
    for case in fixture_binding.get("case_bindings", []):
        if not isinstance(case, dict):
            continue
        expected_outputs = case.get("expected_outputs")
        if not isinstance(expected_outputs, dict):
            continue
        case_id = str(case.get("id") or "case")
        for field in fields:
            if field in expected_outputs:
                fragments.append(f"fixture case {case_id} {field} matched")
    return fragments


def c_oracle_output_executable(argv: list[str], evidence_dir: Path) -> Path | None:
    try:
        output_index = argv.index("-o") + 1
    except ValueError:
        return None
    if output_index >= len(argv):
        return None
    output_path = Path(argv[output_index])
    if not output_path.is_absolute():
        output_path = evidence_dir / output_path
    return output_path


def truncate_text(text: str | bytes | None, limit: int = 4000) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    elif not isinstance(text, str):
        text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def compile_source_root(spec: dict[str, Any]) -> str:
    source_root = spec.get("source", {}).get("source_root")
    if not source_root:
        return "."
    return normalize_path_text(source_root)


def compile_link_source_files(spec: dict[str, Any], source_root: str) -> list[dict[str, Any]]:
    files = []
    for item in spec.get("c_boundary", {}).get("files", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = normalize_path_text(item["path"])
        files.append(
            {
                "path": path,
                "resolved_path": resolve_source_root_path(source_root, path),
                "role": str(item.get("role") or "source"),
                "sha256": str(item.get("sha256") or "unknown"),
                "resolution": "source_root_relative" if source_root != "." else "declared_path",
            }
        )
    for item in spec.get("build_profile", {}).get("link_source_files", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = normalize_path_text(item["path"])
        files.append(
            {
                "path": path,
                "resolved_path": resolve_source_root_path(source_root, path),
                "role": str(item.get("role") or "link_dependency"),
                "sha256": str(item.get("sha256") or "unknown"),
                "resolution": "source_root_relative" if source_root != "." else "declared_path",
            }
        )
    return files


def c_oracle_link_strategy(spec: dict[str, Any]) -> str:
    if c_oracle_embeds_slice_source(spec):
        return "compile_harness_with_embedded_slice_source"
    if spec.get("build_profile", {}).get("link_source_files"):
        return "compile_harness_with_declared_c_boundary_and_build_profile_sources"
    return "compile_harness_with_declared_c_boundary_sources"


def c_oracle_source_mode(spec: dict[str, Any]) -> str:
    return str(spec.get("c_boundary", {}).get("oracle_source_mode") or "declared_c_boundary_sources")


def c_oracle_embeds_slice_source(spec: dict[str, Any]) -> bool:
    return c_oracle_source_mode(spec) == "embedded_slice_c_source"


def c_oracle_embedded_slice_source(spec: dict[str, Any]) -> str | None:
    if not c_oracle_embeds_slice_source(spec):
        return None
    c_source = spec.get("c_source")
    if isinstance(c_source, str) and c_source.strip():
        return c_source
    function_name = required_str(spec, "function_name")
    for signature in spec.get("c_boundary", {}).get("signatures", []):
        if not isinstance(signature, dict) or signature.get("function") != function_name:
            continue
        c_source = signature.get("c_source")
        if isinstance(c_source, str) and c_source.strip():
            return c_source
    return None


def resolve_source_root_path(source_root: str, path: Any) -> str:
    path_text = normalize_path_text(path)
    if not path_text or path_is_absolute(path_text) or source_root == ".":
        return path_text
    if not path_is_absolute(source_root) and (
        path_text == source_root or path_text.startswith(f"{source_root}/")
    ):
        return path_text
    return normalize_path_text(f"{source_root}/{path_text}")


def path_is_absolute(path: str) -> bool:
    return (
        path.startswith("/")
        or path.startswith("//")
        or path.startswith("\\\\")
        or (len(path) >= 3 and path[1] == ":" and path[2] in {"/", "\\"})
    )


def normalize_path_text(path: Any) -> str:
    return str(path).strip().replace("\\", "/").rstrip("/")


def generate_rust_replay_test_draft(
    spec: dict[str, Any],
    evidence_dir: Path,
    slice_spec_path: Path,
    route_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    function_name = required_str(spec, "function_name")
    path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    fixture = spec.get("fixture_contract", {})
    fixture_path_text = fixture_path(spec)
    fixture_binding = oracle_fixture_binding(spec)
    fixture_cases_source = rust_replay_fixture_cases_source(spec, fixture_binding)
    text = (
        "// Auto-generated Rust replay test draft.\n"
        "// Review before promoting into validation/l2_slices/tests.\n\n"
        "#[test]\n"
        f"fn replay_{safe_ident(slice_id)}_fixture_contract() {{\n"
        f"    let _fixture = {rust_string_literal(fixture_path_text)};\n"
        f"    let _api = {rust_string_literal(function_name)};\n"
        "    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;\n"
        f"{fixture_cases_source}"
        "}\n"
    )
    write_text(path, text)
    behavior_fields = fixture.get("observable_outputs") or fixture.get("behavior_fields", [])
    test_name = f"replay_{safe_ident(slice_id)}_fixture_contract"
    payload = {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "level": spec.get("level", "L3"),
        "status": "recorded",
        "generated_draft_semantic_pass": False,
        "test_draft": rel(path),
        "fixture": fixture_path_text,
        "behavior_fields": list(behavior_fields),
        "source_commit": source_commit(spec),
        "repo_commit": repo_commit(),
        "source_test_inputs": {
            "oracle_strategy": "Generated replay draft from slice fixture contract; accepted semantics still require C_ORACLE_GENERATED.",
            "fixtures": [
                {
                    "path": fixture_path_text,
                    "hash": fixture_hash(spec),
                    "operation_count": len(fixture.get("cases", [])),
                    "source_kind": "fixture",
                }
            ],
            "oracle_reports": [
                {
                    "path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"),
                    "status": "draft_or_skipped",
                }
            ],
        },
        "rust_tests": [
            {
                "file": rel(path),
                "test_names": [test_name],
                "cargo_command": f"cargo test {test_name}",
                "framework": "cargo test",
                "file_hash": sha256(path),
            }
        ],
        "coverage": {
            "main_paths": list(behavior_fields),
            "error_paths": [],
            "negative_cases": ["negative diff must be generated before acceptance"],
        },
        "translation_mappings": [
            {
                "source": fixture_path_text,
                "rust_test": f"{rel(path)}::{test_name}",
                "behavior_fields": list(behavior_fields),
                "coverage_kind": "oracle_replay",
                "status": "mapped",
                "evidence": [
                    {
                        "path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"),
                        "status": "not_semantic_pass",
                    }
                ],
            }
        ],
        "evidence_links": {
            "rust_draft": {
                "path": rel(evidence_dir / f"l3-{slice_id}-rust-draft.rs"),
                "status": generated_rust_draft_status(route_decision),
            },
            "c_oracle": {"path": rel(evidence_dir / f"l3-{slice_id}-c-oracle-status.json"), "status": "draft_or_skipped"},
        },
        "known_gaps": [
            "Generated replay test is a draft until accepted C oracle and Rust replay reports are produced."
        ],
        "cache_invalidation_keys": cache_keys(spec, slice_spec_path),
    }
    write_json(evidence_dir / f"l3-{slice_id}-test-translation-generated.json", payload)
    return payload


def rust_replay_fixture_cases_source(spec: dict[str, Any], fixture_binding: dict[str, Any]) -> str:
    if behavior_fields(spec) != ["return_code"]:
        if fdb_blob_make_replay_supported(spec):
            return rust_replay_fdb_blob_make_cases_source(spec, fixture_binding)
        return "    // TODO: bind fixture cases to generated Rust API assertions.\n"

    function_name = safe_ident(required_str(spec, "function_name"))
    case_literals: list[str] = []
    unsupported_comments: list[str] = []
    for case_binding in fixture_binding.get("case_bindings", []):
        if not isinstance(case_binding, dict):
            continue
        case_literal = rust_replay_fixture_case_literal(spec, case_binding)
        if case_literal is None:
            case_id = str(case_binding.get("id") or "unknown-case")
            unsupported_comments.append(
                f"    // TODO: fixture case {case_id} is not supported by this replay draft generator.\n"
            )
            continue
        case_literals.append(case_literal)

    if not case_literals and not unsupported_comments:
        return "    // TODO: bind fixture cases to generated Rust API assertions.\n"

    expected_case_count = fixture_binding.get("case_count", len(case_literals))
    lines = [
        "    struct FixtureCase {\n",
        "        id: &'static str,\n",
        "        crc: u32,\n",
        "        buf: &'static [u8],\n",
        "        size: usize,\n",
        "        return_code: u32,\n",
        "    }\n",
        "\n",
        "    let fixture_cases: &[FixtureCase] = &[\n",
    ]
    lines.extend(case_literals)
    lines.extend(
        [
            "    ];\n",
            f"    assert_eq!(fixture_cases.len(), {expected_case_count}usize, \"fixture case count drifted\");\n",
            "    for case in fixture_cases {\n",
            '        assert_eq!(case.buf.len(), case.size, "{} fixture size must match byte buffer length", case.id);\n',
            f"        let actual = {function_name}(case.crc, case.buf, case.size);\n",
            '        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);\n',
            "    }\n",
        ]
    )
    lines.extend(unsupported_comments)
    return "".join(lines)


def fdb_blob_make_replay_supported(spec: dict[str, Any]) -> bool:
    return required_str(spec, "function_name") == "fdb_blob_make" and behavior_fields(spec) == [
        "return_same_blob",
        "blob.buf",
        "blob.size",
    ]


def rust_replay_fdb_blob_make_cases_source(spec: dict[str, Any], fixture_binding: dict[str, Any]) -> str:
    function_name = safe_ident(required_str(spec, "function_name"))
    case_literals: list[str] = []
    unsupported_comments: list[str] = []
    for case_binding in fixture_binding.get("case_bindings", []):
        if not isinstance(case_binding, dict):
            continue
        case_literal = rust_replay_fdb_blob_make_case_literal(spec, case_binding)
        if case_literal is None:
            case_id = str(case_binding.get("id") or "unknown-case")
            unsupported_comments.append(
                f"    // TODO: fixture case {case_id} is not supported by this fdb_blob_make replay generator.\n"
            )
            continue
        case_literals.append(case_literal)

    if not case_literals and not unsupported_comments:
        return "    // TODO: bind fixture cases to generated Rust API assertions.\n"

    expected_case_count = fixture_binding.get("case_count", len(case_literals))
    lines = [
        "    struct FixtureCase {\n",
        "        id: &'static str,\n",
        "        value_buf: &'static [u8],\n",
        "        value_buf_is_null: bool,\n",
        "        buf_len: usize,\n",
        "        initial_blob_size: usize,\n",
        "    }\n",
        "\n",
        "    let fixture_cases: &[FixtureCase] = &[\n",
    ]
    lines.extend(case_literals)
    lines.extend(
        [
            "    ];\n",
            f"    assert_eq!(fixture_cases.len(), {expected_case_count}usize, \"fixture case count drifted\");\n",
            "    for case in fixture_cases {\n",
            "        if !case.value_buf_is_null {\n",
            '            assert!(case.value_buf.len() >= case.buf_len, "{} fixture buffer shorter than declared length", case.id);\n',
            "        }\n",
            "        let value_ptr: *const core::ffi::c_void = if case.value_buf_is_null {\n",
            "            core::ptr::null::<core::ffi::c_void>()\n",
            "        } else {\n",
            "            case.value_buf.as_ptr().cast::<core::ffi::c_void>()\n",
            "        };\n",
            "        let mut blob = FdbBlob { buf: core::ptr::null_mut(), size: case.initial_blob_size };\n",
            "        let blob_ptr = &mut blob as *mut FdbBlob;\n",
            "        let returned_ptr = {\n",
            f"            let returned = {function_name}(&mut blob, value_ptr, case.buf_len);\n",
            "            returned as *mut FdbBlob\n",
            "        };\n",
            '        assert_eq!(returned_ptr, blob_ptr, "{} return_same_blob drifted", case.id);\n',
            '        assert_eq!(blob.buf, value_ptr as *mut core::ffi::c_void, "{} blob.buf drifted", case.id);\n',
            '        assert_eq!(blob.size, case.buf_len, "{} blob.size drifted", case.id);\n',
            "    }\n",
        ]
    )
    lines.extend(unsupported_comments)
    return "".join(lines)


def rust_replay_fdb_blob_make_case_literal(spec: dict[str, Any], case_binding: dict[str, Any]) -> str | None:
    case_payload = oracle_fixture_input_payload(spec, case_binding)
    if not isinstance(case_payload, dict):
        return None
    expected_outputs = case_binding.get("expected_outputs")
    if not isinstance(expected_outputs, dict):
        return None
    return_same_blob = expected_outputs.get("return_same_blob")
    expected_blob_buf = expected_outputs.get("blob.buf")
    expected_blob_size = expected_outputs.get("blob.size")
    buf_len = case_payload.get("buf_len")
    initial_blob_size = case_payload.get("initial_blob_size", 0)
    value_buf = case_payload.get("value_buf")
    if return_same_blob is not True or expected_blob_buf != "value_buf":
        return None
    if not is_size_value(buf_len) or not is_size_value(initial_blob_size):
        return None
    if expected_blob_size != int(buf_len):
        return None
    if value_buf is None:
        value_buf_literal = "&[]"
        value_buf_is_null = "true"
    elif is_byte_list(value_buf):
        value_buf_literal = rust_byte_slice_literal(value_buf)
        value_buf_is_null = "false"
    else:
        return None
    return (
        "        FixtureCase { "
        f"id: {rust_string_literal(case_binding.get('id') or 'case')}, "
        f"value_buf: {value_buf_literal}, "
        f"value_buf_is_null: {value_buf_is_null}, "
        f"buf_len: {int(buf_len)}usize, "
        f"initial_blob_size: {int(initial_blob_size)}usize "
        "},\n"
    )


def rust_replay_fixture_case_literal(spec: dict[str, Any], case_binding: dict[str, Any]) -> str | None:
    case_payload = oracle_fixture_input_payload(spec, case_binding)
    if not isinstance(case_payload, dict):
        return None
    expected_outputs = case_binding.get("expected_outputs")
    if not isinstance(expected_outputs, dict):
        return None
    expected_return = expected_outputs.get("return_code")
    crc = case_payload.get("crc")
    buf = case_payload.get("buf")
    size = case_payload.get("size")
    if not is_uint32_value(expected_return) or not is_uint32_value(crc):
        return None
    if not is_size_value(size) or not is_byte_list(buf):
        return None
    if int(size) != len(buf):
        return None

    return (
        "        FixtureCase { "
        f"id: {rust_string_literal(case_binding.get('id') or 'case')}, "
        f"crc: {int(crc)}u32, "
        f"buf: {rust_byte_slice_literal(buf)}, "
        f"size: {int(size)}usize, "
        f"return_code: {int(expected_return)}u32 "
        "},\n"
    )


def rust_byte_slice_literal(values: list[int]) -> str:
    if not values:
        return "&[]"
    return "&[" + ", ".join(f"{item}u8" for item in values) + "]"


def rust_string_literal(value: Any) -> str:
    return json.dumps(str(value))


def run_generated_rust_replay(
    spec: dict[str, Any],
    evidence_dir: Path,
    replay: dict[str, Any],
    rust_check: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    replay_path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    draft_path = evidence_dir / f"l3-{slice_id}-rust-draft.rs"
    if rust_check.get("status") != "passed":
        return replay
    if rust_check_has_harness_only_external_bindings(rust_check):
        replay["status"] = "not_applicable"
        replay["skip_reason"] = "compile_only_external_bindings_not_executable"
        replay["not_applicable_reason"] = "compile_only_external_bindings_not_executable"
        replay["generated_draft_replay_pass"] = False
        replay["generated_draft_semantic_pass"] = False
        replay["known_gaps"] = [
            "Rust-check harness-only external callee bindings are compile-only and must not be executed as replay proof."
        ]
        write_json(evidence_dir / f"l3-{slice_id}-test-translation-generated.json", replay)
        return replay
    if not generated_rust_replay_supported(spec, evidence_dir):
        return replay
    result = run_generated_rust_replay_once(draft_path, replay_path)
    write_text(evidence_dir / "generated-rust-replay-compile.stdout.log", result["compile_stdout"])
    write_text(evidence_dir / "generated-rust-replay-compile.stderr.jsonl", result["compile_stderr"])
    write_text(evidence_dir / "generated-rust-replay.stdout.log", result["run_stdout"])
    write_text(evidence_dir / "generated-rust-replay.stderr.log", result["run_stderr"])
    passed = result["status"] == "passed"
    replay["status"] = "passed" if passed else "failed"
    replay["generated_draft_replay_pass"] = passed
    replay["generated_draft_semantic_pass"] = False
    replay["replay_execution"] = {
        "status": result["status"],
        "phase": result["phase"],
        "compile_command": result["compile_command"],
        "compile_returncode": result["compile_returncode"],
        "run_command": result["run_command"],
        "run_returncode": result["run_returncode"],
        "stdout_log": rel(evidence_dir / "generated-rust-replay.stdout.log"),
        "stderr_log": rel(evidence_dir / "generated-rust-replay.stderr.log"),
    }
    replay["known_gaps"] = [
        "Generated Rust replay passed committed fixture cases; C oracle, schema diff, negative diff, unsafe, and final verification gates are still required."
    ]
    for mapping in replay.get("translation_mappings", []):
        if isinstance(mapping, dict):
            mapping["status"] = "passed" if passed else "failed"
    write_json(evidence_dir / f"l3-{slice_id}-test-translation-generated.json", replay)
    return replay


def rust_check_has_harness_only_external_bindings(rust_check: dict[str, Any]) -> bool:
    report = rust_check.get("rust_check_harness_only_bindings")
    if not isinstance(report, dict):
        return False
    return any(
        isinstance(binding, dict) and binding.get("status") == "harness_only"
        for binding in report.get("bindings", [])
    )


def generated_rust_replay_supported(spec: dict[str, Any], evidence_dir: Path) -> bool:
    if behavior_fields(spec) != ["return_code"] and not fdb_blob_make_replay_supported(spec):
        return False
    slice_id = required_str(spec, "slice_id")
    plan_path = evidence_dir / f"l3-{slice_id}-auto-translation-plan.json"
    draft_path = evidence_dir / f"l3-{slice_id}-rust-draft.rs"
    replay_path = evidence_dir / f"l3-{slice_id}-rust-replay-test-draft.rs"
    if not plan_path.exists() or not draft_path.exists() or not replay_path.exists():
        return False
    plan = read_json(plan_path)
    rule_ids = plan.get("translation_summary", {}).get("translation_rule_ids", [])
    return "clang-lowered-typed-ir" in rule_ids


def run_generated_rust_replay_once(draft_path: Path, replay_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c2r-generated-replay-") as build_dir_text:
        build_dir = Path(build_dir_text)
        combined_path = build_dir / "generated_replay.rs"
        exe_path = build_dir / "generated_replay.exe"
        combined_path.write_text(
            draft_path.read_text(encoding="utf-8-sig")
            + "\n"
            + replay_path.read_text(encoding="utf-8-sig"),
            encoding="utf-8",
        )
        compile_cmd = [
            "rustc",
            "--edition=2021",
            "--test",
            "--error-format=json",
            str(combined_path),
            "-o",
            str(exe_path),
        ]
        compile_result = subprocess.run(compile_cmd, cwd=REPO_ROOT, text=True, capture_output=True)
        if compile_result.returncode != 0:
            return {
                "status": "failed",
                "phase": "compile",
                "compile_command": shlex.join(compile_cmd),
                "compile_returncode": compile_result.returncode,
                "compile_stdout": compile_result.stdout,
                "compile_stderr": compile_result.stderr,
                "run_command": None,
                "run_returncode": None,
                "run_stdout": "",
                "run_stderr": "",
            }
        run_cmd = [str(exe_path), "--nocapture"]
        run_result = subprocess.run(run_cmd, cwd=REPO_ROOT, text=True, capture_output=True)
        return {
            "status": "passed" if run_result.returncode == 0 else "failed",
            "phase": "run",
            "compile_command": shlex.join(compile_cmd),
            "compile_returncode": compile_result.returncode,
            "compile_stdout": compile_result.stdout,
            "compile_stderr": compile_result.stderr,
            "run_command": shlex.join(run_cmd),
            "run_returncode": run_result.returncode,
            "run_stdout": run_result.stdout,
            "run_stderr": run_result.stderr,
        }


def generated_rust_report_cases(spec: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    fixture_binding = oracle_fixture_binding(spec)
    for case_binding in fixture_binding.get("case_bindings", []):
        if not isinstance(case_binding, dict):
            continue
        case_payload = oracle_fixture_input_payload(spec, case_binding)
        expected_outputs = case_binding.get("expected_outputs")
        if not isinstance(case_payload, dict) or not isinstance(expected_outputs, dict):
            continue
        case = {
            "id": case_binding.get("id"),
            "crc": case_payload.get("crc"),
            "buf": case_payload.get("buf"),
            "size": case_payload.get("size"),
            "return_code": expected_outputs.get("return_code"),
        }
        for optional_key in ["coverage_kind", "status"]:
            if optional_key in case_payload:
                case[optional_key] = case_payload[optional_key]
        cases.append(case)
    return cases


def run_rust_check(evidence_dir: Path, skip: bool, spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = next(evidence_dir.glob("l3-*-rust-draft.rs"), None)
    slice_id = required_str(spec, "slice_id")
    external_context = external_direct_callee_context(spec, load_plan_call_expressions(evidence_dir, slice_id))
    if skip or path is None:
        payload = {
            "schema_version": 1,
            "status": "skipped",
            "errors": [],
            "command": None,
            "external_callee_context": rust_check_external_context(external_context),
            "rust_check_harness_only_bindings": rust_check_external_binding_report(external_context),
        }
        patch = write_no_patch_required(spec, evidence_dir, path)
    else:
        if external_context["status"] == "recorded":
            inject_external_callee_stubs(path, external_context)
        first = rust_check_once(path)
        write_log_text(evidence_dir / "rust-check-initial.stdout.log", first["stdout"])
        write_log_text(evidence_dir / "rust-check-initial.stderr.jsonl", first["stderr"])
        patch = write_no_patch_required(spec, evidence_dir, path)
        final = first
        if first["returncode"] != 0:
            final, patch = run_safe_self_heal_loop(spec, evidence_dir, path, first)
        if final["returncode"] != 0 and patch["status"] != "blocked":
            patch = write_blocked_patch(
                spec,
                evidence_dir,
                path,
                final["errors"],
                round_number=REPAIR_ROUND_LIMIT,
                append_events=patch.get("self_heal_applied") is True,
            )
        write_log_text(evidence_dir / "rust-check.stdout.log", final["stdout"])
        write_log_text(evidence_dir / "rust-check.stderr.jsonl", final["stderr"])
        payload = {
            "schema_version": 1,
            "status": "passed" if final["returncode"] == 0 else "failed",
            "command": final["command"],
            "error_count": len(final["errors"]),
            "errors": final["errors"],
            "external_callee_context": rust_check_external_context(external_context),
            "rust_check_harness_only_bindings": rust_check_external_binding_report(external_context),
            "self_healing": {
                "status": patch["status"],
                "patch_events": patch["patch_events"],
                "blocked_repairs": patch["blocked_repairs"],
            },
        }
    write_json(evidence_dir / "rust-check.json", payload)
    return payload, patch


def rust_check_once(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c2r-rust-check-") as build_dir:
        cmd = [
            "rustc",
            "--edition=2021",
            "--crate-type=lib",
            "--error-format=json",
            "--out-dir",
            build_dir,
            str(path),
        ]
        result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)
    errors = [
        json.loads(line)
        for line in result.stderr.splitlines()
        if line.startswith("{") and '"level":"error"' in line.replace(" ", "")
    ]
    return {
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "errors": errors,
    }


RUST_KEYWORDS = {
    "as",
    "async",
    "await",
    "break",
    "const",
    "continue",
    "crate",
    "dyn",
    "else",
    "enum",
    "extern",
    "false",
    "fn",
    "for",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "match",
    "mod",
    "move",
    "mut",
    "pub",
    "ref",
    "return",
    "self",
    "Self",
    "static",
    "struct",
    "super",
    "trait",
    "true",
    "type",
    "unsafe",
    "use",
    "where",
    "while",
}


def try_safe_self_heal(
    spec: dict[str, Any],
    evidence_dir: Path,
    draft_path: Path,
    first: dict[str, Any],
    *,
    round_number: int = 1,
    append_events: bool = False,
) -> dict[str, Any]:
    text = draft_path.read_text(encoding="utf-8")
    keyword_param = next(
        (
            match.group(1)
            for match in re.finditer(
                r"(?<![#A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*:",
                text,
            )
            if match.group(1) in RUST_KEYWORDS
        ),
        None,
    )
    if keyword_param is None:
        return write_blocked_patch(
            spec,
            evidence_dir,
            draft_path,
            first["errors"],
            round_number=round_number,
            append_events=append_events,
        )

    patched = re.sub(
        rf"(?<![#A-Za-z0-9_]){re.escape(keyword_param)}(?![A-Za-z0-9_])",
        f"r#{keyword_param}",
        text,
    )
    if patched == text:
        return write_blocked_patch(
            spec,
            evidence_dir,
            draft_path,
            first["errors"],
            round_number=round_number,
            append_events=append_events,
        )

    draft_path.write_text(patched, encoding="utf-8")
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    base_event = {
        "schema_version": 1,
        "patch_id": f"patch-rust-keyword-identifiers-{round_number}",
        "target_id": spec.get("target_id"),
        "slice_id": slice_id,
        "round": round_number,
        "files": [{"path": rel(draft_path), "spans": [{"line_start": 1, "line_end": max(1, len(text.splitlines()))}]}],
        "reason": "Rust keyword used as generated identifier; convert to raw identifier without changing C oracle or fixture semantics.",
        "expected_error_delta": {
            "before": [rustc_error_code(error) for error in first["errors"]],
            "after_expected": [],
        },
        "forbidden_changes": [
            "c_oracle_contract",
            "fixture_expected_behavior",
            "accepted_metadata_differences",
            "public_api_outside_impact_set",
            "source_slice_boundary",
            "unsafe_budget_policy",
        ],
        "rollback_id": f"rollback-{slice_id}-keyword-identifiers-{round_number}",
        "ai_usage": {"used": False},
        "verification_commands": ["rustc --edition=2021 --crate-type=lib --error-format=json <draft>"],
    }
    write_patch_events(events_path, [{**base_event, "status": "applied"}], append=append_events)
    return {
        "patch_events": rel(events_path),
        "blocked_repairs": rel(evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"),
        "blocked_repairs_status": "recorded",
        "blocked_repairs_items": [],
        "status": "applied",
        "self_heal_applied": True,
        "_last_patch_event": base_event,
    }


def run_safe_self_heal_loop(
    spec: dict[str, Any],
    evidence_dir: Path,
    draft_path: Path,
    first: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = first
    for round_number in range(1, REPAIR_ROUND_LIMIT + 1):
        patch = try_safe_self_heal(
            spec,
            evidence_dir,
            draft_path,
            current,
            round_number=round_number,
            append_events=round_number > 1,
        )
        if not patch.get("self_heal_applied"):
            return current, patch
        current = rust_check_once(draft_path)
        if current["returncode"] == 0:
            return current, mark_self_heal_verified(spec, evidence_dir, patch)
    return current, write_blocked_patch(
        spec,
        evidence_dir,
        draft_path,
        current["errors"],
        round_number=REPAIR_ROUND_LIMIT,
        append_events=True,
    )


def mark_self_heal_verified(
    spec: dict[str, Any],
    evidence_dir: Path,
    patch: dict[str, Any],
) -> dict[str, Any]:
    slice_id = required_str(spec, "slice_id")
    events_path = evidence_dir / f"l3-{slice_id}-patch-events.jsonl"
    blocked_path = evidence_dir / f"l3-{slice_id}-self-healing-blocked-repairs.json"
    base_event = patch.get("_last_patch_event")
    if isinstance(base_event, dict):
        write_patch_events(events_path, [{**base_event, "status": "verified"}], append=True)
    blocked = blocked_repairs_payload(spec, [])
    write_json(blocked_path, blocked)
    visible_patch = dict(patch)
    visible_patch.pop("_last_patch_event", None)
    visible_patch.update(
        {
            "blocked_repairs": rel(blocked_path),
            "blocked_repairs_status": blocked["status"],
            "blocked_repairs_items": blocked["blocked_repairs"],
            "status": "recorded",
            "self_heal_applied": True,
        }
    )
    return visible_patch
