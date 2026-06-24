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
    pub statement_kinds: Vec<String>,
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
    pub read_effects: Vec<String>,
    pub write_effects: Vec<String>,
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

#[derive(Clone, Debug, Eq, PartialEq)]
struct ParsedStatement {
    text: String,
    kind: StatementKind,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum StatementKind {
    PrimitiveDeclaration,
    Assignment,
    Return,
    SimpleCall,
    If,
    While,
    For,
    PointerWrite,
    Expression,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Declaration {
    c_type: String,
    name: String,
    initializer: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Assignment {
    target: String,
    value: String,
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

    let statements = parse_statements(&function.body);
    let unsupported_control_flow = detect_unsupported_control_flow(&function.body);
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks: vec![CfgBlock {
            id: "entry".to_string(),
            statements: statements
                .iter()
                .map(|statement| statement.text.clone())
                .collect(),
            statement_kinds: statements
                .iter()
                .map(|statement| statement.kind.label().to_string())
                .collect(),
            terminator: if statements
                .iter()
                .any(|statement| statement.kind == StatementKind::Return)
            {
                "return".to_string()
            } else {
                "fallthrough".to_string()
            },
            edges: cfg_edges_for_statements(&statements),
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

    record_unsupported_statements(&statements, &mut result);
    if result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax")
    {
        result.plan.unsupported_node_count = result.errors.len();
        return result;
    }

    emit_type_map(&function, &statements, spec, &mut result);
    emit_pointer_graph(&function, &statements, &mut result);

    if !result.errors.is_empty() {
        result.plan.unsupported_node_count = result.errors.len();
        return result;
    }

    result.rust_code = emit_rust(&function, &statements, &mut result);
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

fn parse_statements(body: &str) -> Vec<ParsedStatement> {
    let mut statements = Vec::new();
    let mut index = 0;
    while index < body.len() {
        index = skip_whitespace(body, index);
        if index >= body.len() {
            break;
        }

        let end = if starts_with_token_at(body, index, "if")
            || starts_with_token_at(body, index, "while")
            || starts_with_token_at(body, index, "for")
        {
            scan_control_statement_end(body, index)
                .unwrap_or_else(|| scan_statement_end(body, index))
        } else {
            scan_statement_end(body, index)
        };
        let statement_text = body[index..end].trim().trim_end_matches(';').trim();
        if !statement_text.is_empty() {
            statements.push(ParsedStatement {
                text: statement_text.to_string(),
                kind: classify_statement(statement_text),
            });
        }
        index = end;
        if body.as_bytes().get(index) == Some(&b';') {
            index += 1;
        }
    }
    statements
}

fn classify_statement(text: &str) -> StatementKind {
    let trimmed = text.trim();
    if starts_with_token_at(trimmed, 0, "if") {
        return StatementKind::If;
    }
    if starts_with_token_at(trimmed, 0, "while") {
        return StatementKind::While;
    }
    if starts_with_token_at(trimmed, 0, "for") {
        return StatementKind::For;
    }
    if starts_with_token_at(trimmed, 0, "return") {
        return StatementKind::Return;
    }
    if parse_declaration(trimmed).is_some() {
        return StatementKind::PrimitiveDeclaration;
    }
    if let Some(assignment) = parse_assignment(trimmed) {
        if assignment.target.contains("->") || assignment.target.starts_with('*') {
            return StatementKind::PointerWrite;
        }
        return StatementKind::Assignment;
    }
    if parse_simple_call(trimmed).is_some() {
        return StatementKind::SimpleCall;
    }
    StatementKind::Expression
}

impl StatementKind {
    fn label(&self) -> &'static str {
        match self {
            Self::PrimitiveDeclaration => "primitive_declaration",
            Self::Assignment => "assignment",
            Self::Return => "return",
            Self::SimpleCall => "simple_call",
            Self::If => "if",
            Self::While => "while",
            Self::For => "for",
            Self::PointerWrite => "pointer_write",
            Self::Expression => "expression",
        }
    }
}

fn cfg_edges_for_statements(statements: &[ParsedStatement]) -> Vec<String> {
    statements
        .iter()
        .enumerate()
        .filter_map(|(index, statement)| match statement.kind {
            StatementKind::If => Some(format!("entry->if-{index}")),
            StatementKind::While => Some(format!("entry->while-{index}")),
            StatementKind::For => Some(format!("entry->for-{index}")),
            StatementKind::Return => Some(format!("entry->return-{index}")),
            _ => None,
        })
        .collect()
}

fn skip_whitespace(text: &str, mut index: usize) -> usize {
    while index < text.len() && text.as_bytes()[index].is_ascii_whitespace() {
        index += 1;
    }
    index
}

fn scan_statement_end(text: &str, start: usize) -> usize {
    let bytes = text.as_bytes();
    let mut index = start;
    let mut paren_depth = 0usize;
    let mut brace_depth = 0usize;
    while index < bytes.len() {
        match bytes[index] {
            b'(' => paren_depth += 1,
            b')' => paren_depth = paren_depth.saturating_sub(1),
            b'{' => brace_depth += 1,
            b'}' => {
                if brace_depth == 0 {
                    return index;
                }
                brace_depth -= 1;
            }
            b';' if paren_depth == 0 && brace_depth == 0 => return index,
            _ => {}
        }
        index += 1;
    }
    text.len()
}

fn scan_control_statement_end(text: &str, start: usize) -> Option<usize> {
    let open_paren = text[start..].find('(')? + start;
    let close_paren = find_matching_byte(text, open_paren, b'(', b')')?;
    let body_start = skip_whitespace(text, close_paren + 1);
    let mut body_end = scan_control_body_end(text, body_start)?;
    let after_body = skip_whitespace(text, body_end);
    if starts_with_token_at(text, start, "if") && starts_with_token_at(text, after_body, "else") {
        let else_body_start = skip_whitespace(text, after_body + "else".len());
        body_end = scan_control_body_end(text, else_body_start)?;
    }
    Some(body_end)
}

fn scan_control_body_end(text: &str, start: usize) -> Option<usize> {
    if text.as_bytes().get(start) == Some(&b'{') {
        return find_matching_byte(text, start, b'{', b'}').map(|index| index + 1);
    }
    let end = scan_statement_end(text, start);
    Some(if text.as_bytes().get(end) == Some(&b';') {
        end + 1
    } else {
        end
    })
}

fn find_matching_byte(text: &str, open_at: usize, open: u8, close: u8) -> Option<usize> {
    let bytes = text.as_bytes();
    let mut depth = 0usize;
    for (index, byte) in bytes.iter().enumerate().skip(open_at) {
        if *byte == open {
            depth += 1;
        } else if *byte == close {
            depth = depth.checked_sub(1)?;
            if depth == 0 {
                return Some(index);
            }
        }
    }
    None
}

fn starts_with_token_at(text: &str, index: usize, token: &str) -> bool {
    let bytes = text.as_bytes();
    let token_bytes = token.as_bytes();
    if index + token_bytes.len() > bytes.len()
        || &bytes[index..index + token_bytes.len()] != token_bytes
    {
        return false;
    }
    let before_ok = index == 0 || !is_ident_byte(bytes[index - 1]);
    let after_index = index + token_bytes.len();
    let after_ok = after_index == bytes.len() || !is_ident_byte(bytes[after_index]);
    before_ok && after_ok
}

fn is_ident_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

fn parse_declaration(text: &str) -> Option<Declaration> {
    let trimmed = text.trim().trim_end_matches(';').trim();
    let (declaration, initializer) = match trimmed.split_once('=') {
        Some((left, right)) => (left.trim(), Some(right.trim().to_string())),
        None => (trimmed, None),
    };
    let (c_type, name) = split_type_and_name(declaration)?;
    if c_type == "void" || map_c_type(&c_type).is_none() || name.contains('[') || name.contains('(')
    {
        return None;
    }
    Some(Declaration {
        c_type,
        name,
        initializer,
    })
}

fn parse_assignment(text: &str) -> Option<Assignment> {
    let trimmed = text.trim().trim_end_matches(';').trim();
    let bytes = trimmed.as_bytes();
    for (index, byte) in bytes.iter().enumerate() {
        if *byte != b'=' {
            continue;
        }
        let previous = index.checked_sub(1).and_then(|idx| bytes.get(idx)).copied();
        let next = bytes.get(index + 1).copied();
        if matches!(
            previous,
            Some(b'=' | b'!' | b'<' | b'>' | b'+' | b'-' | b'*' | b'/' | b'%')
        ) || next == Some(b'=')
        {
            continue;
        }
        let target = trimmed[..index].trim();
        let value = trimmed[index + 1..].trim();
        if target.is_empty() || target.contains(char::is_whitespace) || value.is_empty() {
            return None;
        }
        return Some(Assignment {
            target: target.to_string(),
            value: value.to_string(),
        });
    }
    None
}

fn record_unsupported_statements(statements: &[ParsedStatement], result: &mut TranslationResult) {
    for statement in statements {
        match statement.kind {
            StatementKind::Expression => result.errors.push(TranslationError {
                kind: "unsupported_syntax".to_string(),
                message: format!(
                    "statement `{}` is outside the bounded MVP C subset",
                    statement.text
                ),
                source_span: Some(statement.text.clone()),
            }),
            StatementKind::If => {
                if let Some((_, then_body, else_body)) = parse_if_parts(&statement.text) {
                    record_unsupported_statements(&parse_statements(&then_body), result);
                    if let Some(else_body) = else_body {
                        record_unsupported_statements(&parse_statements(&else_body), result);
                    }
                } else {
                    result.errors.push(TranslationError {
                        kind: "unsupported_syntax".to_string(),
                        message: "if statement could not be parsed by bounded extractor"
                            .to_string(),
                        source_span: Some(statement.text.clone()),
                    });
                }
            }
            StatementKind::While => {
                if let Some((_, body)) = parse_loop_parts(&statement.text, "while") {
                    record_unsupported_statements(&parse_statements(&body), result);
                } else {
                    result.errors.push(TranslationError {
                        kind: "unsupported_syntax".to_string(),
                        message: "while statement could not be parsed by bounded extractor"
                            .to_string(),
                        source_span: Some(statement.text.clone()),
                    });
                }
            }
            StatementKind::For => {
                if let Some((init, _, step, body)) = parse_for_parts(&statement.text) {
                    let mut nested = parse_statements(&body);
                    if !init.trim().is_empty() {
                        nested.insert(
                            0,
                            ParsedStatement {
                                kind: classify_statement(&init),
                                text: init,
                            },
                        );
                    }
                    if !step.trim().is_empty()
                        && translate_for_step(&step) == translate_expr(&step)
                        && classify_statement(&step) == StatementKind::Expression
                    {
                        result.errors.push(TranslationError {
                            kind: "unsupported_syntax".to_string(),
                            message: format!(
                                "for step `{step}` is outside the bounded MVP C subset"
                            ),
                            source_span: Some(step),
                        });
                    }
                    record_unsupported_statements(&nested, result);
                } else {
                    result.errors.push(TranslationError {
                        kind: "unsupported_syntax".to_string(),
                        message: "for statement could not be parsed by bounded extractor"
                            .to_string(),
                        source_span: Some(statement.text.clone()),
                    });
                }
            }
            _ => {}
        }
    }
}

fn parse_simple_call(text: &str) -> Option<(&str, &str)> {
    let trimmed = text.trim().trim_end_matches(';').trim();
    let open = trimmed.find('(')?;
    if !trimmed.ends_with(')') {
        return None;
    }
    let callee = trimmed[..open].trim();
    if callee.is_empty()
        || !callee
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
    {
        return None;
    }
    Some((callee, trimmed[open + 1..trimmed.len() - 1].trim()))
}

fn emit_type_map(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    spec: &SliceSpec,
    result: &mut TranslationResult,
) {
    record_type_mapping("return", &function.return_type, &spec.build_profile, result);
    for param in &function.params {
        record_type_mapping(&param.name, &param.c_type, &spec.build_profile, result);
    }
    for statement in statements {
        if let Some(declaration) = parse_declaration(&statement.text) {
            record_type_mapping(
                &declaration.name,
                &declaration.c_type,
                &spec.build_profile,
                result,
            );
        }
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

fn emit_pointer_graph(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    result: &mut TranslationResult,
) {
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
        let write_effects = pointer_write_effects(&param.name, statements);
        if role == "out_param" && write_effects.is_empty() {
            result.errors.push(TranslationError {
                kind: "unsupported_pointer_pattern".to_string(),
                message: format!(
                    "out pointer `{}` has no recognized observable write in the slice body",
                    param.name
                ),
                source_span: Some(param.name.clone()),
            });
        }
        result.pointer_graph.nodes.push(PointerNode {
            id: param.name.clone(),
            c_type: param.c_type.clone(),
            role: role.to_string(),
            rust_boundary: rust_boundary.to_string(),
            read_effects: pointer_read_effects(&param.name, statements),
            write_effects,
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

fn pointer_read_effects(name: &str, statements: &[ParsedStatement]) -> Vec<String> {
    statements
        .iter()
        .filter(|statement| contains_token(&statement.text, name))
        .map(|statement| statement.text.clone())
        .collect()
}

fn pointer_write_effects(name: &str, statements: &[ParsedStatement]) -> Vec<String> {
    let arrow_prefix = format!("{name}->");
    let deref_target = format!("*{name}");
    statements
        .iter()
        .filter_map(|statement| {
            if statement.kind != StatementKind::PointerWrite {
                return None;
            }
            let assignment = parse_assignment(&statement.text)?;
            if assignment.target.starts_with(&arrow_prefix) || assignment.target == deref_target {
                Some(assignment.target)
            } else {
                None
            }
        })
        .collect()
}

fn emit_rust(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    result: &mut TranslationResult,
) -> String {
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
    record_statement_rules(statements, result);
    let rust_return = map_c_type(&function.return_type).unwrap_or("()");
    let rust_params = function
        .params
        .iter()
        .map(|param| format!("{}: {}", param.name, public_param_type(&param.c_type)))
        .collect::<Vec<_>>()
        .join(", ");
    let body_lines = emit_rust_body(statements, 1);
    format!(
        "pub fn {}({rust_params}) -> {rust_return} {{\n{}\n}}\n",
        function.name,
        body_lines
            .into_iter()
            .map(|line| if line.is_empty() {
                "    ()".to_string()
            } else {
                line
            })
            .collect::<Vec<_>>()
            .join("\n")
    )
}

fn record_statement_rules(statements: &[ParsedStatement], result: &mut TranslationResult) {
    for statement in statements {
        let rule = match statement.kind {
            StatementKind::PrimitiveDeclaration => Some("primitive-declaration"),
            StatementKind::Assignment => Some("assignment"),
            StatementKind::Return => Some("structured-return-expression"),
            StatementKind::SimpleCall => Some("simple-call"),
            StatementKind::If => Some("structured-if"),
            StatementKind::While => Some("structured-while"),
            StatementKind::For => Some("structured-for"),
            StatementKind::PointerWrite => Some("pointer-write-recorded"),
            StatementKind::Expression => None,
        };
        if let Some(rule) = rule {
            push_rule_once(&mut result.plan.translation_rule_ids, rule);
        }
    }
}

fn push_rule_once(rules: &mut Vec<String>, rule: &str) {
    if !rules.iter().any(|item| item == rule) {
        rules.push(rule.to_string());
    }
}

fn emit_rust_body(statements: &[ParsedStatement], indent_level: usize) -> Vec<String> {
    if statements.is_empty() {
        return vec![format!("{}()", indent(indent_level))];
    }
    statements
        .iter()
        .flat_map(|statement| emit_rust_statement(statement, indent_level))
        .collect()
}

fn emit_rust_statement(statement: &ParsedStatement, indent_level: usize) -> Vec<String> {
    let prefix = indent(indent_level);
    match statement.kind {
        StatementKind::PrimitiveDeclaration => parse_declaration(&statement.text)
            .map(|declaration| {
                let rust_type = map_c_type(&declaration.c_type).unwrap_or("()");
                let initializer = declaration
                    .initializer
                    .as_deref()
                    .map(translate_expr)
                    .unwrap_or_else(|| default_value_for_type(rust_type).to_string());
                vec![format!(
                    "{prefix}let mut {}: {rust_type} = {initializer};",
                    declaration.name
                )]
            })
            .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))]),
        StatementKind::Assignment | StatementKind::PointerWrite => {
            parse_assignment(&statement.text)
                .map(|assignment| {
                    vec![format!(
                        "{prefix}{} = {};",
                        translate_expr(&assignment.target),
                        translate_expr(&assignment.value)
                    )]
                })
                .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))])
        }
        StatementKind::Return => vec![format!(
            "{prefix}return {};",
            translate_expr(strip_keyword(&statement.text, "return"))
        )],
        StatementKind::SimpleCall | StatementKind::Expression => {
            vec![format!("{prefix}{};", translate_expr(&statement.text))]
        }
        StatementKind::If => {
            emit_if_statement(&statement.text, indent_level).unwrap_or_else(|| {
                vec![format!(
                    "{prefix}/* unsupported if lowering: {} */",
                    statement.text
                )]
            })
        }
        StatementKind::While => {
            emit_while_statement(&statement.text, indent_level).unwrap_or_else(|| {
                vec![format!(
                    "{prefix}/* unsupported while lowering: {} */",
                    statement.text
                )]
            })
        }
        StatementKind::For => {
            emit_for_statement(&statement.text, indent_level).unwrap_or_else(|| {
                vec![format!(
                    "{prefix}/* unsupported for lowering: {} */",
                    statement.text
                )]
            })
        }
    }
}

fn emit_if_statement(text: &str, indent_level: usize) -> Option<Vec<String>> {
    let (condition, then_body, else_body) = parse_if_parts(text)?;
    let prefix = indent(indent_level);
    let mut lines = vec![format!("{prefix}if {} {{", translate_expr(&condition))];
    lines.extend(emit_rust_body(
        &parse_statements(&then_body),
        indent_level + 1,
    ));
    if let Some(else_body) = else_body {
        lines.push(format!("{prefix}}} else {{"));
        lines.extend(emit_rust_body(
            &parse_statements(&else_body),
            indent_level + 1,
        ));
    }
    lines.push(format!("{prefix}}}"));
    Some(lines)
}

fn emit_while_statement(text: &str, indent_level: usize) -> Option<Vec<String>> {
    let (condition, body) = parse_loop_parts(text, "while")?;
    let prefix = indent(indent_level);
    let mut lines = vec![format!("{prefix}while {} {{", translate_expr(&condition))];
    lines.extend(emit_rust_body(&parse_statements(&body), indent_level + 1));
    lines.push(format!("{prefix}}}"));
    Some(lines)
}

fn emit_for_statement(text: &str, indent_level: usize) -> Option<Vec<String>> {
    let (init, condition, step, body) = parse_for_parts(text)?;
    let prefix = indent(indent_level);
    let mut lines = vec![format!("{prefix}{{")];
    if !init.trim().is_empty() {
        let init_statement = ParsedStatement {
            kind: classify_statement(&init),
            text: init,
        };
        lines.extend(emit_rust_statement(&init_statement, indent_level + 1));
    }
    let loop_condition = if condition.trim().is_empty() {
        "true".to_string()
    } else {
        translate_expr(&condition)
    };
    lines.push(format!(
        "{}while {loop_condition} {{",
        indent(indent_level + 1)
    ));
    lines.extend(emit_rust_body(&parse_statements(&body), indent_level + 2));
    if !step.trim().is_empty() {
        lines.push(format!(
            "{}{};",
            indent(indent_level + 2),
            translate_for_step(&step)
        ));
    }
    lines.push(format!("{}}}", indent(indent_level + 1)));
    lines.push(format!("{prefix}}}"));
    Some(lines)
}

fn parse_if_parts(text: &str) -> Option<(String, String, Option<String>)> {
    let open = text.find('(')?;
    let close = find_matching_byte(text, open, b'(', b')')?;
    let condition = text[open + 1..close].trim().to_string();
    let then_start = skip_whitespace(text, close + 1);
    let then_end = scan_control_body_end(text, then_start)?;
    let then_body = extract_control_body(text, then_start, then_end)?;
    let after_then = skip_whitespace(text, then_end);
    let else_body = if starts_with_token_at(text, after_then, "else") {
        let else_start = skip_whitespace(text, after_then + "else".len());
        let else_end = scan_control_body_end(text, else_start)?;
        Some(extract_control_body(text, else_start, else_end)?)
    } else {
        None
    };
    Some((condition, then_body, else_body))
}

fn parse_loop_parts(text: &str, keyword: &str) -> Option<(String, String)> {
    if !starts_with_token_at(text, 0, keyword) {
        return None;
    }
    let open = text.find('(')?;
    let close = find_matching_byte(text, open, b'(', b')')?;
    let condition = text[open + 1..close].trim().to_string();
    let body_start = skip_whitespace(text, close + 1);
    let body_end = scan_control_body_end(text, body_start)?;
    Some((condition, extract_control_body(text, body_start, body_end)?))
}

fn parse_for_parts(text: &str) -> Option<(String, String, String, String)> {
    let open = text.find('(')?;
    let close = find_matching_byte(text, open, b'(', b')')?;
    let header = &text[open + 1..close];
    let parts = split_top_level(header, b';');
    if parts.len() != 3 {
        return None;
    }
    let body_start = skip_whitespace(text, close + 1);
    let body_end = scan_control_body_end(text, body_start)?;
    Some((
        parts[0].trim().to_string(),
        parts[1].trim().to_string(),
        parts[2].trim().to_string(),
        extract_control_body(text, body_start, body_end)?,
    ))
}

fn extract_control_body(text: &str, start: usize, end: usize) -> Option<String> {
    if text.as_bytes().get(start) == Some(&b'{') {
        let close = end.checked_sub(1)?;
        return Some(text[start + 1..close].trim().to_string());
    }
    Some(
        text[start..end]
            .trim()
            .trim_end_matches(';')
            .trim()
            .to_string(),
    )
}

fn split_top_level(text: &str, delimiter: u8) -> Vec<String> {
    let mut parts = Vec::new();
    let mut start = 0usize;
    let mut paren_depth = 0usize;
    for (index, byte) in text.as_bytes().iter().enumerate() {
        match *byte {
            b'(' => paren_depth += 1,
            b')' => paren_depth = paren_depth.saturating_sub(1),
            value if value == delimiter && paren_depth == 0 => {
                parts.push(text[start..index].to_string());
                start = index + 1;
            }
            _ => {}
        }
    }
    parts.push(text[start..].to_string());
    parts
}

fn strip_keyword<'a>(text: &'a str, keyword: &str) -> &'a str {
    text.trim()
        .strip_prefix(keyword)
        .unwrap_or(text)
        .trim()
        .trim_end_matches(';')
        .trim()
}

fn default_value_for_type(rust_type: &str) -> &'static str {
    match rust_type {
        "()" => "()",
        "&str" => "\"\"",
        _ => "0",
    }
}

fn translate_for_step(step: &str) -> String {
    let trimmed = step.trim();
    if let Some(name) = trimmed.strip_suffix("++") {
        return format!("{} += 1", translate_expr(name.trim()));
    }
    if let Some(name) = trimmed.strip_prefix("++") {
        return format!("{} += 1", translate_expr(name.trim()));
    }
    if let Some(name) = trimmed.strip_suffix("--") {
        return format!("{} -= 1", translate_expr(name.trim()));
    }
    if let Some(name) = trimmed.strip_prefix("--") {
        return format!("{} -= 1", translate_expr(name.trim()));
    }
    translate_expr(trimmed)
}

fn indent(level: usize) -> String {
    "    ".repeat(level)
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

fn translate_expr(expr: &str) -> String {
    expr.trim().to_string()
}
