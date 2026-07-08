fn emit_type_map(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    spec: &SliceSpec,
    result: &mut TranslationResult,
) {
    record_type_mapping("return", &function.return_type, &spec.build_profile, spec, result);
    for param in &function.params {
        record_type_mapping(&param.name, &param.c_type, &spec.build_profile, spec, result);
    }
    for statement in statements {
        if let Some(declaration) = parse_declaration(&statement.text) {
            record_type_mapping(
                &declaration.name,
                &declaration.c_type,
                &spec.build_profile,
                spec,
                result,
            );
        }
    }
}

pub(crate) fn record_type_mapping(
    symbol: &str,
    c_type: &str,
    profile: &BuildProfile,
    spec: &SliceSpec,
    result: &mut TranslationResult,
) {
    if let Some(rust_type) = map_c_type(c_type) {
        result.type_map.mappings.push(TypeMapping {
            c_type: c_type.to_string(),
            rust_type: rust_type.to_string(),
            symbol: symbol.to_string(),
            reason: "supported MVP C subset mapping".to_string(),
        });
        return;
    }
    if let Some(rust_type) = source_bound_record_pointer_type(c_type, spec) {
        result.type_map.mappings.push(TypeMapping {
            c_type: c_type.to_string(),
            rust_type,
            symbol: symbol.to_string(),
            reason: "source-bound record pointer typedef from slice direct dependencies".to_string(),
        });
        return;
    }

    let reason = if profile.clang_available {
        "type is outside the current bounded translator subset".to_string()
    } else {
        "clang-backed type extraction is unavailable for this unknown C type".to_string()
    };
    result.type_map.uncertainties.push(TypeUncertainty {
        symbol: symbol.to_string(),
        c_type: c_type.to_string(),
        reason: reason.clone(),
    });
    result.errors.push(TranslationError {
        kind: "type_uncertainty".to_string(),
        message: format!("{symbol}: {reason}"),
        source_span: Some(c_type.to_string()),
    });
}

fn map_c_type(c_type: &str) -> Option<&'static str> {
    match normalize_type(c_type).as_str() {
        "int" => Some("i32"),
        "unsigned int" => Some("u32"),
        "uint32_t" => Some("u32"),
        "uint8_t" => Some("u8"),
        "size_t" => Some("usize"),
        // Bare `char` is intentionally absent: its signedness is
        // implementation-defined (signed on the x86-64 Linux gcc target), so
        // mapping it to `u8` would silently flip sign-sensitive comparisons.
        // It falls through to the fail-closed type_uncertainty path instead.
        "unsigned char" => Some("u8"),
        "const char*" => Some("&str"),
        "const void*" => Some("&[u8]"),
        "const uint8_t*" => Some("&[u8]"),
        "const int*" => Some("&[i32]"),
        "int*" => Some("IntOutReport"),
        "struct sockaddr_in*" => Some("Ip4AddrReport"),
        "void" => Some("()"),
        _ => None,
    }
}

fn source_bound_record_pointer_type(c_type: &str, spec: &SliceSpec) -> Option<String> {
    let normalized = normalize_type(c_type);
    let base = normalized
        .trim_start_matches("const ")
        .trim_end_matches('*')
        .trim()
        .trim_start_matches("struct ")
        .to_string();
    if base.is_empty() {
        return None;
    }
    let is_source_bound_type = spec
        .c_boundary
        .direct_dependencies
        .iter()
        .any(|dependency| dependency.kind == "type" && dependency.name == base);
    if is_source_bound_type {
        Some(rust_record_type_name(c_type))
    } else {
        None
    }
}
