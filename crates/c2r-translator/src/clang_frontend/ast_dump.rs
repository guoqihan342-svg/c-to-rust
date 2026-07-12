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

#[cfg(feature = "typed-ir")]
pub fn lower_function_skeleton_report(
    function: &ClangFunctionSkeleton,
    environment: &BTreeMap<String, String>,
) -> ClangLoweringReport {
    report_from_lowering_result(
        None,
        function.name.clone(),
        None,
        Vec::new(),
        environment,
        lower_function_skeleton(function).map(|function_ir| LoweredFunctionWithGlobals {
            function_ir,
            globals: Vec::new(),
        }),
    )
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_skeleton(
    function: &ClangFunctionSkeleton,
) -> Result<IrFunction, ClangFrontendError> {
    Ok(IrFunction {
        name: function.name.clone(),
        return_type: lower_type(&function.return_type)?,
        params: function
            .params
            .iter()
            .map(|param| {
                Ok(IrParam {
                    name: param.name.clone(),
                    ty: lower_type(&param.ty)?,
                    source_span: None,
                })
            })
            .collect::<Result<Vec<_>, ClangFrontendError>>()?,
        body: function
            .body
            .iter()
            .map(lower_stmt)
            .collect::<Result<Vec<_>, ClangFrontendError>>()?,
        source_span: None,
    })
}

#[cfg(feature = "typed-ir")]
fn clang_ast_dump_arguments(source_file: &Path) -> Vec<String> {
    clang_ast_dump_arguments_with_extra(source_file, &[])
}

#[cfg(feature = "typed-ir")]
fn clang_ast_dump_arguments_with_extra(
    source_file: &Path,
    extra_arguments: &[String],
) -> Vec<String> {
    vec![
        "-Xclang".to_string(),
        "-ast-dump=json".to_string(),
        "-fsyntax-only".to_string(),
    ]
    .into_iter()
    .chain(extra_arguments.iter().cloned())
    .chain(std::iter::once(source_file.to_string_lossy().into_owned()))
    .collect()
}

#[cfg(feature = "typed-ir")]
struct VerifiedClangContext {
    arguments: Vec<String>,
    diagnostic: Option<String>,
    compile_database_sha256: Option<String>,
}

#[cfg(feature = "typed-ir")]
fn verified_parse_arguments(
    parse_spec: &ClangParseSpec,
) -> Result<VerifiedClangContext, ClangFrontendError> {
    let Some(command) = parse_spec.resolved_compile_command()? else {
        return Ok(VerifiedClangContext {
            arguments: parse_spec.clang_arguments(),
            diagnostic: None,
            compile_database_sha256: None,
        });
    };
    let mut arguments = without_captured_include_paths(&command.arguments)?;
    for include_path in parse_spec.resolved_include_paths() {
        let argument = format!("-I{}", include_path.to_string_lossy().replace('\\', "/"));
        if !arguments.contains(&argument) {
            arguments.push(argument);
        }
    }
    for define in &parse_spec.defines {
        let argument = format!("-D{define}");
        if !arguments.contains(&argument) {
            arguments.push(argument);
        }
    }
    Ok(VerifiedClangContext {
        arguments,
        diagnostic: Some(format!(
            "hash-bound compile database replay selected: path={}, sha256={}",
            parse_spec
                .compile_commands
                .as_ref()
                .map(CompileDatabaseRef::path)
                .unwrap_or_default(),
            command.database_sha256,
        )),
        compile_database_sha256: Some(command.database_sha256),
    })
}

#[cfg(feature = "typed-ir")]
fn without_captured_include_paths(
    arguments: &[String],
) -> Result<Vec<String>, ClangFrontendError> {
    let mut filtered = Vec::new();
    let mut index = 0usize;
    while index < arguments.len() {
        let argument = &arguments[index];
        if matches!(argument.as_str(), "-I" | "-isystem" | "-iquote" | "-idirafter" | "/I") {
            if index + 1 >= arguments.len() {
                return Err(ClangFrontendError {
                    kind: "invalid_compile_database_entry".to_string(),
                    message: format!("compile include flag {argument} requires a path"),
                });
            }
            index += 2;
            continue;
        }
        if (argument.starts_with("-I") && argument.len() > 2)
            || (argument.starts_with("/I") && argument.len() > 2)
            || argument.starts_with("-isystem=")
            || argument.starts_with("-iquote=")
            || argument.starts_with("-idirafter=")
        {
            index += 1;
            continue;
        }
        filtered.push(argument.clone());
        index += 1;
    }
    Ok(filtered)
}

#[cfg(feature = "typed-ir")]
fn report_from_lowering_result(
    source_file: Option<String>,
    function_name: String,
    clang_path: Option<String>,
    arguments: Vec<String>,
    environment: &BTreeMap<String, String>,
    result: Result<LoweredFunctionWithGlobals, ClangFrontendError>,
) -> ClangLoweringReport {
    match result {
        Ok(lowered) => ClangLoweringReport {
            status: "lowered".to_string(),
            frontend: "clang".to_string(),
            source_file,
            function_name,
            clang_path,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: Vec::new(),
            errors: Vec::new(),
            function_ir: Some(lowered.function_ir),
            globals: lowered.globals,
            record_layout_evidence: None,
        },
        Err(error) => ClangLoweringReport {
            status: lowering_status_for_error(&error).to_string(),
            frontend: "clang".to_string(),
            source_file,
            function_name,
            clang_path,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![error.message.clone()],
            errors: vec![error],
            function_ir: None,
            globals: Vec::new(),
            record_layout_evidence: None,
        },
    }
}

#[cfg(feature = "typed-ir")]
fn lowering_status_for_error(error: &ClangFrontendError) -> &'static str {
    if error.kind == "missing_clang_path" || error.kind == "clang_ast_dump_unavailable" {
        "unavailable"
    } else if error.kind.starts_with("unsupported_") {
        "unsupported"
    } else {
        "blocked"
    }
}
