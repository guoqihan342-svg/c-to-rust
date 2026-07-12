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
        if parse_spec.compile_commands.is_some() {
            return clang_frontend::lower_function_from_clang_parse_spec_report(
                environment,
                parse_spec,
            );
        }
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
            record_layout_evidence: None,
        };
    }

    let mut temp_parse_spec = parse_spec.clone();
    temp_parse_spec.source_root = PathBuf::from(".");
    temp_parse_spec.source_file = temp_source.clone();
    temp_parse_spec.include_paths = parse_spec
        .resolved_include_paths()
        .iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect();
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
        "clang lowering used slice-spec c_source with preserved include and define arguments; compile_commands replay was not used"
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
