use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

use crate::{
    clang_frontend, typed_ir, BuildProfile, CallExpressionEvidence, CfgBlock, CfgFunction,
    PointerNode, SliceSpec, TranslationError, TranslationPlan, TranslationResult,
    TranslationSource, TypeMapping, TypeUncertainty,
};

/// Collects process environment variables without panicking on non-Unicode
/// entries; `std::env::vars()` panics on the first non-UTF-8 key or value,
/// which on Linux hosts would crash artifact writing instead of failing closed.
pub(crate) fn collect_environment_lossy() -> BTreeMap<String, String> {
    std::env::vars_os()
        .map(|(key, value)| {
            (
                key.to_string_lossy().into_owned(),
                value.to_string_lossy().into_owned(),
            )
        })
        .collect()
}

pub(crate) struct ClangLoweredTranslationAttempt {
    pub report: clang_frontend::ClangLoweringReport,
    pub result: Option<TranslationResult>,
}

pub(crate) fn try_clang_lowered_translation_attempt(
    spec: &SliceSpec,
) -> Option<ClangLoweredTranslationAttempt> {
    let parse_spec = clang_frontend::ClangParseSpec::from_slice_spec(spec).ok()?;
    let environment = collect_environment_lossy();
    let report = lower_parse_spec_report_with_optional_ast_fixture_and_slice_source(
        &environment,
        &parse_spec,
        spec.build_profile.clang_ast_fixture.as_deref(),
        Some(spec),
    );
    let result = translation_result_from_clang_lowering_report(spec, &report);
    Some(ClangLoweredTranslationAttempt { report, result })
}

fn translation_result_from_clang_lowering_report(
    spec: &SliceSpec,
    report: &clang_frontend::ClangLoweringReport,
) -> Option<TranslationResult> {
    let function_ir = report.function_ir.as_ref()?;
    let rust_code = typed_ir::emit_rust_from_ir_with_globals_and_policy(
        function_ir,
        &report.globals,
        emit_policy_from_spec(spec),
    )
    .ok()?
    .rust;

    let mut result = TranslationResult {
        rust_code,
        translation_source: TranslationSource::selected("clang-lowered-typed-ir"),
        plan: TranslationPlan {
            target_id: spec.target_id.clone(),
            slice_id: spec.slice_id.clone(),
            function_name: spec.function_name.clone(),
            translation_rule_ids: vec!["clang-lowered-typed-ir".to_string()],
            call_expressions: Vec::new(),
            unsupported_node_count: 0,
            unsafe_candidate_count: 0,
        },
        ..TranslationResult::default()
    };
    record_clang_lowered_ir_evidence(spec, function_ir, &mut result);
    Some(result)
}

#[cfg(test)]
pub(crate) fn lower_parse_spec_report_with_optional_ast_fixture(
    environment: &BTreeMap<String, String>,
    parse_spec: &clang_frontend::ClangParseSpec,
    ast_fixture: Option<&str>,
) -> clang_frontend::ClangLoweringReport {
    lower_parse_spec_report_with_optional_ast_fixture_and_slice_source(
        environment,
        parse_spec,
        ast_fixture,
        None,
    )
}

pub(crate) fn lower_parse_spec_report_with_optional_ast_fixture_and_slice_source(
    environment: &BTreeMap<String, String>,
    parse_spec: &clang_frontend::ClangParseSpec,
    ast_fixture: Option<&str>,
    spec: Option<&SliceSpec>,
) -> clang_frontend::ClangLoweringReport {
    let Some(ast_fixture) = ast_fixture.map(str::trim).filter(|value| !value.is_empty()) else {
        if let Some(spec) = spec.and_then(|spec| {
            if spec.c_source.trim().is_empty() {
                None
            } else {
                Some(spec)
            }
        }) {
            return lower_parse_spec_from_slice_source_report(environment, parse_spec, spec);
        }
        return clang_frontend::lower_function_from_clang_parse_spec_report(
            environment,
            parse_spec,
        );
    };

    lower_parse_spec_from_ast_fixture_report(
        environment,
        parse_spec,
        ast_fixture,
        vec![format!(
            "clang AST JSON fixture replay selected from slice spec; external clang AST dump was not invoked: {}",
            normalize_path(&resolve_ast_fixture_path(ast_fixture))
        )],
    )
}

fn lower_parse_spec_from_slice_source_report(
    environment: &BTreeMap<String, String>,
    parse_spec: &clang_frontend::ClangParseSpec,
    spec: &SliceSpec,
) -> clang_frontend::ClangLoweringReport {
    let logical_source_file = parse_spec.source_root.join(&parse_spec.source_file);
    let source = slice_source_translation_unit(spec);
    let temp_source = std::env::temp_dir().join(format!(
        "c2r-slice-source-{}-{}-{}.c",
        sanitize_path_fragment(&spec.target_id),
        sanitize_path_fragment(&spec.slice_id),
        std::process::id()
    ));

    if let Err(error) = fs::write(&temp_source, source) {
        return clang_frontend::ClangLoweringReport {
            status: "blocked".to_string(),
            frontend: "clang_slice_source".to_string(),
            source_file: Some(normalize_path(&logical_source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments: slice_source_arguments(parse_spec, &temp_source),
            environment: clang_frontend::ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![format!(
                "failed to write temporary slice-source translation unit {}: {error}",
                normalize_path(&temp_source)
            )],
            errors: vec![clang_frontend::ClangFrontendError {
                kind: "slice_source_temp_write_failed".to_string(),
                message: format!(
                    "failed to write temporary slice-source translation unit {}: {error}",
                    normalize_path(&temp_source)
                ),
            }],
            function_ir: None,
            globals: Vec::new(),
        };
    }

    let mut temp_parse_spec = parse_spec.clone();
    temp_parse_spec.source_root = PathBuf::from(".");
    temp_parse_spec.source_file = temp_source.clone();
    temp_parse_spec.include_paths = Vec::new();
    temp_parse_spec.compile_commands = None;
    temp_parse_spec.source_file_hashes = BTreeMap::new();
    temp_parse_spec.function_source_span = None;

    let mut report =
        clang_frontend::lower_function_from_clang_parse_spec_report(environment, &temp_parse_spec);
    report.frontend = "clang_slice_source".to_string();
    report.source_file = Some(normalize_path(&logical_source_file));
    report.arguments = slice_source_arguments(parse_spec, &temp_source);
    report.diagnostics.insert(
        0,
        "clang lowering used slice-spec c_source with declared external callee prototypes; project macros were not expanded"
            .to_string(),
    );
    report
}

fn slice_source_arguments(
    parse_spec: &clang_frontend::ClangParseSpec,
    temp_source: &Path,
) -> Vec<String> {
    let mut arguments = parse_spec.clang_arguments();
    arguments.push("--slice-source-from-spec".to_string());
    arguments.push(normalize_path(temp_source));
    arguments.push(parse_spec.source_file.to_string_lossy().replace('\\', "/"));
    arguments
}

fn slice_source_translation_unit(spec: &SliceSpec) -> String {
    let mut source = String::new();
    source.push_str("#include <stdbool.h>\n#include <stddef.h>\n#include <stdint.h>\n\n");
    source.push_str(&slice_source_struct_declarations(spec));
    source.push_str(&slice_source_typedefs(spec));
    source.push_str(&slice_source_constants(spec));
    source.push_str(&slice_source_function_prototypes(spec));
    source.push_str(&slice_source_global_dependency_definitions(spec));
    source.push('\n');
    source.push_str(&spec.c_source);
    source.push('\n');
    source
}

fn slice_source_global_dependency_definitions(spec: &SliceSpec) -> String {
    let mut definitions = String::new();
    let mut seen_spans = BTreeSet::new();
    for dependency in &spec.c_boundary.direct_dependencies {
        if dependency.kind != "global" {
            continue;
        }
        let Some(span) = &dependency.source_span else {
            continue;
        };
        if span.file.trim().is_empty() || span.byte_end <= span.byte_start {
            continue;
        }
        let key = (span.file.clone(), span.byte_start, span.byte_end);
        if !seen_spans.insert(key) {
            continue;
        }
        let Some(fragment) = source_span_fragment(spec, span) else {
            continue;
        };
        let Some(fragment) = trim_global_dependency_fragment(&fragment, &dependency.name) else {
            continue;
        };
        definitions.push_str(&fragment);
        if !fragment.ends_with('\n') {
            definitions.push('\n');
        }
        definitions.push('\n');
    }
    definitions
}

fn source_span_fragment(spec: &SliceSpec, span: &crate::SourceSpanRef) -> Option<String> {
    let source_path = if let Some(source_root) = spec.source_root.as_deref() {
        resolve_repo_path(source_root).join(&span.file)
    } else {
        resolve_repo_path(&span.file)
    };
    let source = fs::read_to_string(source_path).ok()?;
    if span.line_start > 0 && span.line_end >= span.line_start {
        let line_start = usize::try_from(span.line_start - 1).ok()?;
        let line_end = usize::try_from(span.line_end).ok()?;
        let lines = source.lines().collect::<Vec<_>>();
        if line_end <= lines.len() {
            return Some(lines[line_start..line_end].join("\n") + "\n");
        }
    }
    let start = usize::try_from(span.byte_start).ok()?;
    let end = usize::try_from(span.byte_end).ok()?;
    if start >= end || end > source.len() || !source.is_char_boundary(start) || !source.is_char_boundary(end) {
        return None;
    }
    Some(source[start..end].to_string())
}

fn trim_global_dependency_fragment(fragment: &str, name: &str) -> Option<String> {
    let name = name.trim();
    if name.is_empty() {
        return None;
    }
    for (index, _) in fragment.match_indices(name) {
        let before = fragment[..index].chars().next_back();
        let after = fragment[index + name.len()..].chars().next();
        if before.is_some_and(is_c_identifier_char) || after.is_some_and(is_c_identifier_char) {
            continue;
        }
        let line_start = fragment[..index].rfind('\n').map_or(0, |pos| pos + 1);
        return Some(fragment[line_start..].to_string());
    }
    None
}

fn is_c_identifier_char(ch: char) -> bool {
    ch == '_' || ch.is_ascii_alphanumeric()
}

fn slice_source_struct_declarations(spec: &SliceSpec) -> String {
    let mut structs = collect_struct_names(&spec.c_source);
    for signature in &spec.c_boundary.signatures {
        collect_struct_names_from_type(&signature.return_type, &mut structs);
        for parameter in &signature.parameters {
            collect_struct_names_from_type(&parameter.c_type, &mut structs);
        }
    }
    let complete_source_structs = collect_complete_struct_names(&spec.c_source);
    let accepted_record_fields = collect_accepted_named_slice_record_fields(spec);
    let field_placeholders = collect_signature_record_pointer_field_placeholders(spec);

    structs
        .into_iter()
        .map(|name| {
            if complete_source_structs.contains(&name) {
                return format!("struct {name};\n");
            }
            if let Some(fields) = accepted_record_fields
                .get(&name)
                .filter(|fields| !fields.is_empty())
            {
                let mut declaration = format!("struct {name} {{\n");
                for field in fields {
                    declaration.push_str(&format!("    {} {};\n", field.c_type, field.name));
                }
                declaration.push_str("};\n");
                return declaration;
            }
            let Some(fields) = field_placeholders.get(&name).filter(|fields| !fields.is_empty())
            else {
                return format!("struct {name} {{ unsigned char _c2r_opaque; }};\n");
            };
            let mut declaration = format!("struct {name} {{\n");
            for field in fields {
                declaration.push_str(&format!("    int {field};\n"));
            }
            declaration.push_str("    unsigned char _c2r_opaque;\n};\n");
            declaration
        })
        .collect::<String>()
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct SliceSourceRecordField {
    name: String,
    c_type: String,
}

fn collect_accepted_named_slice_record_fields(
    spec: &SliceSpec,
) -> BTreeMap<String, Vec<SliceSourceRecordField>> {
    let mut result = BTreeMap::new();
    for callee in &spec.c_boundary.external_direct_callees {
        let Some(evidence) = &callee.accepted_named_slice_evidence else {
            continue;
        };
        let Some(report_path) = accepted_named_slice_clang_lowering_report_path(evidence) else {
            continue;
        };
        for (record_name, fields) in record_fields_from_clang_lowering_report(&report_path) {
            result.entry(record_name).or_insert(fields);
        }
    }
    result
}

fn accepted_named_slice_clang_lowering_report_path(
    evidence: &crate::AcceptedNamedSliceEvidence,
) -> Option<PathBuf> {
    let final_verification = evidence.final_verification.trim();
    if final_verification.is_empty() {
        return None;
    }
    let final_path = resolve_repo_path(final_verification);
    let final_value: serde_json::Value = serde_json::from_str(&fs::read_to_string(&final_path).ok()?).ok()?;
    if !final_verification_accepts_named_slice(&final_value) {
        return None;
    }

    if let Some(manifest_path) =
        sibling_path_with_replaced_file_name(&final_path, "final-verification", "evidence-manifest")
    {
        if let Some(report_path) = clang_lowering_report_path_from_manifest(&manifest_path) {
            return Some(report_path);
        }
    }

    sibling_path_with_replaced_file_name(&final_path, "final-verification", "clang-lowering-report")
        .filter(|path| path.exists())
}

fn final_verification_accepts_named_slice(value: &serde_json::Value) -> bool {
    let status_passed = value
        .get("status")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|status| status == "passed");
    let semantic_pass = value
        .get("semantic_pass")
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);
    status_passed && semantic_pass
}

fn clang_lowering_report_path_from_manifest(manifest_path: &Path) -> Option<PathBuf> {
    let value: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(manifest_path).ok()?).ok()?;
    let report = value
        .pointer("/evidence/clang_lowering_report")
        .and_then(serde_json::Value::as_object)?;
    let status_recorded = report
        .get("status")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|status| status == "recorded" || status == "passed");
    if !status_recorded {
        return None;
    }
    report
        .get("path")
        .and_then(serde_json::Value::as_str)
        .map(resolve_repo_path)
        .filter(|path| path.exists())
}

fn sibling_path_with_replaced_file_name(path: &Path, needle: &str, replacement: &str) -> Option<PathBuf> {
    let file_name = path.file_name()?.to_str()?;
    let replaced = file_name.replace(needle, replacement);
    (replaced != file_name).then(|| path.with_file_name(replaced))
}

fn record_fields_from_clang_lowering_report(
    report_path: &Path,
) -> BTreeMap<String, Vec<SliceSourceRecordField>> {
    let Ok(raw_json) = fs::read_to_string(report_path) else {
        return BTreeMap::new();
    };
    let Ok(report) = serde_json::from_str::<serde_json::Value>(&raw_json) else {
        return BTreeMap::new();
    };
    let root = report
        .pointer("/lowering_report/function_ir")
        .or_else(|| report.get("function_ir"))
        .unwrap_or(&report);
    let mut result = BTreeMap::new();
    collect_record_fields_from_json_value(root, &mut result);
    result
}

fn collect_record_fields_from_json_value(
    value: &serde_json::Value,
    records: &mut BTreeMap<String, Vec<SliceSourceRecordField>>,
) {
    match value {
        serde_json::Value::Object(object) => {
            if let Some(record) = object.get("kind").and_then(|kind| kind.get("Record")) {
                collect_record_fields_from_record_kind(record, records);
            }
            for child in object.values() {
                collect_record_fields_from_json_value(child, records);
            }
        }
        serde_json::Value::Array(items) => {
            for item in items {
                collect_record_fields_from_json_value(item, records);
            }
        }
        _ => {}
    }
}

fn collect_record_fields_from_record_kind(
    record: &serde_json::Value,
    records: &mut BTreeMap<String, Vec<SliceSourceRecordField>>,
) {
    let Some(name) = record
        .get("name")
        .and_then(serde_json::Value::as_str)
        .filter(|name| is_c_identifier(name))
    else {
        return;
    };
    let Some(fields) = record.get("fields").and_then(serde_json::Value::as_array) else {
        return;
    };
    if fields.is_empty() {
        return;
    }

    let mut declarations = Vec::new();
    for field in fields {
        let Some(field_name) = field
            .get("name")
            .and_then(serde_json::Value::as_str)
            .filter(|name| is_c_identifier(name))
        else {
            return;
        };
        let Some(c_type) = field
            .get("ty")
            .and_then(c_field_type_from_typed_ir_json)
        else {
            return;
        };
        declarations.push(SliceSourceRecordField {
            name: field_name.to_string(),
            c_type,
        });
    }
    records.entry(name.to_string()).or_insert(declarations);
}

fn c_field_type_from_typed_ir_json(ty: &serde_json::Value) -> Option<String> {
    ty.get("spelled")
        .and_then(serde_json::Value::as_str)
        .and_then(normalize_supported_c_field_type)
        .or_else(|| {
            ty.get("canonical")
                .and_then(serde_json::Value::as_str)
                .and_then(normalize_supported_c_field_type)
        })
}

fn normalize_supported_c_field_type(candidate: &str) -> Option<String> {
    let trimmed = candidate.trim();
    if trimmed.is_empty()
        || !trimmed
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'*' || byte.is_ascii_whitespace())
    {
        return None;
    }
    let tokens = c_identifier_tokens(trimmed);
    if tokens.is_empty() || tokens.iter().any(|token| !is_builtin_type_token(token)) {
        return None;
    }
    if tokens.len() == 1 && tokens[0] == "void" && !trimmed.contains('*') {
        return None;
    }
    Some(normalize_c_type_spacing(trimmed))
}

fn normalize_c_type_spacing(value: &str) -> String {
    let mut result = String::new();
    let mut previous_was_space = false;
    for ch in value.trim().chars() {
        if ch.is_whitespace() {
            if !previous_was_space {
                result.push(' ');
                previous_was_space = true;
            }
        } else {
            result.push(ch);
            previous_was_space = false;
        }
    }
    result
}

fn collect_signature_record_pointer_field_placeholders(
    spec: &SliceSpec,
) -> BTreeMap<String, BTreeSet<String>> {
    let mut record_pointer_params: BTreeMap<String, String> = BTreeMap::new();
    for signature in &spec.c_boundary.signatures {
        for parameter in &signature.parameters {
            if let Some(record_name) = record_pointer_type_name(&parameter.c_type) {
                record_pointer_params.insert(parameter.name.clone(), record_name);
            }
        }
    }
    collect_record_pointer_arrow_field_uses(&spec.c_source, &record_pointer_params)
}

fn collect_record_pointer_arrow_field_uses(
    source: &str,
    record_pointer_params: &BTreeMap<String, String>,
) -> BTreeMap<String, BTreeSet<String>> {
    let searchable_source = c_source_without_strings_and_comments(source);
    let bytes = searchable_source.as_bytes();
    let mut result: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_c_ident_start(bytes[index]) {
            index += 1;
            continue;
        }
        let base_start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        let base = &searchable_source[base_start..index];
        let mut lookahead = index;
        while lookahead < bytes.len() && bytes[lookahead].is_ascii_whitespace() {
            lookahead += 1;
        }
        if lookahead + 1 >= bytes.len() || bytes[lookahead] != b'-' || bytes[lookahead + 1] != b'>'
        {
            continue;
        }
        lookahead += 2;
        while lookahead < bytes.len() && bytes[lookahead].is_ascii_whitespace() {
            lookahead += 1;
        }
        if lookahead >= bytes.len() || !is_c_ident_start(bytes[lookahead]) {
            continue;
        }
        let field_start = lookahead;
        lookahead += 1;
        while lookahead < bytes.len() && is_c_ident_continue(bytes[lookahead]) {
            lookahead += 1;
        }
        let field = &searchable_source[field_start..lookahead];
        if let Some(record_name) = record_pointer_params.get(base) {
            result
                .entry(record_name.clone())
                .or_default()
                .insert(field.to_string());
        }
    }
    result
}

fn record_pointer_type_name(c_type: &str) -> Option<String> {
    if !c_type.contains('*') {
        return None;
    }
    let tokens = c_identifier_tokens(c_type);
    for window in tokens.windows(2) {
        if window[0] == "struct" && !is_builtin_type_token(&window[1]) {
            return Some(window[1].clone());
        }
    }
    None
}

fn slice_source_typedefs(spec: &SliceSpec) -> String {
    let mut aliases: BTreeMap<String, &'static str> = BTreeMap::new();
    let mut structs = collect_struct_names(&spec.c_source);
    for signature in &spec.c_boundary.signatures {
        collect_struct_names_from_type(&signature.return_type, &mut structs);
        for parameter in &signature.parameters {
            collect_struct_names_from_type(&parameter.c_type, &mut structs);
        }
    }
    for signature in &spec.c_boundary.signatures {
        collect_typedef_alias_from_type(&signature.return_type, true, &mut aliases);
        for parameter in &signature.parameters {
            collect_typedef_alias_from_type(&parameter.c_type, false, &mut aliases);
        }
    }
    collect_typedef_alias_from_type(
        spec.c_boundary
            .signatures
            .iter()
            .find(|signature| signature.function == spec.function_name)
            .map(|signature| signature.return_type.as_str())
            .unwrap_or_default(),
        true,
        &mut aliases,
    );

    aliases
        .into_iter()
        .map(|(name, kind)| match kind {
            "int" => format!("typedef int {name};\n"),
            _ if record_name_for_typedef_alias(&name, &structs).is_some() => {
                let record = record_name_for_typedef_alias(&name, &structs)
                    .expect("record alias checked above");
                format!("typedef struct {record} *{name};\n")
            }
            _ => format!("typedef void *{name};\n"),
        })
        .collect::<String>()
}

fn slice_source_constants(spec: &SliceSpec) -> String {
    let mut constants: BTreeMap<String, String> = BTreeMap::new();
    let build_profile_defines = build_profile_define_names(spec);
    for dependency in &spec.c_boundary.direct_dependencies {
        if dependency.kind != "constant" || dependency.name.trim().is_empty() {
            continue;
        }
        if build_profile_defines.contains(&dependency.name) {
            continue;
        }
        if let Some(value) = dependency.value.as_ref().and_then(json_numeric_literal) {
            constants.insert(dependency.name.clone(), value);
        }
    }
    for name in collect_object_like_uppercase_identifiers(&spec.c_source) {
        if build_profile_defines.contains(&name) {
            continue;
        }
        constants.entry(name).or_insert_with(|| "0".to_string());
    }

    constants
        .into_iter()
        .map(|(name, value)| format!("enum {{ {name} = {value} }};\n"))
        .collect::<String>()
}

fn build_profile_define_names(spec: &SliceSpec) -> BTreeSet<String> {
    spec.build_profile
        .defines
        .iter()
        .filter_map(|define| {
            let name = define.split_once('=').map(|(name, _)| name).unwrap_or(define);
            let name = name.trim();
            (!name.is_empty()
                && name.as_bytes().first().is_some_and(|byte| is_c_ident_start(*byte))
                && name.bytes().all(is_c_ident_continue))
            .then(|| name.to_string())
        })
        .collect()
}

fn slice_source_function_prototypes(spec: &SliceSpec) -> String {
    spec.c_boundary
        .signatures
        .iter()
        .filter(|signature| {
            !signature.function.trim().is_empty() && signature.function != spec.function_name
        })
        .map(signature_prototype)
        .collect::<String>()
}

fn signature_prototype(signature: &crate::CSignature) -> String {
    let params = if signature.parameters.is_empty() {
        "void".to_string()
    } else {
        signature
            .parameters
            .iter()
            .enumerate()
            .map(|(index, parameter)| {
                let name = if parameter.name.trim().is_empty() {
                    format!("arg{index}")
                } else {
                    parameter.name.clone()
                };
                format!("{} {}", parameter.c_type.trim(), name)
            })
            .collect::<Vec<_>>()
            .join(", ")
    };
    format!(
        "{} {}({});\n",
        signature.return_type.trim(),
        signature.function.trim(),
        params
    )
}

fn collect_struct_names(source: &str) -> BTreeSet<String> {
    let tokens = c_identifier_tokens(source);
    let mut names = BTreeSet::new();
    for window in tokens.windows(2) {
        if window[0] == "struct" && !is_builtin_type_token(&window[1]) {
            names.insert(window[1].clone());
        }
    }
    names
}

fn collect_complete_struct_names(source: &str) -> BTreeSet<String> {
    let searchable_source = c_source_without_strings_and_comments(source);
    let bytes = searchable_source.as_bytes();
    let mut names = BTreeSet::new();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_c_ident_start(bytes[index]) {
            index += 1;
            continue;
        }
        let keyword_start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        if &searchable_source[keyword_start..index] != "struct" {
            continue;
        }

        while index < bytes.len() && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        if index >= bytes.len() || !is_c_ident_start(bytes[index]) {
            continue;
        }
        let name_start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        let name = &searchable_source[name_start..index];
        while index < bytes.len() && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        if index < bytes.len() && bytes[index] == b'{' {
            names.insert(name.to_string());
        }
    }
    names
}

fn collect_struct_names_from_type(c_type: &str, names: &mut BTreeSet<String>) {
    let tokens = c_identifier_tokens(c_type);
    for window in tokens.windows(2) {
        if window[0] == "struct" && !is_builtin_type_token(&window[1]) {
            names.insert(window[1].clone());
        }
    }
}

fn collect_typedef_alias_from_type(
    c_type: &str,
    return_position: bool,
    aliases: &mut BTreeMap<String, &'static str>,
) {
    let mut previous_was_struct = false;
    for token in c_identifier_tokens(c_type) {
        if previous_was_struct {
            previous_was_struct = false;
            continue;
        }
        if token == "struct" {
            previous_was_struct = true;
            continue;
        }
        if is_builtin_type_token(&token) {
            continue;
        }
        let kind = if token.ends_with("_err_t") || (return_position && !token.ends_with("_t")) {
            "int"
        } else {
            "void_ptr"
        };
        aliases.entry(token).or_insert(kind);
    }
}

fn record_name_for_typedef_alias<'a>(
    alias: &str,
    structs: &'a BTreeSet<String>,
) -> Option<&'a str> {
    let record = alias.strip_suffix("_t")?;
    structs.get(record).map(String::as_str)
}

fn collect_object_like_uppercase_identifiers(source: &str) -> BTreeSet<String> {
    let mut result = BTreeSet::new();
    let searchable_source = c_source_without_strings_and_comments(source);
    let bytes = searchable_source.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_c_ident_start(bytes[index]) {
            index += 1;
            continue;
        }
        let start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        let ident = &source[start..index];
        let mut lookahead = index;
        while lookahead < bytes.len() && bytes[lookahead].is_ascii_whitespace() {
            lookahead += 1;
        }
        if ident.chars().any(|ch| ch.is_ascii_lowercase())
            || !ident.chars().any(|ch| ch.is_ascii_uppercase())
            || is_reserved_object_like_identifier(ident)
            || (lookahead < bytes.len() && bytes[lookahead] == b'(')
        {
            continue;
        }
        result.insert(ident.to_string());
    }
    result
}

fn c_source_without_strings_and_comments(source: &str) -> String {
    let mut result = String::with_capacity(source.len());
    let bytes = source.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index] == b'"' || bytes[index] == b'\'' {
            let quote = bytes[index];
            push_identifier_scan_blank(&mut result, bytes[index]);
            index += 1;
            while index < bytes.len() {
                let byte = bytes[index];
                if byte == b'\\' {
                    push_identifier_scan_blank(&mut result, byte);
                    index += 1;
                    if index < bytes.len() {
                        push_identifier_scan_blank(&mut result, bytes[index]);
                        index += 1;
                    }
                    continue;
                }
                push_identifier_scan_blank(&mut result, byte);
                index += 1;
                if byte == quote {
                    break;
                }
            }
            continue;
        }
        if bytes[index] == b'/' && index + 1 < bytes.len() && bytes[index + 1] == b'/' {
            push_identifier_scan_blank(&mut result, bytes[index]);
            push_identifier_scan_blank(&mut result, bytes[index + 1]);
            index += 2;
            while index < bytes.len() {
                let byte = bytes[index];
                push_identifier_scan_blank(&mut result, byte);
                index += 1;
                if byte == b'\n' {
                    break;
                }
            }
            continue;
        }
        if bytes[index] == b'/' && index + 1 < bytes.len() && bytes[index + 1] == b'*' {
            push_identifier_scan_blank(&mut result, bytes[index]);
            push_identifier_scan_blank(&mut result, bytes[index + 1]);
            index += 2;
            while index < bytes.len() {
                let byte = bytes[index];
                if byte == b'*' && index + 1 < bytes.len() && bytes[index + 1] == b'/' {
                    push_identifier_scan_blank(&mut result, byte);
                    push_identifier_scan_blank(&mut result, bytes[index + 1]);
                    index += 2;
                    break;
                }
                push_identifier_scan_blank(&mut result, byte);
                index += 1;
            }
            continue;
        }
        if bytes[index].is_ascii() {
            result.push(bytes[index] as char);
        } else {
            result.push(' ');
        }
        index += 1;
    }
    result
}

fn push_identifier_scan_blank(result: &mut String, byte: u8) {
    if byte == b'\n' {
        result.push('\n');
    } else {
        result.push(' ');
    }
}

fn is_reserved_object_like_identifier(ident: &str) -> bool {
    matches!(ident, "NULL")
}

fn c_identifier_tokens(text: &str) -> Vec<String> {
    text.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
        .filter(|token| !token.is_empty())
        .map(str::to_string)
        .collect()
}

fn is_builtin_type_token(token: &str) -> bool {
    matches!(
        token,
        "void"
            | "char"
            | "signed"
            | "unsigned"
            | "short"
            | "int"
            | "long"
            | "float"
            | "double"
            | "const"
            | "volatile"
            | "restrict"
            | "bool"
            | "_Bool"
            | "size_t"
            | "int8_t"
            | "uint8_t"
            | "int16_t"
            | "uint16_t"
            | "int32_t"
            | "uint32_t"
            | "int64_t"
            | "uint64_t"
    )
}

fn is_c_ident_start(byte: u8) -> bool {
    byte == b'_' || byte.is_ascii_alphabetic()
}

fn is_c_ident_continue(byte: u8) -> bool {
    byte == b'_' || byte.is_ascii_alphanumeric()
}

fn is_c_identifier(value: &str) -> bool {
    let mut bytes = value.bytes();
    let Some(first) = bytes.next() else {
        return false;
    };
    is_c_ident_start(first) && bytes.all(is_c_ident_continue)
}

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

/// Mirrors an already-emitted typed IR function into translator evidence.
///
/// Rust code has already been produced by `typed_ir` before this runs. The job
/// here is to describe the semantic route that was accepted: type mappings,
/// call expressions, coarse CFG shape, pointer boundaries, and rule ids.
fn record_clang_lowered_ir_evidence(
    spec: &SliceSpec,
    function: &typed_ir::IrFunction,
    result: &mut TranslationResult,
) {
    record_ir_type_mapping("return", &function.return_type, &spec.build_profile, result);
    for param in &function.params {
        let rust_type_override = ir_param_type_map_rust_override(function, param);
        record_ir_type_mapping_with_rust_type_override(
            &param.name,
            &param.ty,
            &spec.build_profile,
            rust_type_override,
            result,
        );
    }
    record_ir_decl_type_mappings(&function.body, &spec.build_profile, result);
    record_ir_call_expression_evidence(&function.body, result);
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks: vec![CfgBlock {
            id: "entry".to_string(),
            statements: function.body.iter().map(ir_statement_label).collect(),
            statement_kinds: ir_statement_kind_labels(&function.body),
            lvalue_kinds: Vec::new(),
            terminator: if function
                .body
                .iter()
                .any(|stmt| matches!(stmt, typed_ir::IrStmt::Return { .. }))
            {
                "return".to_string()
            } else {
                "fallthrough".to_string()
            },
            edges: ir_cfg_edges(&function.body),
        }],
        unsupported_control_flow: Vec::new(),
        structured_control_flow: None,
    });
    emit_ir_pointer_graph(function, result);
    push_rule_once(
        &mut result.plan.translation_rule_ids,
        "clang-lowered-typed-ir",
    );
    if ir_has_byte_cursor_read(function, "buf") {
        for rule in [
            "const-void-byte-slice",
            "byte-cursor-post-increment-read",
            "byte-cursor-loop",
            "structured-while",
            "structured-return-expression",
        ] {
            push_rule_once(&mut result.plan.translation_rule_ids, rule);
        }
    }
}

fn record_ir_decl_type_mappings(
    statements: &[typed_ir::IrStmt],
    profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl { name, ty, .. } => {
                record_ir_type_mapping(name, ty, profile, result);
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                record_ir_decl_type_mappings(then_body, profile, result);
                record_ir_decl_type_mappings(else_body, profile, result);
            }
            typed_ir::IrStmt::While { body, .. } => {
                record_ir_decl_type_mappings(body, profile, result);
            }
            typed_ir::IrStmt::DoWhile { body, .. } => {
                record_ir_decl_type_mappings(body, profile, result);
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                record_ir_decl_type_mappings(init, profile, result);
                record_ir_decl_type_mappings(body, profile, result);
                if let Some(step) = step.as_deref() {
                    record_ir_decl_type_mappings(std::slice::from_ref(step), profile, result);
                }
            }
            _ => {}
        }
    }
}

/// Records direct-call evidence across all statement positions in typed IR.
///
/// The traversal keeps statement context labels because the validation reports
/// need to distinguish calls in initializers, assignments, loop conditions, and
/// returns. It recurses through nested control flow without changing the IR.
fn record_ir_call_expression_evidence(
    statements: &[typed_ir::IrStmt],
    result: &mut TranslationResult,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl {
                init: Some(init), ..
            } => {
                record_ir_call_expression_evidence_for_expr(init, "declaration_initializer", result)
            }
            typed_ir::IrStmt::Decl { init: None, .. } => {}
            typed_ir::IrStmt::Assign { value, .. } => {
                record_ir_call_expression_evidence_for_expr(value, "assignment", result);
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                record_ir_call_expression_evidence(then_body, result);
                record_ir_call_expression_evidence(else_body, result);
            }
            typed_ir::IrStmt::While { body, .. } => {
                record_ir_call_expression_evidence(body, result);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                record_ir_call_expression_evidence(body, result);
                record_ir_call_expression_evidence_for_expr(
                    condition,
                    "do_while_condition",
                    result,
                );
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                record_ir_call_expression_evidence(init, result);
                record_ir_call_expression_evidence(body, result);
                if let Some(step) = step.as_deref() {
                    record_ir_call_expression_evidence(std::slice::from_ref(step), result);
                }
            }
            typed_ir::IrStmt::Return {
                value: Some(value), ..
            } => record_ir_call_expression_evidence_for_expr(value, "return", result),
            typed_ir::IrStmt::Return { value: None, .. } => {}
            typed_ir::IrStmt::Break { .. } | typed_ir::IrStmt::Continue { .. } => {}
            typed_ir::IrStmt::Expr { expr, .. } => {
                record_ir_call_expression_evidence_for_expr(expr, "expression", result);
            }
            typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

fn record_ir_call_expression_evidence_for_expr(
    expr: &typed_ir::IrExpr,
    statement_context: &str,
    result: &mut TranslationResult,
) {
    match expr {
        typed_ir::IrExpr::Call { callee, args, .. } => {
            let arguments = args.iter().map(ir_expr_source_text).collect::<Vec<_>>();
            let call = CallExpressionEvidence {
                callee: callee.clone(),
                source_expression: format!("{callee}({})", arguments.join(", ")),
                arguments,
                statement_context: statement_context.to_string(),
            };
            result.plan.call_expressions.push(call);
            push_rule_once(
                &mut result.plan.translation_rule_ids,
                "bounded-call-expression",
            );
            for arg in args {
                record_ir_call_expression_evidence_for_expr(arg, statement_context, result);
            }
        }
        typed_ir::IrExpr::Binary { lhs, rhs, .. } => {
            record_ir_call_expression_evidence_for_expr(lhs, statement_context, result);
            record_ir_call_expression_evidence_for_expr(rhs, statement_context, result);
        }
        typed_ir::IrExpr::Unary { operand, .. } => {
            record_ir_call_expression_evidence_for_expr(operand, statement_context, result);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            record_ir_call_expression_evidence_for_expr(condition, statement_context, result);
            record_ir_call_expression_evidence_for_expr(then_expr, statement_context, result);
            record_ir_call_expression_evidence_for_expr(else_expr, statement_context, result);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            record_ir_call_expression_evidence_for_expr(base, statement_context, result);
            record_ir_call_expression_evidence_for_expr(index, statement_context, result);
        }
        typed_ir::IrExpr::Member { base, .. } => {
            record_ir_call_expression_evidence_for_expr(base, statement_context, result);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                record_ir_call_expression_evidence_for_expr(element, statement_context, result);
            }
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            record_ir_call_expression_evidence_for_expr(target, statement_context, result);
        }
        typed_ir::IrExpr::Deref { ptr, .. } => {
            record_ir_call_expression_evidence_for_expr(ptr, statement_context, result);
        }
        typed_ir::IrExpr::AddrOf { operand, .. } => {
            record_ir_call_expression_evidence_for_expr(operand, statement_context, result);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}
