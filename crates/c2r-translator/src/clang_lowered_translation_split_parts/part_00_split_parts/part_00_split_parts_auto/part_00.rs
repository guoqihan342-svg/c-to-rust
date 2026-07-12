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
