
fn json_numeric_literal(value: &serde_json::Value) -> Option<String> {
    value
        .as_i64()
        .map(|value| value.to_string())
        .or_else(|| value.as_u64().map(|value| value.to_string()))
}

fn sanitize_path_fragment(value: &str) -> String {
    value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

fn resolve_repo_path(path_text: &str) -> PathBuf {
    let path = PathBuf::from(path_text);
    if path.is_absolute() || path.exists() {
        return path;
    }
    if let Ok(current_dir) = std::env::current_dir() {
        let candidate = current_dir.join(&path);
        if candidate.exists() {
            return candidate;
        }
    }
    if let Ok(manifest_dir) = std::env::var("CARGO_MANIFEST_DIR") {
        let crate_dir = PathBuf::from(&manifest_dir);
        if let Some(repo_root) = crate_dir.parent().and_then(Path::parent) {
            let candidate = repo_root.join(&path);
            if candidate.exists() {
                return candidate;
            }
        }
    }
    path
}

fn lower_parse_spec_from_ast_fixture_report(
    environment: &BTreeMap<String, String>,
    parse_spec: &clang_frontend::ClangParseSpec,
    ast_fixture: &str,
    diagnostics: Vec<String>,
) -> clang_frontend::ClangLoweringReport {
    let fixture_path = resolve_ast_fixture_path(ast_fixture);
    let logical_source_file = parse_spec.source_root.join(&parse_spec.source_file);

    let result = match fs::read_to_string(&fixture_path) {
        Ok(raw_json) => match serde_json::from_str::<serde_json::Value>(&raw_json) {
            Ok(ast) => {
                clang_frontend::lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
                    &ast,
                    &parse_spec.function_name,
                    parse_spec.target_abi.as_ref(),
                )
            }
            Err(error) => Err(clang_frontend::ClangFrontendError {
                kind: "invalid_ast_fixture_json".to_string(),
                message: format!(
                    "failed to parse clang AST JSON fixture {}: {error}",
                    normalize_path(&fixture_path)
                ),
            }),
        },
        Err(error) => Err(clang_frontend::ClangFrontendError {
            kind: "missing_ast_fixture".to_string(),
            message: format!(
                "failed to read clang AST JSON fixture {}: {error}",
                normalize_path(&fixture_path)
            ),
        }),
    };

    match result {
        Ok(lowered) => clang_frontend::ClangLoweringReport {
            status: "lowered".to_string(),
            frontend: "clang_ast_json_fixture".to_string(),
            source_file: Some(normalize_path(&logical_source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments: ast_fixture_arguments(parse_spec, &fixture_path),
            environment: clang_frontend::ClangEnvironment::detect_from_env(environment),
            diagnostics,
            errors: Vec::new(),
            function_ir: Some(lowered.function_ir),
            globals: lowered.globals,
            record_layout_evidence: None,
        },
        Err(error) => clang_frontend::ClangLoweringReport {
            status: "blocked".to_string(),
            frontend: "clang_ast_json_fixture".to_string(),
            source_file: Some(normalize_path(&logical_source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments: ast_fixture_arguments(parse_spec, &fixture_path),
            environment: clang_frontend::ClangEnvironment::detect_from_env(environment),
            diagnostics: diagnostics
                .into_iter()
                .chain(std::iter::once(error.message.clone()))
                .collect(),
            errors: vec![error],
            function_ir: None,
            globals: Vec::new(),
            record_layout_evidence: None,
        },
    }
}

fn resolve_ast_fixture_path(ast_fixture: &str) -> PathBuf {
    resolve_repo_path(ast_fixture)
}

fn ast_fixture_arguments(
    parse_spec: &clang_frontend::ClangParseSpec,
    fixture_path: &Path,
) -> Vec<String> {
    let mut arguments = parse_spec.clang_arguments();
    arguments.push("--ast-json-fixture".to_string());
    arguments.push(normalize_path(fixture_path));
    arguments.push(parse_spec.source_file.to_string_lossy().replace('\\', "/"));
    arguments
}

fn normalize_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

pub(crate) fn emit_policy_from_spec(spec: &SliceSpec) -> typed_ir::EmitPolicy {
    let signed_right_shift = if spec
        .c_boundary
        .scalar_arithmetic_contract
        .signed_right_shift
        == "explicit_implementation_defined_contract"
    {
        typed_ir::SignedRightShiftPolicy::ImplementationDefinedArithmetic
    } else {
        typed_ir::SignedRightShiftPolicy::FailClosed
    };
    typed_ir::EmitPolicy {
        signed_right_shift,
        noalias_param_pairs: noalias_param_pairs_from_spec(spec),
    }
}

fn noalias_param_pairs_from_spec(spec: &SliceSpec) -> Vec<typed_ir::NoAliasParamPair> {
    let inputs: Vec<&str> = spec
        .c_boundary
        .pointer_contract
        .input_buffers
        .iter()
        .map(|item| item.name.as_str())
        .collect();
    let outputs: Vec<&str> = spec
        .c_boundary
        .pointer_contract
        .output_pointers
        .iter()
        .map(|item| item.name.as_str())
        .collect();
    let declared_pointers: BTreeSet<&str> = inputs
        .iter()
        .chain(outputs.iter())
        .copied()
        .collect();
    spec.c_boundary
        .pointer_contract
        .noalias_required
        .iter()
        .filter_map(|pair| {
            let [left, right] = pair.as_slice() else {
                return None;
            };
            let left = left.as_str();
            let right = right.as_str();
            if inputs.contains(&left) && outputs.contains(&right) {
                Some(typed_ir::NoAliasParamPair {
                    readonly_param: left.to_string(),
                    mutable_param: right.to_string(),
                })
            } else if inputs.contains(&right) && outputs.contains(&left) {
                Some(typed_ir::NoAliasParamPair {
                    readonly_param: right.to_string(),
                    mutable_param: left.to_string(),
                })
            } else if declared_pointers.contains(left) && declared_pointers.contains(right) {
                Some(typed_ir::NoAliasParamPair {
                    readonly_param: left.to_string(),
                    mutable_param: right.to_string(),
                })
            } else {
                None
            }
        })
        .collect()
}
