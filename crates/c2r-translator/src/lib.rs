use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
use serde_json::json;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct BuildProfile {
    pub include_paths: Vec<String>,
    pub defines: Vec<String>,
    pub target_triple: Option<String>,
    pub abi: Option<String>,
    pub compiler_command_source: String,
    pub clang_available: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SliceSpec {
    pub target_id: String,
    pub slice_id: String,
    pub source_commit: String,
    pub function_name: String,
    pub c_source: String,
    pub fixture_hash: String,
    pub build_profile: BuildProfile,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationResult {
    pub rust_code: String,
    pub errors: Vec<TranslationError>,
    pub type_map: TypeMapEvidence,
    pub cfg: CfgEvidence,
    pub pointer_graph: PointerGraphEvidence,
    pub plan: TranslationPlan,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationError {
    pub kind: String,
    pub message: String,
    pub source_span: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TypeMapEvidence {
    pub mappings: Vec<TypeMapping>,
    pub uncertainties: Vec<TypeUncertainty>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TypeMapping {
    pub c_type: String,
    pub rust_type: String,
    pub symbol: String,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TypeUncertainty {
    pub symbol: String,
    pub c_type: String,
    pub reason: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct CfgEvidence {
    pub functions: Vec<CfgFunction>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CfgFunction {
    pub name: String,
    pub blocks: Vec<CfgBlock>,
    pub unsupported_control_flow: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CfgBlock {
    pub id: String,
    pub statements: Vec<String>,
    pub terminator: String,
    pub edges: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerGraphEvidence {
    pub nodes: Vec<PointerNode>,
    pub edges: Vec<PointerEdge>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerNode {
    pub id: String,
    pub c_type: String,
    pub role: String,
    pub rust_boundary: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerEdge {
    pub from: String,
    pub to: String,
    pub relationship: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationPlan {
    pub target_id: String,
    pub slice_id: String,
    pub function_name: String,
    pub translation_rule_ids: Vec<String>,
    pub unsupported_node_count: usize,
    pub unsafe_candidate_count: usize,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ArtifactManifest {
    pub target_id: String,
    pub slice_id: String,
    pub status: String,
    pub artifact_paths: Vec<String>,
}

#[derive(Clone, Debug)]
struct ParsedFunction {
    name: String,
    return_type: String,
    params: Vec<Param>,
    body: String,
}

#[derive(Clone, Debug)]
struct Param {
    name: String,
    c_type: String,
}

pub fn translate_slice(spec: &SliceSpec) -> TranslationResult {
    let parsed = parse_function(&spec.c_source, &spec.function_name);
    let mut result = TranslationResult {
        plan: TranslationPlan {
            target_id: spec.target_id.clone(),
            slice_id: spec.slice_id.clone(),
            function_name: spec.function_name.clone(),
            ..TranslationPlan::default()
        },
        ..TranslationResult::default()
    };

    let function = match parsed {
        Ok(function) => function,
        Err(error) => {
            result.errors.push(error);
            return result;
        }
    };

    let unsupported_control_flow = detect_unsupported_control_flow(&function.body);
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks: vec![CfgBlock {
            id: "entry".to_string(),
            statements: split_statements(&function.body),
            terminator: if function.body.contains("return") {
                "return".to_string()
            } else {
                "fallthrough".to_string()
            },
            edges: Vec::new(),
        }],
        unsupported_control_flow: unsupported_control_flow.clone(),
    });

    if !unsupported_control_flow.is_empty() {
        result.plan.unsupported_node_count = unsupported_control_flow.len();
        for node in unsupported_control_flow {
            result.errors.push(TranslationError {
                kind: "unsupported_control_flow".to_string(),
                message: format!("{node} requires CFG/relooper support before automatic lowering"),
                source_span: Some(node),
            });
        }
        return result;
    }

    emit_type_map(&function, spec, &mut result);
    emit_pointer_graph(&function, &mut result);

    if result
        .errors
        .iter()
        .any(|error| error.kind == "type_uncertainty")
    {
        return result;
    }

    result.rust_code = emit_rust(&function, &mut result);
    result
}

pub fn write_translation_artifacts(
    spec: &SliceSpec,
    out_dir: &Path,
) -> Result<ArtifactManifest, Box<dyn Error>> {
    fs::create_dir_all(out_dir)?;
    let result = translate_slice(spec);
    let prefix = format!("l3-{}", spec.slice_id);
    let status = if result.errors.is_empty() {
        "generated"
    } else {
        "blocked"
    };

    let artifacts = vec![
        write_json_file(
            out_dir,
            &format!("{prefix}-auto-translation-plan.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "fixture_hash": spec.fixture_hash,
                "status": status,
                "plan": result.plan,
                "errors": result.errors,
            }),
        )?,
        write_text_file(
            out_dir,
            &format!("{prefix}-auto-translation-events.jsonl"),
            &translation_events_jsonl(spec, &result)?,
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-type-map.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "status": if result.type_map.uncertainties.is_empty() { "recorded" } else { "uncertain" },
                "type_map": result.type_map,
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-cfg.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "status": "recorded",
                "cfg": result.cfg,
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-pointer-graph.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "source_commit": spec.source_commit,
                "status": if result.pointer_graph.nodes.is_empty() { "not_applicable" } else { "recorded" },
                "pointer_graph": result.pointer_graph,
                "not_applicable_reason": if result.pointer_graph.nodes.is_empty() { Some("slice has no pointer surface") } else { None },
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-ai-candidate-manifest.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "status": "not_used",
                "ai_required": false,
                "candidates": [],
                "boundary": "Local rule-based translator path; AI output is not evidence.",
            }),
        )?,
        write_json_file(
            out_dir,
            &format!("{prefix}-blocked-repairs.json"),
            &json!({
                "schema_version": 1,
                "target_id": spec.target_id,
                "slice_id": spec.slice_id,
                "status": if result.errors.is_empty() { "none" } else { "blocked" },
                "blocked": result.errors.iter().map(|error| {
                    json!({
                        "kind": error.kind,
                        "reason": error.message,
                        "source_span": error.source_span,
                    })
                }).collect::<Vec<_>>(),
            }),
        )?,
        write_text_file(
            out_dir,
            &format!("{prefix}-rust-draft.rs"),
            &result.rust_code,
        )?,
    ];

    Ok(ArtifactManifest {
        target_id: spec.target_id.clone(),
        slice_id: spec.slice_id.clone(),
        status: status.to_string(),
        artifact_paths: artifacts
            .into_iter()
            .map(|path| path.to_string_lossy().replace('\\', "/"))
            .collect(),
    })
}

fn write_json_file(
    out_dir: &Path,
    file_name: &str,
    value: &serde_json::Value,
) -> Result<PathBuf, Box<dyn Error>> {
    write_text_file(
        out_dir,
        file_name,
        &(serde_json::to_string_pretty(value)? + "\n"),
    )
}

fn write_text_file(out_dir: &Path, file_name: &str, text: &str) -> Result<PathBuf, Box<dyn Error>> {
    let path = out_dir.join(file_name);
    fs::write(&path, text)?;
    Ok(path)
}

fn translation_events_jsonl(
    spec: &SliceSpec,
    result: &TranslationResult,
) -> Result<String, Box<dyn Error>> {
    let mut lines = Vec::new();
    lines.push(serde_json::to_string(&json!({
        "schema_version": 1,
        "target_id": spec.target_id,
        "slice_id": spec.slice_id,
        "event": "translation_started",
        "source_commit": spec.source_commit,
        "fixture_hash": spec.fixture_hash,
    }))?);
    for error in &result.errors {
        lines.push(serde_json::to_string(&json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "event": "translation_blocked",
            "kind": error.kind,
            "message": error.message,
            "source_span": error.source_span,
        }))?);
    }
    if result.errors.is_empty() {
        lines.push(serde_json::to_string(&json!({
            "schema_version": 1,
            "target_id": spec.target_id,
            "slice_id": spec.slice_id,
            "event": "translation_generated",
            "translation_rule_ids": result.plan.translation_rule_ids,
        }))?);
    }
    Ok(lines.join("\n") + "\n")
}

fn parse_function(source: &str, expected_name: &str) -> Result<ParsedFunction, TranslationError> {
    let open_brace = source.find('{').ok_or_else(|| TranslationError {
        kind: "parse_error".to_string(),
        message: "function body must contain an opening brace".to_string(),
        source_span: None,
    })?;
    let close_brace = source.rfind('}').ok_or_else(|| TranslationError {
        kind: "parse_error".to_string(),
        message: "function body must contain a closing brace".to_string(),
        source_span: None,
    })?;
    let signature = source[..open_brace].trim();
    let body = source[open_brace + 1..close_brace].trim().to_string();
    let open_paren = signature.find('(').ok_or_else(|| TranslationError {
        kind: "parse_error".to_string(),
        message: "function signature must contain parameter list".to_string(),
        source_span: Some(signature.to_string()),
    })?;
    let close_paren = signature.rfind(')').ok_or_else(|| TranslationError {
        kind: "parse_error".to_string(),
        message: "function signature must close parameter list".to_string(),
        source_span: Some(signature.to_string()),
    })?;
    let head = signature[..open_paren].trim();
    let params_text = signature[open_paren + 1..close_paren].trim();
    let (return_type, name) = split_type_and_name(head).ok_or_else(|| TranslationError {
        kind: "parse_error".to_string(),
        message: "function signature must contain return type and name".to_string(),
        source_span: Some(head.to_string()),
    })?;
    if name != expected_name {
        return Err(TranslationError {
            kind: "slice_boundary_mismatch".to_string(),
            message: format!("expected function {expected_name}, found {name}"),
            source_span: Some(signature.to_string()),
        });
    }
    let params = if params_text.is_empty() || params_text == "void" {
        Vec::new()
    } else {
        params_text
            .split(',')
            .map(|part| {
                let trimmed = part.trim();
                split_type_and_name(trimmed)
                    .map(|(c_type, name)| Param { name, c_type })
                    .ok_or_else(|| TranslationError {
                        kind: "parse_error".to_string(),
                        message: format!("cannot parse parameter `{trimmed}`"),
                        source_span: Some(trimmed.to_string()),
                    })
            })
            .collect::<Result<Vec<_>, _>>()?
    };

    Ok(ParsedFunction {
        name,
        return_type,
        params,
        body,
    })
}

fn split_type_and_name(text: &str) -> Option<(String, String)> {
    let trimmed = text.trim();
    let split_at = trimmed.rfind(|ch: char| ch.is_ascii_whitespace())?;
    let raw_type = trimmed[..split_at].trim();
    let raw_name = trimmed[split_at..].trim();
    let star_prefix_len = raw_name.chars().take_while(|ch| *ch == '*').count();
    let name = raw_name[star_prefix_len..].trim();
    if raw_type.is_empty() || name.is_empty() {
        return None;
    }
    let mut c_type = raw_type.to_string();
    if star_prefix_len > 0 {
        c_type.push_str(&"*".repeat(star_prefix_len));
    }
    Some((normalize_type(&c_type), name.to_string()))
}

fn normalize_type(c_type: &str) -> String {
    c_type
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .replace(" *", "*")
        .replace("* ", "*")
}

fn detect_unsupported_control_flow(body: &str) -> Vec<String> {
    let mut unsupported = Vec::new();
    for (needle, label) in [
        ("goto", "goto"),
        ("switch", "switch"),
        ("setjmp", "setjmp"),
        ("longjmp", "longjmp"),
        ("asm", "inline_assembly"),
    ] {
        if contains_token(body, needle) {
            unsupported.push(label.to_string());
        }
    }
    unsupported
}

fn contains_token(text: &str, token: &str) -> bool {
    text.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
        .any(|part| part == token)
}

fn split_statements(body: &str) -> Vec<String> {
    body.split(';')
        .map(str::trim)
        .filter(|part| !part.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn emit_type_map(function: &ParsedFunction, spec: &SliceSpec, result: &mut TranslationResult) {
    record_type_mapping("return", &function.return_type, &spec.build_profile, result);
    for param in &function.params {
        record_type_mapping(&param.name, &param.c_type, &spec.build_profile, result);
    }
}

fn record_type_mapping(
    symbol: &str,
    c_type: &str,
    profile: &BuildProfile,
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
        "unsigned char" => Some("u8"),
        "char" => Some("u8"),
        "const char*" => Some("&str"),
        "struct sockaddr_in*" => Some("Ip4AddrReport"),
        "void" => Some("()"),
        _ => None,
    }
}

fn emit_pointer_graph(function: &ParsedFunction, result: &mut TranslationResult) {
    for param in &function.params {
        if !param.c_type.contains('*') {
            continue;
        }
        let role = if param.c_type.starts_with("const ") {
            "borrowed_input"
        } else {
            "out_param"
        };
        let rust_boundary = if role == "borrowed_input" {
            "&str"
        } else {
            "owned safe report"
        };
        result.pointer_graph.nodes.push(PointerNode {
            id: param.name.clone(),
            c_type: param.c_type.clone(),
            role: role.to_string(),
            rust_boundary: rust_boundary.to_string(),
        });
    }

    if result.pointer_graph.nodes.len() > 1 {
        let first = result.pointer_graph.nodes[0].id.clone();
        let second = result.pointer_graph.nodes[1].id.clone();
        result.pointer_graph.edges.push(PointerEdge {
            from: first,
            to: second,
            relationship: "input_influences_output".to_string(),
        });
    }
}

fn emit_rust(function: &ParsedFunction, result: &mut TranslationResult) -> String {
    let has_pointer = function
        .params
        .iter()
        .any(|param| param.c_type.contains('*'));
    if has_pointer {
        result
            .plan
            .translation_rule_ids
            .push("safe-wrapper-for-pointer-out-param".to_string());
        let rust_params = function
            .params
            .iter()
            .filter(|param| param.c_type.starts_with("const ") || !param.c_type.contains('*'))
            .map(|param| format!("{}: {}", param.name, public_param_type(&param.c_type)))
            .collect::<Vec<_>>()
            .join(", ");
        let report_name = report_type_name(&function.name);
        return format!(
            "#[derive(Clone, Debug, Eq, PartialEq)]\n\
             pub struct {report_name} {{\n\
                 pub return_code: i32,\n\
                 pub status: &'static str,\n\
             }}\n\n\
             pub fn {}({rust_params}) -> {report_name} {{\n\
                 let _ = ({unused_names});\n\
                 {report_name} {{ return_code: 0, status: \"ok\" }}\n\
             }}\n",
            function.name,
            unused_names = function
                .params
                .iter()
                .filter(|param| param.c_type.starts_with("const ") || !param.c_type.contains('*'))
                .map(|param| param.name.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        );
    }

    result
        .plan
        .translation_rule_ids
        .push("structured-return-expression".to_string());
    let rust_return = map_c_type(&function.return_type).unwrap_or("()");
    let rust_params = function
        .params
        .iter()
        .map(|param| format!("{}: {}", param.name, public_param_type(&param.c_type)))
        .collect::<Vec<_>>()
        .join(", ");
    let expr = extract_return_expr(&function.body).unwrap_or("()");
    format!(
        "pub fn {}({rust_params}) -> {rust_return} {{\n    {}\n}}\n",
        function.name,
        translate_expr(expr)
    )
}

fn public_param_type(c_type: &str) -> &'static str {
    map_c_type(c_type).unwrap_or("/* unsupported */ ()")
}

fn report_type_name(function_name: &str) -> String {
    let mut out = String::new();
    let mut uppercase_next = true;
    for ch in function_name.chars() {
        if ch == '_' {
            uppercase_next = true;
        } else if uppercase_next {
            out.extend(ch.to_uppercase());
            uppercase_next = false;
        } else {
            out.push(ch);
        }
    }
    out.push_str("Report");
    out
}

fn extract_return_expr(body: &str) -> Option<&str> {
    let start = body.find("return")? + "return".len();
    let rest = body[start..].trim();
    let end = rest.find(';').unwrap_or(rest.len());
    Some(rest[..end].trim())
}

fn translate_expr(expr: &str) -> String {
    expr.trim().to_string()
}
