#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_ast_dump(
    clang_path: &Path,
    source_file: &Path,
    function_name: &str,
) -> Result<IrFunction, ClangFrontendError> {
    let arguments = clang_ast_dump_arguments(source_file);
    lower_function_from_clang_ast_dump_with_arguments(clang_path, &arguments, function_name)
}

#[cfg(feature = "typed-ir")]
fn lower_function_from_clang_ast_dump_with_arguments(
    clang_path: &Path,
    arguments: &[String],
    function_name: &str,
) -> Result<IrFunction, ClangFrontendError> {
    lower_function_and_globals_from_clang_ast_dump_with_arguments(
        clang_path,
        arguments,
        function_name,
    )
    .map(|lowered| lowered.function_ir)
}

#[cfg(feature = "typed-ir")]
fn lower_function_and_globals_from_clang_ast_dump_with_arguments(
    clang_path: &Path,
    arguments: &[String],
    function_name: &str,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    let ast = clang_ast_dump_json(clang_path, arguments)?;
    lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
}

#[cfg(feature = "typed-ir")]
fn clang_ast_dump_json(
    clang_path: &Path,
    arguments: &[String],
) -> Result<Value, ClangFrontendError> {
    let output = Command::new(clang_path)
        .args(arguments)
        .output()
        .map_err(|error| ClangFrontendError {
            kind: "clang_ast_dump_unavailable".to_string(),
            message: format!("failed to execute clang ast dump: {error}"),
        })?;
    if !output.status.success() {
        return Err(ClangFrontendError {
            kind: "clang_ast_dump_failed".to_string(),
            message: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        });
    }

    let ast: Value =
        serde_json::from_slice(&output.stdout).map_err(|error| ClangFrontendError {
            kind: "invalid_clang_ast_json".to_string(),
            message: format!("failed to parse clang AST JSON: {error}"),
        })?;
    Ok(ast)
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_parse_spec_report(
    environment: &BTreeMap<String, String>,
    parse_spec: &ClangParseSpec,
) -> ClangLoweringReport {
    let source_file = parse_spec.source_root.join(&parse_spec.source_file);
    let verified_context =
        match verified_parse_arguments(parse_spec) {
            Ok(context) => context,
            Err(error) => {
                return report_from_lowering_result(
                    Some(normalized_report_path(&source_file)),
                    parse_spec.function_name.clone(),
                    None,
                    Vec::new(),
                    environment,
                    Err(error),
                );
            }
        };
    let arguments =
        clang_ast_dump_arguments_with_extra(&source_file, &verified_context.arguments);
    let Some((clang_path, _clang_source)) = resolve_clang_path(environment) else {
        return ClangLoweringReport {
            status: "unavailable".to_string(),
            frontend: "clang".to_string(),
            source_file: Some(normalized_report_path(&source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![
                "CLANG_PATH is not set and no vendored clang binary found in tools/llvm/bin/ or tools/clang/bin/; clang AST lowering is unavailable".to_string()
            ],
            errors: vec![ClangFrontendError {
                kind: "missing_clang_path".to_string(),
                message: "clang AST lowering requires CLANG_PATH or a vendored clang binary".to_string(),
            }],
            function_ir: None,
            globals: Vec::new(),
            record_layout_evidence: None,
        };
    };

    let mut resolved_function_name = None;
    let layout_dump = match (
        verified_context.compile_database_sha256.as_deref(),
        parse_spec.target_abi.as_ref(),
    ) {
        (Some(compile_database_sha256), Some(target_abi)) => {
            shared_compile_arguments_sha256(&arguments).and_then(|arguments_sha256| {
                clang_record_layout_dump(
                    &clang_path,
                    &arguments,
                    &arguments_sha256,
                    compile_database_sha256,
                    target_abi,
                )
            })
        }
        _ => Err(ClangFrontendError {
            kind: "record_layout_provenance_unavailable".to_string(),
            message: "record-layout lowering requires hash-bound compile database and target ABI"
                .to_string(),
        }),
    };
    let mut used_record_layouts = Vec::new();
    let mut report = report_from_lowering_result(
        Some(normalized_report_path(&source_file)),
        parse_spec.function_name.clone(),
        Some(clang_path.to_string_lossy().to_string()),
        arguments.clone(),
        environment,
        clang_ast_dump_json(&clang_path, &arguments).and_then(|ast| {
            let selected_name = match parse_spec.function_source_span.as_ref() {
                Some(span) => source_span_selector::select_expanded_function_name_by_source_span(
                    &ast,
                    &source_file,
                    span,
                )?,
                None => parse_spec.function_name.clone(),
            };
            resolved_function_name = Some(selected_name.clone());
            let mut lowered =
                lower_function_and_globals_from_clang_ast_json_value_with_context(
                &ast,
                &selected_name,
                parse_spec.target_abi.as_ref(),
                layout_dump.as_ref().ok(),
                &mut used_record_layouts,
            )?;
            lowered.function_ir.name.clone_from(&parse_spec.function_name);
            Ok(lowered)
        }),
    );
    report.record_layout_evidence = Some(record_layout_evidence(
        layout_dump,
        used_record_layouts,
    ));
    if let Some(diagnostic) = verified_context.diagnostic {
        report.diagnostics.insert(0, diagnostic);
    }
    if let Some(selected_name) = resolved_function_name
        .filter(|selected_name| selected_name != &parse_spec.function_name)
    {
        report.diagnostics.push(format!(
            "source-span selection resolved macro-expanded FunctionDecl {selected_name}; emitted logical function name {}",
            parse_spec.function_name
        ));
    }
    report
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_ast_dump_report(
    environment: &BTreeMap<String, String>,
    source_file: &Path,
    function_name: &str,
) -> ClangLoweringReport {
    let arguments = clang_ast_dump_arguments(source_file);
    let Some((clang_path, _clang_source)) = resolve_clang_path(environment) else {
        return ClangLoweringReport {
            status: "unavailable".to_string(),
            frontend: "clang".to_string(),
            source_file: Some(normalized_report_path(source_file)),
            function_name: function_name.to_string(),
            clang_path: None,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![
                "CLANG_PATH is not set and no vendored clang binary found in tools/llvm/bin/ or tools/clang/bin/; clang AST lowering is unavailable".to_string()
            ],
            errors: vec![ClangFrontendError {
                kind: "missing_clang_path".to_string(),
                message: "clang AST lowering requires CLANG_PATH or a vendored clang binary".to_string(),
            }],
            function_ir: None,
            globals: Vec::new(),
            record_layout_evidence: None,
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(source_file)),
        function_name.to_string(),
        Some(clang_path.to_string_lossy().to_string()),
        arguments.clone(),
        environment,
        lower_function_and_globals_from_clang_ast_dump_with_arguments(
            &clang_path,
            &arguments,
            function_name,
        ),
    )
}
