
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
