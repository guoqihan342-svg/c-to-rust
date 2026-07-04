//! Legacy string translator for bounded compatibility candidates.
//!
//! This module is a compatibility-only candidate source. It recognizes a small
//! historical subset of C by string shape, then emits candidate Rust plus route
//! evidence for that subset. It is not a C semantic authority; new forward
//! translation should prefer clang lowering into typed IR and use this path only
//! where existing compatibility fixtures still depend on it.

use crate::{
    BuildProfile, CallExpressionEvidence, CfgBlock, CfgFunction, PointerEdge, PointerNode,
    SliceSpec, StructuredControlFlowEvidence, TranslationError, TranslationPlan, TranslationResult,
    TranslationSource, TypeMapping, TypeUncertainty,
};
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
    CompoundAssignment,
    IncDec,
    Return,
    SimpleCall,
    If,
    While,
    For,
    BoundedInputBufferRead,
    PointerWrite,
    UnsupportedLValue,
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

#[derive(Clone, Debug, Eq, PartialEq)]
struct CompoundAssignment {
    target: String,
    operator: String,
    value: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct IncDecStatement {
    target: String,
    delta_operator: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct UnsupportedControlFlow {
    kind: &'static str,
    detail: Option<String>,
}

impl UnsupportedControlFlow {
    fn label(&self) -> String {
        match &self.detail {
            Some(detail) => format!("{}:{detail}", self.kind),
            None => self.kind.to_string(),
        }
    }

    fn block_id(&self) -> String {
        match &self.detail {
            Some(detail) => format!("{}-{}", self.kind, sanitize_cfg_id(detail)),
            None => self.kind.to_string(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum LValue {
    SimpleIdentifier {
        name: String,
    },
    PointerField {
        base: String,
        field: String,
    },
    DerefIdentifier {
        base: String,
    },
    BoundedPointerIndex {
        base: String,
        index: String,
    },
    BoundedPointerArithmeticIndex {
        base: String,
        index: String,
        source: String,
    },
    Unsupported {
        reason: String,
    },
}

/// Runs the legacy string pipeline end to end for one slice.
///
/// The result is useful as a compatibility candidate only: parsing,
/// unsupported-node detection, evidence, and Rust emission all share the same
/// bounded string view of the C body. Any uncertainty is recorded on the result
/// and stops emission instead of being silently interpreted as real C semantics.
pub fn translate_slice(spec: &SliceSpec) -> TranslationResult {
    let parsed = parse_function(&spec.c_source, &spec.function_name);
    let mut result = TranslationResult {
        translation_source: TranslationSource::selected("legacy-string-translator"),
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
    let unsupported_control_flow_labels =
        unsupported_control_flow_labels(&unsupported_control_flow);
    let mut blocks = vec![CfgBlock {
        id: "entry".to_string(),
        statements: statements
            .iter()
            .map(|statement| statement.text.clone())
            .collect(),
        statement_kinds: statement_kind_labels(&statements),
        lvalue_kinds: statement_lvalue_kinds(&statements),
        terminator: if statements
            .iter()
            .any(|statement| statement.kind == StatementKind::Return)
        {
            "return".to_string()
        } else {
            "fallthrough".to_string()
        },
        edges: cfg_edges_for_statements(&statements, &unsupported_control_flow),
    }];
    blocks.extend(unsupported_control_flow_blocks(&unsupported_control_flow));
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks,
        unsupported_control_flow: unsupported_control_flow_labels.clone(),
        structured_control_flow: structured_control_flow_evidence(
            &statements,
            &unsupported_control_flow,
        ),
    });

    if !unsupported_control_flow.is_empty() {
        result.plan.unsupported_node_count = unsupported_control_flow_labels.len();
        for node in unsupported_control_flow_labels {
            result.errors.push(TranslationError {
                kind: "unsupported_control_flow".to_string(),
                message: format!("{node} requires CFG/relooper support before automatic lowering"),
                source_span: Some(node),
            });
        }
        return result;
    }

    record_unsupported_statements(&statements, &mut result);
    record_unbounded_buffer_reads(&statements, &mut result);
    record_unbounded_pointer_arithmetic_output_writes(&function, &statements, &mut result);
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
    record_call_expression_evidence(&statements, &mut result);

    if !result.errors.is_empty() {
        result.plan.unsupported_node_count = result.errors.len();
        return result;
    }

    result.rust_code = emit_rust(&function, &statements, &mut result);
    result
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

fn detect_unsupported_control_flow(body: &str) -> Vec<UnsupportedControlFlow> {
    let mut unsupported = Vec::new();
    for label in label_targets(body) {
        push_control_flow(&mut unsupported, "label", Some(label));
    }
    if contains_token(body, "goto") {
        push_control_flow(&mut unsupported, "goto", None);
        for target in goto_targets(body) {
            push_control_flow(&mut unsupported, "goto", Some(target));
        }
    }
    if contains_token(body, "switch") {
        push_control_flow(&mut unsupported, "switch", None);
        for case in case_targets(body) {
            push_control_flow(&mut unsupported, "case", Some(case));
        }
        if contains_token(body, "default") {
            push_control_flow(&mut unsupported, "default", None);
        }
    }
    for (needle, label) in [
        ("setjmp", "setjmp"),
        ("longjmp", "longjmp"),
        ("asm", "inline_assembly"),
    ] {
        if contains_token(body, needle) {
            push_control_flow(&mut unsupported, label, None);
        }
    }
    unsupported
}

fn push_control_flow(
    unsupported: &mut Vec<UnsupportedControlFlow>,
    kind: &'static str,
    detail: Option<String>,
) {
    let candidate = UnsupportedControlFlow { kind, detail };
    if !unsupported.iter().any(|item| item == &candidate) {
        unsupported.push(candidate);
    }
}

fn unsupported_control_flow_labels(items: &[UnsupportedControlFlow]) -> Vec<String> {
    let mut labels = items
        .iter()
        .map(UnsupportedControlFlow::label)
        .collect::<Vec<_>>();
    if items.iter().any(|item| item.kind == "goto") {
        push_unique(&mut labels, "relooper_refusal:goto");
    }
    if items.iter().any(|item| item.kind == "switch") {
        push_unique(&mut labels, "relooper_refusal:switch");
    }
    labels
}

fn structured_control_flow_evidence(
    statements: &[ParsedStatement],
    items: &[UnsupportedControlFlow],
) -> Option<StructuredControlFlowEvidence> {
    if items.is_empty() {
        return None;
    }
    let has_goto = items.iter().any(|item| item.kind == "goto");
    let has_switch = items.iter().any(|item| item.kind == "switch");
    let label_names = items
        .iter()
        .filter(|item| item.kind == "label")
        .filter_map(|item| item.detail.as_deref())
        .collect::<Vec<_>>();
    let mut preconditions = Vec::new();
    if has_goto
        && items
            .iter()
            .filter(|item| item.kind == "goto")
            .filter_map(|item| item.detail.as_deref())
            .all(|target| label_names.iter().any(|label| *label == target))
    {
        push_unique(&mut preconditions, "goto_target_resolved");
    }
    if has_switch
        && items
            .iter()
            .any(|item| matches!(item.kind, "case" | "default"))
    {
        push_unique(&mut preconditions, "switch_cases_enumerated");
    }

    let mut refusals = Vec::new();
    if has_goto {
        push_unique(&mut refusals, "goto_requires_structured_recovery");
    }
    if has_switch {
        push_unique(&mut refusals, "switch_requires_structured_recovery");
    }

    Some(StructuredControlFlowEvidence {
        if_count: statements
            .iter()
            .filter(|statement| statement.kind == StatementKind::If)
            .count(),
        loop_count: statements
            .iter()
            .filter(|statement| {
                matches!(statement.kind, StatementKind::While | StatementKind::For)
            })
            .count(),
        has_goto,
        has_switch,
        relooper_required: has_goto || has_switch,
        recovery_status: "refused".to_string(),
        relooper_preconditions: preconditions,
        relooper_refusals: refusals,
        scope_note: "minimal structured-recovery evidence only; no Rust candidate lowering or C/Rust semantic pass is claimed".to_string(),
    })
}

fn label_targets(body: &str) -> Vec<String> {
    let mut labels = Vec::new();
    for segment in body.split(';') {
        let trimmed = segment.trim();
        let Some(colon_index) = trimmed.find(':') else {
            continue;
        };
        let before_colon = trimmed[..colon_index].trim();
        if before_colon.starts_with("case ")
            || before_colon == "default"
            || before_colon.contains('?')
            || before_colon.contains(' ')
        {
            continue;
        }
        if is_identifier(before_colon) {
            push_unique(&mut labels, before_colon);
        }
    }
    labels
}

fn goto_targets(body: &str) -> Vec<String> {
    let mut targets = Vec::new();
    for segment in body.split(';') {
        let Some(index) = find_token(segment, "goto") else {
            continue;
        };
        let after_goto = segment[index + "goto".len()..].trim();
        let target = after_goto
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .next()
            .unwrap_or("")
            .trim();
        if is_identifier(target) {
            push_unique(&mut targets, target);
        }
    }
    targets
}

fn case_targets(body: &str) -> Vec<String> {
    let mut cases = Vec::new();
    let mut rest = body;
    while let Some(index) = find_token(rest, "case") {
        let after_case = &rest[index + "case".len()..];
        if let Some(colon_index) = after_case.find(':') {
            let value = after_case[..colon_index].trim();
            if !value.is_empty() {
                push_unique(&mut cases, &sanitize_case_label(value));
            }
            rest = &after_case[colon_index + 1..];
        } else {
            break;
        }
    }
    cases
}

fn find_token(text: &str, token: &str) -> Option<usize> {
    let mut offset = 0usize;
    while let Some(index) = text[offset..].find(token) {
        let absolute = offset + index;
        let before = text[..absolute].chars().next_back();
        let after = text[absolute + token.len()..].chars().next();
        let before_boundary = before
            .map(|ch| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .unwrap_or(true);
        let after_boundary = after
            .map(|ch| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .unwrap_or(true);
        if before_boundary && after_boundary {
            return Some(absolute);
        }
        offset = absolute + token.len();
    }
    None
}

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == '_')
        && chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
}

fn sanitize_case_label(value: &str) -> String {
    value
        .trim()
        .trim_matches(|ch: char| ch == '(' || ch == ')')
        .to_string()
}

fn contains_token(text: &str, token: &str) -> bool {
    text.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
        .any(|part| part == token)
}

/// Splits a function body into the statement shapes understood by this module.
///
/// This is deliberately a shallow scanner, not a C parser. It preserves whole
/// control-flow statements so later compatibility checks can recursively inspect
/// their bodies without pretending to model arbitrary syntax.
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
        return classify_lvalue_statement(&assignment.target, StatementKind::Assignment);
    }
    if let Some(assignment) = parse_compound_assignment(trimmed) {
        return classify_lvalue_statement(&assignment.target, StatementKind::CompoundAssignment);
    }
    if parse_inc_dec_statement(trimmed).is_some() {
        return StatementKind::IncDec;
    }
    if parse_simple_call(trimmed).is_some() {
        return StatementKind::SimpleCall;
    }
    StatementKind::Expression
}

fn classify_lvalue_statement(target: &str, simple_kind: StatementKind) -> StatementKind {
    match parse_lvalue(target) {
        LValue::SimpleIdentifier { .. } => simple_kind,
        LValue::BoundedPointerArithmeticIndex { .. } => {
            if simple_kind == StatementKind::Assignment {
                StatementKind::PointerWrite
            } else {
                StatementKind::UnsupportedLValue
            }
        }
        LValue::PointerField { .. }
        | LValue::DerefIdentifier { .. }
        | LValue::BoundedPointerIndex { .. } => StatementKind::PointerWrite,
        LValue::Unsupported { .. } => StatementKind::UnsupportedLValue,
    }
}

fn statement_kind_labels(statements: &[ParsedStatement]) -> Vec<String> {
    let mut labels = Vec::new();
    for statement in statements {
        push_unique(&mut labels, statement.kind.label());
        if statement_has_bounded_call_expression(statement) {
            push_unique(&mut labels, "call_expression");
        }
        if statement_has_bounded_input_buffer_read(statement) {
            push_unique(&mut labels, StatementKind::BoundedInputBufferRead.label());
        }
        if statement_has_bounded_pointer_arithmetic_input_read(statement) {
            push_unique(&mut labels, "bounded_pointer_arithmetic_input_read");
        }
        if statement_has_bounded_pointer_arithmetic_output_write(statement) {
            push_unique(&mut labels, "bounded_pointer_arithmetic_output_write");
        }
    }
    labels
}

fn statement_lvalue_kinds(statements: &[ParsedStatement]) -> Vec<String> {
    let mut kinds = Vec::new();
    for statement in statements {
        push_unique(&mut kinds, statement_lvalue_kind(statement));
        if statement_has_bounded_input_buffer_read(statement) {
            push_unique(&mut kinds, "bounded_input_buffer");
        }
        if statement_has_bounded_pointer_arithmetic_input_read(statement) {
            push_unique(&mut kinds, "bounded_pointer_arithmetic_input_buffer");
        }
        if statement_has_bounded_pointer_arithmetic_output_write(statement) {
            push_unique(&mut kinds, "bounded_pointer_arithmetic_output_buffer");
        }
    }
    kinds
}

fn push_unique(values: &mut Vec<String>, value: &str) {
    if !values.iter().any(|item| item == value) {
        values.push(value.to_string());
    }
}

impl StatementKind {
    fn label(&self) -> &'static str {
        match self {
            Self::PrimitiveDeclaration => "primitive_declaration",
            Self::Assignment => "assignment",
            Self::CompoundAssignment => "compound_assignment",
            Self::IncDec => "inc_dec",
            Self::Return => "return",
            Self::SimpleCall => "simple_call",
            Self::If => "if",
            Self::While => "while",
            Self::For => "for",
            Self::BoundedInputBufferRead => "bounded_input_buffer_read",
            Self::PointerWrite => "pointer_write",
            Self::UnsupportedLValue => "unsupported_lvalue",
            Self::Expression => "expression",
        }
    }
}

fn cfg_edges_for_statements(
    statements: &[ParsedStatement],
    unsupported_control_flow: &[UnsupportedControlFlow],
) -> Vec<String> {
    let mut edges = statements
        .iter()
        .enumerate()
        .filter_map(|(index, statement)| match statement.kind {
            StatementKind::If => Some(format!("entry->if-{index}")),
            StatementKind::While => Some(format!("entry->while-{index}")),
            StatementKind::For => Some(format!("entry->for-{index}")),
            StatementKind::Return => Some(format!("entry->return-{index}")),
            _ => None,
        })
        .collect::<Vec<_>>();
    for item in unsupported_control_flow {
        match item.kind {
            "label" => push_unique(&mut edges, &format!("entry->{}", item.block_id())),
            "goto" if item.detail.is_some() => {
                push_unique(&mut edges, &format!("entry->{}", item.block_id()));
            }
            "switch" => push_unique(&mut edges, "entry->switch-0"),
            _ => {}
        }
    }
    edges
}

fn unsupported_control_flow_blocks(items: &[UnsupportedControlFlow]) -> Vec<CfgBlock> {
    let mut blocks = Vec::new();
    let labels = items
        .iter()
        .filter(|item| item.kind == "label")
        .collect::<Vec<_>>();
    let cases = items
        .iter()
        .filter(|item| item.kind == "case")
        .collect::<Vec<_>>();
    let has_default = items.iter().any(|item| item.kind == "default");

    for item in items {
        match item.kind {
            "label" => blocks.push(CfgBlock {
                id: item.block_id(),
                statements: vec![item.label()],
                statement_kinds: vec!["label".to_string()],
                lvalue_kinds: Vec::new(),
                terminator: "unsupported_label".to_string(),
                edges: Vec::new(),
            }),
            "goto" if item.detail.is_some() => {
                let mut edges = Vec::new();
                if let Some(target) = &item.detail {
                    if labels
                        .iter()
                        .any(|label| label.detail.as_ref() == Some(target))
                    {
                        push_unique(
                            &mut edges,
                            &format!("{}->label-{}", item.block_id(), sanitize_cfg_id(target)),
                        );
                    }
                }
                blocks.push(CfgBlock {
                    id: item.block_id(),
                    statements: vec![item.label()],
                    statement_kinds: vec!["goto".to_string()],
                    lvalue_kinds: Vec::new(),
                    terminator: "unsupported_goto".to_string(),
                    edges,
                });
            }
            "switch" => {
                let mut edges = Vec::new();
                for case in &cases {
                    push_unique(&mut edges, &format!("switch-0->{}", case.block_id()));
                }
                if has_default {
                    push_unique(&mut edges, "switch-0->default");
                }
                blocks.push(CfgBlock {
                    id: "switch-0".to_string(),
                    statements: vec!["switch".to_string()],
                    statement_kinds: vec!["switch".to_string()],
                    lvalue_kinds: Vec::new(),
                    terminator: "unsupported_switch".to_string(),
                    edges,
                });
            }
            "case" | "default" => blocks.push(CfgBlock {
                id: item.block_id(),
                statements: vec![item.label()],
                statement_kinds: vec![item.kind.to_string()],
                lvalue_kinds: Vec::new(),
                terminator: format!("unsupported_{}", item.kind),
                edges: Vec::new(),
            }),
            _ => {}
        }
    }
    blocks
}

fn sanitize_cfg_id(value: &str) -> String {
    let sanitized = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '_' {
                ch
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .replace('_', "-");
    if sanitized.is_empty() {
        "unknown".to_string()
    } else {
        sanitized
    }
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

fn is_simple_identifier(text: &str) -> bool {
    let trimmed = text.trim();
    let mut bytes = trimmed.bytes();
    let Some(first) = bytes.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == b'_') && bytes.all(is_ident_byte)
}

fn parse_lvalue(target: &str) -> LValue {
    let trimmed = target.trim();
    if is_simple_identifier(trimmed) {
        return LValue::SimpleIdentifier {
            name: trimmed.to_string(),
        };
    }
    if let Some((base, field)) = trimmed.split_once("->") {
        let base = base.trim();
        let field = field.trim();
        if is_simple_identifier(base) && is_simple_identifier(field) {
            return LValue::PointerField {
                base: base.to_string(),
                field: field.to_string(),
            };
        }
        return LValue::Unsupported {
            reason: "unsupported pointer field lvalue".to_string(),
        };
    }
    if let Some(rest) = trimmed.strip_prefix('*') {
        if let Some((base, index, source)) = parse_pointer_arithmetic_deref_lvalue(trimmed) {
            return LValue::BoundedPointerArithmeticIndex {
                base,
                index,
                source,
            };
        }
        let base = rest.trim();
        if is_simple_identifier(base) {
            return LValue::DerefIdentifier {
                base: base.to_string(),
            };
        }
        return LValue::Unsupported {
            reason: "pointer arithmetic or complex dereference is outside the bounded subset"
                .to_string(),
        };
    }
    if let Some(open) = trimmed.find('[') {
        if trimmed.ends_with(']') {
            let base = trimmed[..open].trim();
            let index = trimmed[open + 1..trimmed.len() - 1].trim();
            if is_simple_identifier(base) && index == "0" {
                return LValue::BoundedPointerIndex {
                    base: base.to_string(),
                    index: index.to_string(),
                };
            }
            return LValue::Unsupported {
                reason: "pointer index boundary is unproven".to_string(),
            };
        }
    }
    LValue::Unsupported {
        reason: "complex lvalue is outside the bounded subset".to_string(),
    }
}

fn parse_pointer_arithmetic_deref_lvalue(target: &str) -> Option<(String, String, String)> {
    let trimmed = target.trim();
    let rest = trimmed.strip_prefix('*')?.trim();
    if !rest.starts_with('(') {
        return None;
    }
    let close = find_matching_byte(rest, 0, b'(', b')')?;
    if !rest[close + 1..].trim().is_empty() {
        return None;
    }
    let inner = rest[1..close].trim();
    let parts = split_top_level(inner, b'+');
    if parts.len() != 2 {
        return None;
    }
    let base = parts[0].trim();
    let index = parts[1].trim();
    if !is_simple_identifier(base) || !is_simple_identifier(index) {
        return None;
    }
    Some((base.to_string(), index.to_string(), trimmed.to_string()))
}

fn lvalue_kind(lvalue: &LValue) -> &'static str {
    match lvalue {
        LValue::SimpleIdentifier { .. } => "simple_identifier",
        LValue::PointerField { .. } => "pointer_field",
        LValue::DerefIdentifier { .. } => "deref_identifier",
        LValue::BoundedPointerIndex { .. } => "bounded_pointer_index",
        LValue::BoundedPointerArithmeticIndex { .. } => "bounded_pointer_arithmetic_output_buffer",
        LValue::Unsupported { .. } => "unsupported_lvalue",
    }
}

fn lvalue_write_effects(lvalue: &LValue) -> Vec<String> {
    match lvalue {
        LValue::PointerField { base, field } => vec![format!("{base}->{field}")],
        LValue::DerefIdentifier { base } => vec![format!("*{base}")],
        LValue::BoundedPointerIndex { base, index } => vec![format!("{base}[{index}]")],
        LValue::BoundedPointerArithmeticIndex {
            base,
            index,
            source,
        } => vec![format!("{base}[{index}]"), source.clone()],
        _ => Vec::new(),
    }
}

fn lvalue_base(lvalue: &LValue) -> Option<&str> {
    match lvalue {
        LValue::PointerField { base, .. }
        | LValue::DerefIdentifier { base }
        | LValue::BoundedPointerIndex { base, .. }
        | LValue::BoundedPointerArithmeticIndex { base, .. } => Some(base),
        _ => None,
    }
}

fn statement_lvalue(statement: &ParsedStatement) -> Option<LValue> {
    parse_assignment(&statement.text)
        .map(|assignment| parse_lvalue(&assignment.target))
        .or_else(|| {
            parse_compound_assignment(&statement.text)
                .map(|assignment| parse_lvalue(&assignment.target))
        })
        .or_else(|| {
            parse_inc_dec_statement(&statement.text).map(|inc_dec| parse_lvalue(&inc_dec.target))
        })
}

fn statement_lvalue_kind(statement: &ParsedStatement) -> &'static str {
    statement_lvalue(statement)
        .as_ref()
        .map(lvalue_kind)
        .unwrap_or("none")
}

fn statement_has_bounded_input_buffer_read(statement: &ParsedStatement) -> bool {
    if statement.kind != StatementKind::For {
        return false;
    }
    let Some((_, condition, _, body)) = parse_for_parts(&statement.text) else {
        return false;
    };
    let nested = parse_statements(&body);
    nested
        .iter()
        .flat_map(bounded_input_buffer_reads_for_statement)
        .any(|read| loop_condition_bounds_index(&condition, &read.index, "len"))
}

fn statement_has_bounded_pointer_arithmetic_input_read(statement: &ParsedStatement) -> bool {
    if statement.kind != StatementKind::For {
        return false;
    }
    let Some((_, condition, _, body)) = parse_for_parts(&statement.text) else {
        return false;
    };
    let nested = parse_statements(&body);
    nested
        .iter()
        .flat_map(bounded_input_buffer_reads_for_statement)
        .any(|read| {
            read.pointer_arithmetic && loop_condition_bounds_index(&condition, &read.index, "len")
        })
}

fn statement_has_bounded_pointer_arithmetic_output_write(statement: &ParsedStatement) -> bool {
    if statement.kind != StatementKind::For {
        return false;
    }
    let Some((_, condition, _, body)) = parse_for_parts(&statement.text) else {
        return false;
    };
    let nested = parse_statements(&body);
    nested
        .iter()
        .flat_map(pointer_arithmetic_output_writes_for_statement)
        .any(|write| loop_condition_bounds_index(&condition, &write.index, "len"))
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
        if target.is_empty()
            || value.is_empty()
            || (target.contains(char::is_whitespace) && !target.trim().starts_with('*'))
        {
            return None;
        }
        return Some(Assignment {
            target: target.to_string(),
            value: value.to_string(),
        });
    }
    None
}

fn parse_compound_assignment(text: &str) -> Option<CompoundAssignment> {
    let trimmed = text.trim().trim_end_matches(';').trim();
    for operator in ["<<=", ">>=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^="] {
        let Some(index) = find_operator_outside_parens(trimmed, operator) else {
            continue;
        };
        let target = trimmed[..index].trim();
        let value = trimmed[index + operator.len()..].trim();
        if target.is_empty() || value.is_empty() {
            return None;
        }
        return Some(CompoundAssignment {
            target: target.to_string(),
            operator: operator.to_string(),
            value: value.to_string(),
        });
    }
    None
}

fn parse_inc_dec_statement(text: &str) -> Option<IncDecStatement> {
    let trimmed = text.trim().trim_end_matches(';').trim();
    for (prefix, suffix, delta_operator) in [
        ("++", "", "+="),
        ("--", "", "-="),
        ("", "++", "+="),
        ("", "--", "-="),
    ] {
        let target = if let Some(target) =
            trimmed.strip_prefix(prefix).filter(|_| !prefix.is_empty())
        {
            target.trim()
        } else if let Some(target) = trimmed.strip_suffix(suffix).filter(|_| !suffix.is_empty()) {
            target.trim()
        } else {
            continue;
        };
        if is_simple_assignment_target(target) {
            return Some(IncDecStatement {
                target: target.to_string(),
                delta_operator,
            });
        }
    }
    None
}

fn find_operator_outside_parens(text: &str, operator: &str) -> Option<usize> {
    let bytes = text.as_bytes();
    let operator_bytes = operator.as_bytes();
    let mut index = 0usize;
    let mut paren_depth = 0usize;
    while index + operator_bytes.len() <= bytes.len() {
        match bytes[index] {
            b'(' => paren_depth += 1,
            b')' => paren_depth = paren_depth.saturating_sub(1),
            _ => {}
        }
        if paren_depth == 0 && &bytes[index..index + operator_bytes.len()] == operator_bytes {
            return Some(index);
        }
        index += 1;
    }
    None
}

fn is_simple_assignment_target(target: &str) -> bool {
    is_simple_identifier(target)
}

fn contains_inc_dec_operator(text: &str) -> bool {
    text.contains("++") || text.contains("--")
}

/// Detects standalone integer literals with a leading zero (C octal syntax).
///
/// Rust parses `010` as decimal ten while C parses it as octal eight, so
/// passing such literals through unchanged would be a silent semantic
/// mistranslation; the legacy path must refuse them instead. Hex literals
/// (`0x..`) do not trigger because the character after `0` is not a digit.
fn contains_leading_zero_integer_literal(text: &str) -> bool {
    let bytes = text.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        let byte = bytes[index];
        if byte.is_ascii_alphanumeric() || byte == b'_' {
            let token_starts_with_zero = byte == b'0';
            let next_is_digit = matches!(bytes.get(index + 1), Some(b'0'..=b'9'));
            if token_starts_with_zero && next_is_digit {
                return true;
            }
            index += 1;
            while index < bytes.len()
                && (bytes[index].is_ascii_alphanumeric()
                    || bytes[index] == b'_'
                    || bytes[index] == b'.')
            {
                index += 1;
            }
            continue;
        }
        index += 1;
    }
    false
}

fn push_unsupported_expression_value(
    statement: &ParsedStatement,
    expression: &str,
    result: &mut TranslationResult,
) {
    if let Err(reason) = parse_bounded_direct_call_expression(expression, "expression") {
        result.errors.push(TranslationError {
            kind: "unsupported_syntax".to_string(),
            message: format!(
                "call expression `{expression}` is outside the bounded MVP C subset: {reason}"
            ),
            source_span: Some(statement.text.clone()),
        });
    }
    if contains_inc_dec_operator(expression) {
        result.errors.push(TranslationError {
            kind: "unsupported_syntax".to_string(),
            message: format!(
                "expression `{expression}` uses increment/decrement value semantics outside the bounded MVP C subset"
            ),
            source_span: Some(statement.text.clone()),
        });
    }
    if contains_leading_zero_integer_literal(expression) {
        result.errors.push(TranslationError {
            kind: "unsupported_syntax".to_string(),
            message: format!(
                "expression `{expression}` contains a leading-zero integer literal; C octal syntax would be silently reinterpreted as decimal by Rust and is outside the bounded MVP C subset"
            ),
            source_span: Some(statement.text.clone()),
        });
    }
}

/// Converts unknown or unsafe string shapes into explicit translation errors.
///
/// The legacy path fails closed by attaching a concrete unsupported reason to
/// the result before Rust emission is attempted; nested bodies are re-scanned so
/// unsupported constructs cannot hide inside accepted outer control flow.
fn record_unsupported_statements(statements: &[ParsedStatement], result: &mut TranslationResult) {
    for statement in statements {
        match statement.kind {
            StatementKind::PrimitiveDeclaration => {
                if let Some(declaration) = parse_declaration(&statement.text) {
                    if let Some(initializer) = declaration.initializer.as_deref() {
                        push_unsupported_expression_value(statement, initializer, result);
                    }
                }
            }
            StatementKind::Assignment | StatementKind::PointerWrite => {
                if let Some(assignment) = parse_assignment(&statement.text) {
                    push_unsupported_expression_value(statement, &assignment.value, result);
                }
            }
            StatementKind::CompoundAssignment => {
                if let Some(assignment) = parse_compound_assignment(&statement.text) {
                    push_unsupported_expression_value(statement, &assignment.value, result);
                }
            }
            StatementKind::Return => {
                push_unsupported_expression_value(
                    statement,
                    strip_keyword(&statement.text, "return"),
                    result,
                );
            }
            StatementKind::UnsupportedLValue => {
                let reason = statement_lvalue(statement)
                    .and_then(|lvalue| match lvalue {
                        LValue::Unsupported { reason } => Some(reason),
                        _ => None,
                    })
                    .unwrap_or_else(|| "complex lvalue is outside the bounded subset".to_string());
                result.errors.push(TranslationError {
                    kind: "unsupported_lvalue".to_string(),
                    message: format!(
                        "statement `{}` uses unsupported lvalue: {reason}",
                        statement.text
                    ),
                    source_span: Some(statement.text.clone()),
                });
            }
            StatementKind::Expression => result.errors.push(TranslationError {
                kind: "unsupported_syntax".to_string(),
                message: format!(
                    "statement `{}` is outside the bounded MVP C subset",
                    statement.text
                ),
                source_span: Some(statement.text.clone()),
            }),
            StatementKind::SimpleCall => {
                if let Some((callee, _)) = parse_simple_call(&statement.text) {
                    if reserved_c_macro_or_stdlib_callee(callee) {
                        result.errors.push(TranslationError {
                            kind: "unsupported_syntax".to_string(),
                            message: format!(
                                "simple call `{}` targets reserved C macro/stdlib/extern surface `{callee}` and requires the typed-IR pipeline with explicit lowering/modeling or extern binding",
                                statement.text
                            ),
                            source_span: Some(statement.text.clone()),
                        });
                    }
                }
            }
            StatementKind::If => {
                if let Some((condition, then_body, else_body)) = parse_if_parts(&statement.text) {
                    push_unsupported_expression_value(statement, &condition, result);
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
                if let Some((condition, body)) = parse_loop_parts(&statement.text, "while") {
                    push_unsupported_expression_value(statement, &condition, result);
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
                if let Some((init, condition, step, body)) = parse_for_parts(&statement.text) {
                    push_unsupported_expression_value(statement, &condition, result);
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
                    if !step.trim().is_empty() {
                        let step_statement = ParsedStatement {
                            kind: classify_statement(&step),
                            text: step.clone(),
                        };
                        if translate_for_step(&step) == translate_expr(&step)
                            && step_statement.kind == StatementKind::Expression
                        {
                            result.errors.push(TranslationError {
                                kind: "unsupported_syntax".to_string(),
                                message: format!(
                                    "for step `{step}` is outside the bounded MVP C subset"
                                ),
                                source_span: Some(step),
                            });
                        }
                        record_unsupported_statements(&[step_statement], result);
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

fn reserved_c_macro_or_stdlib_callee(callee: &str) -> bool {
    matches!(
        callee,
        "assert"
            | "static_assert"
            | "_Static_assert"
            | "sizeof"
            | "offsetof"
            | "malloc"
            | "calloc"
            | "realloc"
            | "free"
            | "memcpy"
            | "memmove"
            | "memset"
            | "memcmp"
            | "strlen"
            | "printf"
            | "fprintf"
            | "sprintf"
            | "snprintf"
            | "puts"
            | "putchar"
            | "getchar"
            | "exit"
            | "abort"
    )
}

fn record_unbounded_buffer_reads(statements: &[ParsedStatement], result: &mut TranslationResult) {
    record_unbounded_buffer_reads_with_bounds(statements, &[], result);
}

fn record_unbounded_buffer_reads_with_bounds(
    statements: &[ParsedStatement],
    bounds: &[(&str, &str)],
    result: &mut TranslationResult,
) {
    for statement in statements {
        if statement.kind == StatementKind::For {
            if let Some((_, condition, _, body)) = parse_for_parts(&statement.text) {
                let nested = parse_statements(&body);
                let nested_reads = nested
                    .iter()
                    .flat_map(bounded_input_buffer_reads_for_statement)
                    .collect::<Vec<_>>();
                let mut nested_bounds = bounds.to_vec();
                for read in &nested_reads {
                    if loop_condition_bounds_index(&condition, &read.index, "len") {
                        nested_bounds.push((read.base.as_str(), read.index.as_str()));
                    }
                }
                record_unbounded_buffer_reads_with_bounds(&nested, &nested_bounds, result);
            }
            continue;
        }
        for read in bounded_input_buffer_reads_for_statement(statement) {
            let allowed = bounds
                .iter()
                .any(|(base, index)| *base == read.base && *index == read.index);
            if !allowed {
                result.errors.push(TranslationError {
                    kind: "unsupported_syntax".to_string(),
                    message: format!(
                        "input buffer read `{}` is not proven by a bounded length companion",
                        read.source
                    ),
                    source_span: Some(statement.text.clone()),
                });
            }
        }
    }
}

fn record_unbounded_pointer_arithmetic_output_writes(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    result: &mut TranslationResult,
) {
    record_unbounded_pointer_arithmetic_output_writes_with_bounds(
        function,
        statements,
        &[],
        result,
    );
}

fn record_unbounded_pointer_arithmetic_output_writes_with_bounds(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    bounds: &[(&str, &str)],
    result: &mut TranslationResult,
) {
    for statement in statements {
        if statement.kind == StatementKind::For {
            if let Some((_, condition, _, body)) = parse_for_parts(&statement.text) {
                let nested = parse_statements(&body);
                let nested_writes = nested
                    .iter()
                    .flat_map(pointer_arithmetic_output_writes_for_statement)
                    .collect::<Vec<_>>();
                let mut nested_bounds = bounds.to_vec();
                for write in &nested_writes {
                    if loop_condition_bounds_index(&condition, &write.index, "len")
                        && mutable_i32_pointer_param(function, &write.base)
                    {
                        nested_bounds.push((write.base.as_str(), write.index.as_str()));
                    }
                }
                record_unbounded_pointer_arithmetic_output_writes_with_bounds(
                    function,
                    &nested,
                    &nested_bounds,
                    result,
                );
            }
            continue;
        }
        for write in pointer_arithmetic_output_writes_for_statement(statement) {
            let allowed = bounds
                .iter()
                .any(|(base, index)| *base == write.base && *index == write.index);
            if !allowed {
                result.errors.push(TranslationError {
                    kind: "unsupported_syntax".to_string(),
                    message: format!(
                        "output buffer write `{}` is not proven by a bounded length companion",
                        write.source
                    ),
                    source_span: Some(statement.text.clone()),
                });
            }
        }
    }
}

fn mutable_i32_pointer_param(function: &ParsedFunction, name: &str) -> bool {
    function
        .params
        .iter()
        .any(|param| param.name == name && normalize_type(&param.c_type) == "int*")
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

fn parse_bounded_direct_call_expression(
    expression: &str,
    statement_context: &str,
) -> Result<Option<CallExpressionEvidence>, String> {
    let trimmed = expression.trim().trim_end_matches(';').trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    let Some((callee, arguments_text)) = parse_simple_call(trimmed) else {
        return if contains_call_like_syntax(trimmed) {
            Err("callee is not a direct identifier call".to_string())
        } else {
            Ok(None)
        };
    };
    let arguments = split_call_arguments(arguments_text)?;
    for argument in &arguments {
        if contains_inc_dec_operator(argument) {
            return Err(
                "call arguments cannot use increment/decrement value semantics".to_string(),
            );
        }
        if contains_call_like_syntax(argument) {
            return Err("nested call expressions are outside the bounded subset".to_string());
        }
    }
    Ok(Some(CallExpressionEvidence {
        callee: callee.to_string(),
        arguments,
        source_expression: trimmed.to_string(),
        statement_context: statement_context.to_string(),
    }))
}

fn split_call_arguments(arguments_text: &str) -> Result<Vec<String>, String> {
    let trimmed = arguments_text.trim();
    if trimmed.is_empty() {
        return Ok(Vec::new());
    }
    let mut arguments = Vec::new();
    for raw in split_top_level(trimmed, b',') {
        let argument = raw.trim();
        if argument.is_empty() {
            return Err("empty call argument".to_string());
        }
        arguments.push(argument.to_string());
    }
    Ok(arguments)
}

fn contains_call_like_syntax(expression: &str) -> bool {
    let trimmed = expression.trim();
    if trimmed.starts_with("(*") || trimmed.contains(")(") {
        return true;
    }
    for (index, byte) in trimmed.as_bytes().iter().enumerate() {
        if *byte != b'(' {
            continue;
        }
        let before = trimmed[..index].trim_end();
        if before.is_empty() {
            continue;
        }
        let previous = before.as_bytes()[before.len() - 1];
        if previous == b')' || previous.is_ascii_alphanumeric() || previous == b'_' {
            return true;
        }
    }
    false
}

fn call_expression_evidence_for_statement(
    statement: &ParsedStatement,
) -> Vec<CallExpressionEvidence> {
    let mut evidence = Vec::new();
    for (context, expression) in call_expression_contexts(statement) {
        if let Ok(Some(call)) = parse_bounded_direct_call_expression(&expression, &context) {
            evidence.push(call);
        }
    }
    evidence
}

fn call_expression_contexts(statement: &ParsedStatement) -> Vec<(String, String)> {
    match statement.kind {
        StatementKind::PrimitiveDeclaration => parse_declaration(&statement.text)
            .and_then(|declaration| {
                declaration
                    .initializer
                    .map(|initializer| ("declaration_initializer".to_string(), initializer))
            })
            .into_iter()
            .collect(),
        StatementKind::Assignment | StatementKind::PointerWrite => {
            parse_assignment(&statement.text)
                .map(|assignment| vec![("assignment".to_string(), assignment.value)])
                .unwrap_or_default()
        }
        StatementKind::Return => vec![(
            "return".to_string(),
            strip_keyword(&statement.text, "return").to_string(),
        )],
        _ => Vec::new(),
    }
}

fn statement_has_bounded_call_expression(statement: &ParsedStatement) -> bool {
    !call_expression_evidence_for_statement(statement).is_empty()
}

fn record_call_expression_evidence(statements: &[ParsedStatement], result: &mut TranslationResult) {
    for statement in statements {
        for call in call_expression_evidence_for_statement(statement) {
            if !result.plan.call_expressions.iter().any(|item| {
                item.source_expression == call.source_expression
                    && item.statement_context == call.statement_context
            }) {
                result.plan.call_expressions.push(call);
            }
        }
        match statement.kind {
            StatementKind::If => {
                if let Some((_, then_body, else_body)) = parse_if_parts(&statement.text) {
                    record_call_expression_evidence(&parse_statements(&then_body), result);
                    if let Some(else_body) = else_body {
                        record_call_expression_evidence(&parse_statements(&else_body), result);
                    }
                }
            }
            StatementKind::While => {
                if let Some((_, body)) = parse_loop_parts(&statement.text, "while") {
                    record_call_expression_evidence(&parse_statements(&body), result);
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
                    if !step.trim().is_empty() {
                        nested.push(ParsedStatement {
                            kind: classify_statement(&step),
                            text: step,
                        });
                    }
                    record_call_expression_evidence(&nested, result);
                }
            }
            _ => {}
        }
    }
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

pub(crate) fn record_type_mapping(
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

/// Builds legacy pointer evidence from parameter spellings and recognized uses.
///
/// The graph records boundary decisions for reviewers and gates; it is not a
/// proof of aliasing or lifetime safety. Only recognized bounded reads/writes
/// are reported, and suspicious out-pointers are rejected by adding an error.
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
        let boundary_decisions = pointer_boundary_decisions(&param.name, statements);
        let rust_boundary = if boundary_decisions
            .iter()
            .any(|item| item == "bounded_pointer_arithmetic_output_write")
        {
            "&mut [i32]"
        } else if normalize_type(&param.c_type) == "const int*" {
            "&[i32]"
        } else if normalize_type(&param.c_type) == "const void*" {
            "&[u8]"
        } else if role == "borrowed_input" {
            "&str"
        } else {
            "owned safe report"
        };
        let read_effects = pointer_read_effects(&param.name, statements);
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
            read_effects,
            write_effects,
            boundary_decisions,
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
    let mut effects = Vec::new();
    collect_pointer_read_effects(name, statements, &mut effects);
    effects
}

fn collect_pointer_read_effects(
    name: &str,
    statements: &[ParsedStatement],
    effects: &mut Vec<String>,
) {
    for statement in statements {
        match statement.kind {
            StatementKind::For => {
                if let Some((_, condition, _, body)) = parse_for_parts(&statement.text) {
                    let nested = parse_statements(&body);
                    collect_pointer_read_effects(name, &nested, effects);
                    if bounded_buffer_read_in_loop(name, &condition, &nested)
                        && !effects.iter().any(|item| item == &format!("{name}[i]"))
                    {
                        effects.push(format!("{name}[i]"));
                    }
                }
            }
            _ if contains_token(&statement.text, name) => {
                let recorded_buffer_read =
                    push_buffer_read_effects_from_statement(name, statement, effects);
                if !recorded_buffer_read {
                    if statement.kind == StatementKind::PointerWrite {
                        if let Some(lvalue) = statement_lvalue(statement) {
                            if matches!(lvalue, LValue::BoundedPointerArithmeticIndex { .. })
                                && lvalue_base(&lvalue) == Some(name)
                            {
                                continue;
                            }
                        }
                    }
                    let effect = if statement.text.contains(&format!("{name}[i]")) {
                        format!("{name}[i]")
                    } else {
                        statement.text.clone()
                    };
                    if !effects.iter().any(|item| item == &effect) {
                        effects.push(effect);
                    }
                }
            }
            _ => {}
        }
    }
}

fn push_buffer_read_effects_from_statement(
    name: &str,
    statement: &ParsedStatement,
    effects: &mut Vec<String>,
) -> bool {
    let mut recorded = false;
    for read in bounded_input_buffer_reads_for_statement(statement) {
        if read.base != name {
            continue;
        }
        let canonical = read.canonical_source();
        if !effects.iter().any(|item| item == &canonical) {
            effects.push(canonical);
        }
        if read.pointer_arithmetic && !effects.iter().any(|item| item == &read.source) {
            effects.push(read.source);
        }
        recorded = true;
    }
    recorded
}

fn bounded_buffer_read_in_loop(
    name: &str,
    condition: &str,
    statements: &[ParsedStatement],
) -> bool {
    statements
        .iter()
        .flat_map(bounded_input_buffer_reads_for_statement)
        .any(|read| read.base == name && loop_condition_bounds_index(condition, &read.index, "len"))
}

fn bounded_pointer_arithmetic_read_in_loop(
    name: &str,
    condition: &str,
    statements: &[ParsedStatement],
) -> bool {
    statements
        .iter()
        .flat_map(bounded_input_buffer_reads_for_statement)
        .any(|read| {
            read.base == name
                && read.pointer_arithmetic
                && loop_condition_bounds_index(condition, &read.index, "len")
        })
}

fn bounded_pointer_arithmetic_output_write_in_loop(
    name: &str,
    condition: &str,
    statements: &[ParsedStatement],
) -> bool {
    statements
        .iter()
        .flat_map(pointer_arithmetic_output_writes_for_statement)
        .any(|write| {
            write.base == name && loop_condition_bounds_index(condition, &write.index, "len")
        })
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct BufferRead {
    base: String,
    index: String,
    source: String,
    pointer_arithmetic: bool,
}

impl BufferRead {
    fn canonical_source(&self) -> String {
        format!("{}[{}]", self.base, self.index)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct OutputBufferWrite {
    base: String,
    index: String,
    source: String,
}

fn pointer_arithmetic_output_writes_for_statement(
    statement: &ParsedStatement,
) -> Vec<OutputBufferWrite> {
    if statement.kind != StatementKind::PointerWrite {
        return Vec::new();
    }
    let Some(assignment) = parse_assignment(&statement.text) else {
        return Vec::new();
    };
    match parse_lvalue(&assignment.target) {
        LValue::BoundedPointerArithmeticIndex {
            base,
            index,
            source,
        } => vec![OutputBufferWrite {
            base,
            index,
            source,
        }],
        _ => Vec::new(),
    }
}

fn bounded_input_buffer_reads(text: &str) -> Vec<BufferRead> {
    let mut reads = Vec::new();
    collect_array_index_buffer_reads(text, &mut reads);
    collect_pointer_arithmetic_buffer_reads(text, &mut reads);
    reads
}

/// Extracts bounded buffer-read evidence from the value side of a statement.
///
/// The walker follows accepted nested control-flow bodies but only records
/// index and pointer-arithmetic patterns that the compatibility translator can
/// later justify. Other expression forms intentionally produce no evidence.
fn bounded_input_buffer_reads_for_statement(statement: &ParsedStatement) -> Vec<BufferRead> {
    match statement.kind {
        StatementKind::PrimitiveDeclaration => parse_declaration(&statement.text)
            .and_then(|declaration| declaration.initializer)
            .map(|initializer| bounded_input_buffer_reads(&initializer))
            .unwrap_or_default(),
        StatementKind::Assignment | StatementKind::PointerWrite => {
            parse_assignment(&statement.text)
                .map(|assignment| bounded_input_buffer_reads(&assignment.value))
                .unwrap_or_default()
        }
        StatementKind::CompoundAssignment => parse_compound_assignment(&statement.text)
            .map(|assignment| bounded_input_buffer_reads(&assignment.value))
            .unwrap_or_default(),
        StatementKind::Return => {
            bounded_input_buffer_reads(strip_keyword(&statement.text, "return"))
        }
        StatementKind::If => parse_if_parts(&statement.text)
            .map(|(condition, then_body, else_body)| {
                let mut reads = bounded_input_buffer_reads(&condition);
                reads.extend(
                    parse_statements(&then_body)
                        .iter()
                        .flat_map(bounded_input_buffer_reads_for_statement),
                );
                if let Some(else_body) = else_body {
                    reads.extend(
                        parse_statements(&else_body)
                            .iter()
                            .flat_map(bounded_input_buffer_reads_for_statement),
                    );
                }
                reads
            })
            .unwrap_or_default(),
        StatementKind::While => parse_loop_parts(&statement.text, "while")
            .map(|(condition, body)| {
                let mut reads = bounded_input_buffer_reads(&condition);
                reads.extend(
                    parse_statements(&body)
                        .iter()
                        .flat_map(bounded_input_buffer_reads_for_statement),
                );
                reads
            })
            .unwrap_or_default(),
        StatementKind::For => parse_for_parts(&statement.text)
            .map(|(_, condition, _, body)| {
                let mut reads = bounded_input_buffer_reads(&condition);
                reads.extend(
                    parse_statements(&body)
                        .iter()
                        .flat_map(bounded_input_buffer_reads_for_statement),
                );
                reads
            })
            .unwrap_or_default(),
        StatementKind::Expression
        | StatementKind::SimpleCall
        | StatementKind::BoundedInputBufferRead
        | StatementKind::IncDec
        | StatementKind::UnsupportedLValue => Vec::new(),
    }
}

fn collect_array_index_buffer_reads(text: &str, reads: &mut Vec<BufferRead>) {
    let bytes = text.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index] != b'[' {
            index += 1;
            continue;
        }
        let base_start = text[..index]
            .rfind(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .map(|pos| pos + 1)
            .unwrap_or(0);
        let base = text[base_start..index].trim();
        let Some(close_offset) = text[index + 1..].find(']') else {
            break;
        };
        let close = index + 1 + close_offset;
        let subscript = text[index + 1..close].trim();
        if is_simple_identifier(base) && is_simple_identifier(subscript) {
            reads.push(BufferRead {
                base: base.to_string(),
                index: subscript.to_string(),
                source: text[base_start..=close].trim().to_string(),
                pointer_arithmetic: false,
            });
        }
        index = close + 1;
    }
}

fn collect_pointer_arithmetic_buffer_reads(text: &str, reads: &mut Vec<BufferRead>) {
    let bytes = text.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index] != b'*' || !is_unary_deref_context(text, index) {
            index += 1;
            continue;
        }
        let open = skip_whitespace(text, index + 1);
        if bytes.get(open) != Some(&b'(') {
            index += 1;
            continue;
        }
        let Some(close) = find_matching_byte(text, open, b'(', b')') else {
            break;
        };
        let inner = text[open + 1..close].trim();
        let parts = split_top_level(inner, b'+');
        if parts.len() == 2 {
            let base = parts[0].trim();
            let read_index = parts[1].trim();
            if is_simple_identifier(base) && is_simple_identifier(read_index) {
                reads.push(BufferRead {
                    base: base.to_string(),
                    index: read_index.to_string(),
                    source: text[index..=close].trim().to_string(),
                    pointer_arithmetic: true,
                });
            }
        }
        index = close + 1;
    }
}

fn is_unary_deref_context(text: &str, star_index: usize) -> bool {
    let prefix = text[..star_index].trim_end();
    if prefix.is_empty() || prefix.ends_with("return") {
        return true;
    }
    prefix
        .as_bytes()
        .last()
        .map(|byte| {
            matches!(
                *byte,
                b'=' | b'('
                    | b'{'
                    | b'['
                    | b','
                    | b';'
                    | b':'
                    | b'?'
                    | b'+'
                    | b'-'
                    | b'*'
                    | b'/'
                    | b'%'
                    | b'&'
                    | b'|'
                    | b'^'
                    | b'!'
                    | b'<'
                    | b'>'
            )
        })
        .unwrap_or(true)
}

fn loop_condition_bounds_index(condition: &str, index_name: &str, len_name: &str) -> bool {
    let normalized = condition.split_whitespace().collect::<String>();
    normalized == format!("{index_name}<{len_name}")
        || normalized == format!("0<={index_name}&&{index_name}<{len_name}")
}

fn pointer_write_effects(name: &str, statements: &[ParsedStatement]) -> Vec<String> {
    let mut effects = Vec::new();
    collect_pointer_write_effects(name, statements, &mut effects);
    effects
}

fn collect_pointer_write_effects(
    name: &str,
    statements: &[ParsedStatement],
    effects: &mut Vec<String>,
) {
    for statement in statements {
        if statement.kind == StatementKind::For {
            if let Some((_, _, _, body)) = parse_for_parts(&statement.text) {
                collect_pointer_write_effects(name, &parse_statements(&body), effects);
            }
            continue;
        }
        if statement.kind != StatementKind::PointerWrite {
            continue;
        }
        let Some(lvalue) = statement_lvalue(statement) else {
            continue;
        };
        if lvalue_base(&lvalue) != Some(name) {
            continue;
        }
        for effect in lvalue_write_effects(&lvalue) {
            if !effects.iter().any(|item| item == &effect) {
                effects.push(effect);
            }
        }
    }
}

/// Classifies the public Rust boundary suggested for one C pointer parameter.
///
/// Decisions are derived from bounded legacy patterns such as loop-guarded
/// reads, pointer arithmetic reads, output-buffer writes, and wrapper
/// candidates. The labels are evidence for route selection, not generalized
/// pointer reasoning.
fn pointer_boundary_decisions(name: &str, statements: &[ParsedStatement]) -> Vec<String> {
    let mut decisions = Vec::new();
    for statement in statements {
        if statement.kind == StatementKind::For {
            if let Some((_, condition, _, body)) = parse_for_parts(&statement.text) {
                let nested = parse_statements(&body);
                if bounded_buffer_read_in_loop(name, &condition, &nested)
                    && !decisions.iter().any(|item| item == "bounded_input_buffer")
                {
                    decisions.push("bounded_input_buffer".to_string());
                }
                if bounded_pointer_arithmetic_read_in_loop(name, &condition, &nested)
                    && !decisions
                        .iter()
                        .any(|item| item == "bounded_pointer_arithmetic_input_read")
                {
                    decisions.push("bounded_pointer_arithmetic_input_read".to_string());
                }
                if bounded_pointer_arithmetic_output_write_in_loop(name, &condition, &nested)
                    && !decisions
                        .iter()
                        .any(|item| item == "bounded_pointer_arithmetic_output_write")
                {
                    decisions.push("bounded_pointer_arithmetic_output_write".to_string());
                }
            }
        }
        if statement.kind != StatementKind::PointerWrite {
            continue;
        }
        let Some(lvalue) = statement_lvalue(statement) else {
            continue;
        };
        if lvalue_base(&lvalue) != Some(name) {
            continue;
        };
        let decision = match lvalue {
            LValue::BoundedPointerIndex { .. } => "bounded_pointer_index",
            LValue::BoundedPointerArithmeticIndex { .. } => {
                "bounded_pointer_arithmetic_output_write"
            }
            LValue::PointerField { .. } | LValue::DerefIdentifier { .. } => {
                "safe_wrapper_candidate"
            }
            _ => continue,
        };
        if !decisions.iter().any(|item| item == decision) {
            decisions.push(decision.to_string());
        }
    }
    decisions
}

fn statement_mutates_target(statement: &ParsedStatement, target: &str) -> bool {
    match statement.kind {
        StatementKind::Assignment | StatementKind::PointerWrite => {
            parse_assignment(&statement.text)
                .map(|assignment| assignment.target == target)
                .unwrap_or(false)
        }
        StatementKind::CompoundAssignment => parse_compound_assignment(&statement.text)
            .map(|assignment| assignment.target == target)
            .unwrap_or(false),
        StatementKind::IncDec => parse_inc_dec_statement(&statement.text)
            .map(|inc_dec| inc_dec.target == target)
            .unwrap_or(false),
        StatementKind::If => parse_if_parts(&statement.text)
            .map(|(_, then_body, else_body)| {
                parse_statements(&then_body)
                    .iter()
                    .any(|nested| statement_mutates_target(nested, target))
                    || else_body
                        .as_deref()
                        .map(|body| {
                            parse_statements(body)
                                .iter()
                                .any(|nested| statement_mutates_target(nested, target))
                        })
                        .unwrap_or(false)
            })
            .unwrap_or(false),
        StatementKind::While => parse_loop_parts(&statement.text, "while")
            .map(|(_, body)| {
                parse_statements(&body)
                    .iter()
                    .any(|nested| statement_mutates_target(nested, target))
            })
            .unwrap_or(false),
        StatementKind::For => parse_for_parts(&statement.text)
            .map(|(init, _, step, body)| {
                let init_mutates = !init.trim().is_empty()
                    && statement_mutates_target(
                        &ParsedStatement {
                            kind: classify_statement(&init),
                            text: init,
                        },
                        target,
                    );
                let step_mutates = !step.trim().is_empty()
                    && statement_mutates_target(
                        &ParsedStatement {
                            kind: classify_statement(&step),
                            text: step.clone(),
                        },
                        target,
                    );
                init_mutates
                    || step_mutates
                    || parse_statements(&body)
                        .iter()
                        .any(|nested| statement_mutates_target(nested, target))
            })
            .unwrap_or(false),
        _ => false,
    }
}

fn param_is_mutated(param: &Param, statements: &[ParsedStatement]) -> bool {
    statements
        .iter()
        .any(|statement| statement_mutates_target(statement, &param.name))
}

fn supports_pointer_body_translation(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
) -> bool {
    let has_const_i32_input = function
        .params
        .iter()
        .any(|param| normalize_type(&param.c_type) == "const int*");
    let has_out = function
        .params
        .iter()
        .any(|param| normalize_type(&param.c_type) == "int*");
    has_const_i32_input
        && has_out
        && statements
            .iter()
            .any(statement_has_bounded_input_buffer_read)
        && statements.iter().any(|statement| {
            pointer_lvalue_rule(&statement.text) == Some("bounded-pointer-index-write")
        })
}

fn supports_pointer_output_buffer_translation(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
) -> bool {
    function
        .params
        .iter()
        .any(|param| normalize_type(&param.c_type) == "int*")
        && statements
            .iter()
            .any(statement_has_bounded_pointer_arithmetic_output_write)
}

/// Emits Rust for the accepted legacy subset after all compatibility gates pass.
///
/// This is the last step in the candidate path. It chooses among a few
/// historical templates and safe-wrapper shapes already backed by collected
/// evidence; it does not lower arbitrary C and must not be used to bypass typed
/// IR fail-closed errors.
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
        record_statement_rules(statements, result);
        if supports_pointer_output_buffer_translation(function, statements) {
            let rust_params = function
                .params
                .iter()
                .map(|param| {
                    format!(
                        "{}: {}",
                        param.name,
                        public_pointer_buffer_param_type(&param.c_type)
                    )
                })
                .collect::<Vec<_>>()
                .join(", ");
            let body_lines = emit_safe_pointer_body(statements, 1);
            return format!(
                "pub fn {}({rust_params}) -> i32 {{\n{}\n}}\n",
                function.name,
                body_lines
                    .into_iter()
                    .map(|line| if line.is_empty() {
                        "    0".to_string()
                    } else {
                        line
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            );
        }
        if supports_pointer_body_translation(function, statements) {
            let rust_params = function
                .params
                .iter()
                .filter(|param| param.c_type.starts_with("const ") || !param.c_type.contains('*'))
                .map(|param| format!("{}: {}", param.name, public_param_type(&param.c_type)))
                .collect::<Vec<_>>()
                .join(", ");
            let body_lines = emit_safe_pointer_body(statements, 1);
            return format!(
                "pub fn {}({rust_params}) -> i32 {{\n{}\n}}\n",
                function.name,
                body_lines
                    .into_iter()
                    .map(|line| if line.is_empty() {
                        "    0".to_string()
                    } else {
                        line
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            );
        }
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
        .map(|param| {
            let mutability = if param_is_mutated(param, statements) {
                "mut "
            } else {
                ""
            };
            format!(
                "{mutability}{}: {}",
                param.name,
                public_param_type(&param.c_type)
            )
        })
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

fn emit_safe_pointer_body(statements: &[ParsedStatement], indent_level: usize) -> Vec<String> {
    let mut lines = Vec::new();
    let mut output_return_emitted = false;
    for statement in statements {
        if output_return_emitted && statement.kind == StatementKind::Return {
            continue;
        }
        if statement.kind == StatementKind::PointerWrite {
            if let Some(assignment) = parse_assignment(&statement.text) {
                if matches!(
                    parse_lvalue(&assignment.target),
                    LValue::BoundedPointerIndex { .. }
                ) {
                    lines.push(format!(
                        "{}return {};",
                        indent(indent_level),
                        translate_expr(&assignment.value)
                    ));
                    output_return_emitted = true;
                    continue;
                }
            }
        }
        lines.extend(emit_rust_statement(statement, indent_level));
    }
    lines
}

fn record_statement_rules(statements: &[ParsedStatement], result: &mut TranslationResult) {
    for statement in statements {
        if statement_has_bounded_call_expression(statement) {
            push_rule_once(
                &mut result.plan.translation_rule_ids,
                "bounded-call-expression",
            );
        }
        let rule = match statement.kind {
            StatementKind::PrimitiveDeclaration => Some("primitive-declaration"),
            StatementKind::Assignment => Some("assignment"),
            StatementKind::CompoundAssignment => Some("compound-assignment"),
            StatementKind::IncDec => Some("increment-decrement"),
            StatementKind::Return => Some("structured-return-expression"),
            StatementKind::SimpleCall => Some("simple-call"),
            StatementKind::If => Some("structured-if"),
            StatementKind::While => Some("structured-while"),
            StatementKind::For => {
                if statement_has_bounded_input_buffer_read(statement) {
                    push_rule_once(
                        &mut result.plan.translation_rule_ids,
                        "bounded-input-buffer-read",
                    );
                }
                if statement_has_bounded_pointer_arithmetic_input_read(statement) {
                    push_rule_once(
                        &mut result.plan.translation_rule_ids,
                        "bounded-pointer-arithmetic-input-read",
                    );
                }
                if statement_has_bounded_pointer_arithmetic_output_write(statement) {
                    push_rule_once(
                        &mut result.plan.translation_rule_ids,
                        "bounded-pointer-arithmetic-output-write",
                    );
                }
                Some("structured-for")
            }
            StatementKind::BoundedInputBufferRead => Some("bounded-input-buffer-read"),
            StatementKind::PointerWrite => {
                push_rule_once(
                    &mut result.plan.translation_rule_ids,
                    "pointer-write-recorded",
                );
                if let Some(rule) = pointer_lvalue_rule(&statement.text) {
                    push_rule_once(&mut result.plan.translation_rule_ids, rule);
                }
                continue;
            }
            StatementKind::UnsupportedLValue | StatementKind::Expression => None,
        };
        if let Some(rule) = rule {
            push_rule_once(&mut result.plan.translation_rule_ids, rule);
        }
    }
}

fn pointer_lvalue_rule(text: &str) -> Option<&'static str> {
    match statement_lvalue(&ParsedStatement {
        text: text.to_string(),
        kind: StatementKind::PointerWrite,
    })? {
        LValue::PointerField { .. } => Some("pointer-field-write"),
        LValue::DerefIdentifier { .. } => Some("pointer-deref-write"),
        LValue::BoundedPointerIndex { .. } => Some("bounded-pointer-index-write"),
        LValue::BoundedPointerArithmeticIndex { .. } => {
            Some("bounded-pointer-arithmetic-output-write")
        }
        _ => None,
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
        StatementKind::BoundedInputBufferRead => {
            vec![format!("{prefix}{};", translate_expr(&statement.text))]
        }
        StatementKind::CompoundAssignment => parse_compound_assignment(&statement.text)
            .map(|assignment| {
                vec![format!(
                    "{prefix}{} {} {};",
                    translate_expr(&assignment.target),
                    assignment.operator,
                    translate_expr(&assignment.value)
                )]
            })
            .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))]),
        StatementKind::IncDec => parse_inc_dec_statement(&statement.text)
            .map(|inc_dec| {
                vec![format!(
                    "{prefix}{} {} 1;",
                    translate_expr(&inc_dec.target),
                    inc_dec.delta_operator
                )]
            })
            .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))]),
        StatementKind::Return => vec![format!(
            "{prefix}return {};",
            translate_expr(strip_keyword(&statement.text, "return"))
        )],
        StatementKind::SimpleCall
        | StatementKind::UnsupportedLValue
        | StatementKind::Expression => {
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
    if let Some(inc_dec) = parse_inc_dec_statement(trimmed) {
        return format!(
            "{} {} 1",
            translate_expr(&inc_dec.target),
            inc_dec.delta_operator
        );
    }
    if let Some(assignment) = parse_compound_assignment(trimmed) {
        return format!(
            "{} {} {}",
            translate_expr(&assignment.target),
            assignment.operator,
            translate_expr(&assignment.value)
        );
    }
    translate_expr(trimmed)
}

fn indent(level: usize) -> String {
    "    ".repeat(level)
}

fn public_param_type(c_type: &str) -> &'static str {
    map_c_type(c_type).unwrap_or("/* unsupported */ ()")
}

fn public_pointer_buffer_param_type(c_type: &str) -> &'static str {
    match normalize_type(c_type).as_str() {
        "int*" => "&mut [i32]",
        _ => public_param_type(c_type),
    }
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
    let mut out = expr.trim().to_string();
    for read in bounded_input_buffer_reads(expr) {
        out = out.replace(
            &read.source,
            &format!("{}[{} as usize]", read.base, read.index),
        );
    }
    out
}

#[cfg(test)]
mod tests {
    //! Behavior-regression locks for the legacy string translator, moved here
    //! from tests/bounded_translation.rs when the `translate_slice` export was
    //! demoted from the public API (P1-R6). The legacy translator is retired to
    //! a compatibility candidate source: these tests pin its existing emitted
    //! Rust text and legacy-specific refusal paths so they cannot drift, and
    //! they must not be used as a basis for extending its C coverage. New
    //! forward translation coverage belongs to the clang-lowered typed IR route
    //! and its artifact-level integration tests.

    use super::translate_slice;
    use crate::{BuildProfile, SliceSpec};

    // Minimal copy of the shared `profile` helper from
    // tests/bounded_translation.rs so the moved tests keep their original
    // build-profile inputs verbatim.
    fn profile(clang_available: bool) -> BuildProfile {
        BuildProfile {
            include_paths: vec!["/tmp/lib/include".to_string()],
            defines: vec!["_GNU_SOURCE".to_string()],
            target: None,
            clang_ast_fixture: None,
            target_triple: Some("x86_64-unknown-linux-gnu".to_string()),
            abi: Some("linux-gnu".to_string()),
            compiler_command_source: "compile_commands.json".to_string(),
            clang_available,
        }
    }

    #[test]
    fn translates_structured_integer_function_and_emits_type_map_and_cfg() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-one".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn add_one(value: i32) -> i32"));
        assert!(result.rust_code.contains("value + 1"));
        assert_eq!(result.type_map.mappings[0].c_type, "int");
        assert_eq!(result.type_map.mappings[0].rust_type, "i32");
        assert_eq!(result.cfg.functions[0].name, "add_one");
        assert_eq!(result.cfg.functions[0].blocks[0].terminator, "return");
        assert!(result.pointer_graph.nodes.is_empty());
        assert_eq!(result.plan.unsupported_node_count, 0);
    }

    #[test]
    fn pointer_out_param_generates_safe_public_boundary_and_pointer_graph() {
        let spec = SliceSpec {
        target_id: "libuv".to_string(),
        slice_id: "ip4-addr".to_string(),
        source_commit: "5e7d51a".to_string(),
        function_name: "uv_ip4_addr".to_string(),
        c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn uv_ip4_addr(ip: &str, port: i32)"));
        assert!(!result.rust_code.contains("*mut sockaddr_in"));
        assert_eq!(result.pointer_graph.nodes.len(), 2);
        assert!(result
            .pointer_graph
            .nodes
            .iter()
            .any(|node| node.id == "ip" && node.role == "borrowed_input"));
        assert!(result
            .pointer_graph
            .nodes
            .iter()
            .any(|node| node.id == "addr" && node.role == "out_param"));
        let addr = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "addr")
            .expect("addr pointer node");
        assert!(addr.write_effects.contains(&"addr->sin_family".to_string()));
        assert!(addr
            .read_effects
            .contains(&"addr->sin_family = AF_INET".to_string()));
        assert_eq!(result.plan.unsafe_candidate_count, 0);
    }

    #[test]
    fn bounded_pointer_index_write_generates_safe_boundary_and_decision() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "fill-first".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "fill_first".to_string(),
            c_source: "int fill_first(int* out, int value) { out[0] = value; return 0; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("pub fn fill_first(value: i32)"));
        assert!(!result.rust_code.contains("*mut"));
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert_eq!(out.role, "out_param");
        assert!(out.write_effects.contains(&"out[0]".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-index-write".to_string()));
    }

    #[test]
    fn bounded_pointer_index_compound_assignment_records_decision() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-first".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_first".to_string(),
            c_source: "int add_first(int* out, int value) { out[0] += value; return 0; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert!(out.write_effects.contains(&"out[0]".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-index-write".to_string()));
    }

    #[test]
    fn bounded_input_buffer_read_generates_safe_slice_boundary_and_decisions() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-i32-buffer".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_i32_buffer".to_string(),
        c_source: "int sum_i32_buffer(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + values[i]; } out[0] = total; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn sum_i32_buffer(values: &[i32], len: i32)"));
        assert!(result
            .rust_code
            .contains("total = total + values[i as usize];"));
        assert!(!result.rust_code.contains("*const"));
        assert!(!result.rust_code.contains("*mut"));
        let values = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "values")
            .expect("values pointer node");
        assert_eq!(values.role, "borrowed_input");
        assert!(values.read_effects.contains(&"values[i]".to_string()));
        assert!(values
            .boundary_decisions
            .contains(&"bounded_input_buffer".to_string()));
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert_eq!(out.role, "out_param");
        assert!(out.write_effects.contains(&"out[0]".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-input-buffer-read".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-index-write".to_string()));
    }

    #[test]
    fn bounded_pointer_arithmetic_read_generates_safe_slice_boundary_and_decisions() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-i32-ptr-arith".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_i32_ptr_arith".to_string(),
        c_source: "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn sum_i32_ptr_arith(values: &[i32], len: i32)"));
        assert!(result
            .rust_code
            .contains("total = total + values[i as usize];"));
        assert!(!result.rust_code.contains("*(values + i)"));
        assert!(!result.rust_code.contains("*const"));
        assert!(!result.rust_code.contains("*mut"));
        let values = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "values")
            .expect("values pointer node");
        assert_eq!(values.role, "borrowed_input");
        assert!(values.read_effects.contains(&"values[i]".to_string()));
        assert!(values.read_effects.contains(&"*(values + i)".to_string()));
        assert!(values
            .boundary_decisions
            .contains(&"bounded_input_buffer".to_string()));
        assert!(values
            .boundary_decisions
            .contains(&"bounded_pointer_arithmetic_input_read".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-input-buffer-read".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
    }

    #[test]
    fn flashdb_crc32_byte_cursor_loop_blocks_without_legacy_canned_template() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "real-fdb-calc-crc32".to_string(),
            source_commit: "93d1755".to_string(),
            function_name: "fdb_calc_crc32".to_string(),
            c_source: "uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size)
{
    const uint8_t *p;

    p = (const uint8_t *)buf;
    crc = crc ^ ~0U;

    while (size--) {
        crc = crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
    }

    return crc ^ ~0U;
}"
            .to_string(),
            fixture_hash: "real-fdb-calc-crc32-fixture".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.rust_code.is_empty());
        assert!(!result.rust_code.contains("crc32_update_byte"));
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"crc32-byte-cursor-loop".to_string()));
        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"),
            "{:?}",
            result.errors
        );
        assert!(result
            .errors
            .iter()
            .any(|error| error.message.contains("increment/decrement")));
    }

    #[test]
    fn bounded_pointer_arithmetic_output_write_generates_safe_mut_slice_boundary_and_decisions() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "fill-i32-ptr-arith-out".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "fill_i32_ptr_arith_out".to_string(),
        c_source: "int fill_i32_ptr_arith_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn fill_i32_ptr_arith_out(out: &mut [i32], len: i32, value: i32)"));
        assert!(result.rust_code.contains("out[i as usize] = value;"));
        assert!(!result.rust_code.contains("*(out + i)"));
        assert!(!result.rust_code.contains("*mut"));
        let out = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "out")
            .expect("out pointer node");
        assert_eq!(out.role, "out_param");
        assert_eq!(out.rust_boundary, "&mut [i32]");
        assert!(out.write_effects.contains(&"out[i]".to_string()));
        assert!(out.write_effects.contains(&"*(out + i)".to_string()));
        assert!(out
            .boundary_decisions
            .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .lvalue_kinds
            .contains(&"bounded_pointer_arithmetic_output_buffer".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-output-write".to_string()));
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
    }

    #[test]
    fn bounded_pointer_arithmetic_writes_do_not_count_as_input_buffer_reads() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "ptr-arith-write".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "ptr_arith_write".to_string(),
        c_source: "int ptr_arith_write(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(!result
            .cfg
            .functions
            .iter()
            .flat_map(|function| function.blocks.iter())
            .flat_map(|block| block.statement_kinds.iter())
            .any(|kind| kind == "bounded_input_buffer_read"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"bounded_pointer_arithmetic_output_write".to_string()));
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-pointer-arithmetic-input-read".to_string()));
    }

    #[test]
    fn translates_primitive_declaration_assignment_and_return() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "local-state".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "local_state".to_string(),
        c_source:
            "int local_state(int value) { int total = value + 1; total = total + 2; return total; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("let mut total: i32 = value + 1;"));
        assert!(result.rust_code.contains("total = total + 2;"));
        assert!(result.rust_code.contains("return total;"));
        assert!(result.type_map.mappings.iter().any(|mapping| {
            mapping.symbol == "total" && mapping.c_type == "int" && mapping.rust_type == "i32"
        }));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"primitive_declaration".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"assignment".to_string()));
    }

    #[test]
    fn translates_if_else_with_cfg_branch_edges() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "clamp".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "clamp_non_negative".to_string(),
        c_source: "int clamp_non_negative(int value) { if (value < 0) { return 0; } else { return value; } }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("if value < 0 {"));
        assert!(result.rust_code.contains("} else {"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"if".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .edges
            .iter()
            .any(|edge| edge.starts_with("entry->if-")));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"structured-if".to_string()));
    }

    #[test]
    fn translates_while_loop_with_cfg_back_edge() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-while".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_while".to_string(),
        c_source: "int sum_while(int limit) { int total = 0; while (limit > 0) { total = total + limit; limit = limit - 1; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("while limit > 0 {"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"while".to_string()));
        assert!(result.cfg.functions[0].blocks[0]
            .edges
            .iter()
            .any(|edge| edge.starts_with("entry->while-")));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"structured-while".to_string()));
    }

    #[test]
    fn translates_for_loop_by_lowering_to_bounded_while() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-for".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_for".to_string(),
        c_source: "int sum_for(int limit) { int total = 0; for (int i = 0; i < limit; i++) { total = total + i; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("let mut i: i32 = 0;"));
        assert!(result.rust_code.contains("while i < limit {"));
        assert!(result.rust_code.contains("i += 1;"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"for".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"structured-for".to_string()));
    }

    #[test]
    fn translates_for_loop_with_compound_assignment_step() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "sum-for-compound-step".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "sum_for_compound_step".to_string(),
        c_source: "int sum_for_compound_step(int limit) { int total = 0; for (int i = 0; i < limit; i += 1) { total = total + i; } return total; }"
            .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("while i < limit {"));
        assert!(result.rust_code.contains("i += 1;"));
    }

    #[test]
    fn translates_simple_call_expression_and_records_call_rule() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "call_hook".to_string(),
            c_source: "int call_hook(int value) { observe(value); return value; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result.rust_code.contains("observe(value);"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"simple_call".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"simple-call".to_string()));
    }

    #[test]
    fn translates_direct_call_expressions_and_records_callee_evidence() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "call-expression".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "call_expression".to_string(),
        c_source: "int call_expression(int value) { int first = helper(value); value = helper(first); return helper(value); }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("let mut first: i32 = helper(value);"));
        assert!(result.rust_code.contains("value = helper(first);"));
        assert!(result.rust_code.contains("return helper(value);"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"call_expression".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));

        let plan = serde_json::to_value(&result.plan).unwrap();
        let calls = plan["call_expressions"].as_array().unwrap();
        assert_eq!(calls.len(), 3);
        assert_eq!(calls[0]["callee"], "helper");
        assert_eq!(calls[0]["arguments"], serde_json::json!(["value"]));
        assert_eq!(calls[1]["source_expression"], "helper(first)");
        assert_eq!(calls[2]["statement_context"], "return");
    }

    #[test]
    fn translates_compound_assignment_statement_and_records_rule() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "compound-assignment".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "compound_assignment".to_string(),
        c_source:
            "int compound_assignment(int value) { value += 1; value-=1; value *= 2; return value; }"
                .to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn compound_assignment(mut value: i32) -> i32"));
        assert!(result.rust_code.contains("value += 1;"));
        assert!(result.rust_code.contains("value -= 1;"));
        assert!(result.rust_code.contains("value *= 2;"));
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"compound_assignment".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"compound-assignment".to_string()));
    }

    #[test]
    fn translates_increment_and_decrement_statements_and_records_rule() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "inc-dec".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "inc_dec".to_string(),
            c_source:
                "int inc_dec(int value) { value++; --value; ++value; value--; return value; }"
                    .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn inc_dec(mut value: i32) -> i32"));
        assert_eq!(result.rust_code.matches("value += 1;").count(), 2);
        assert_eq!(result.rust_code.matches("value -= 1;").count(), 2);
        assert!(result.cfg.functions[0].blocks[0]
            .statement_kinds
            .contains(&"inc_dec".to_string()));
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"increment-decrement".to_string()));
    }

    #[test]
    fn legacy_translation_rejects_leading_zero_octal_integer_literals() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "octal-literal-reject".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_octal".to_string(),
            c_source: "int add_octal(int value) { int base = 010; return value + base; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"
                    && error.message.contains("leading-zero integer literal")),
            "{:?}",
            result.errors
        );
        assert!(!result.rust_code.contains("010"));
    }

    #[test]
    fn legacy_translation_rejects_leading_zero_octal_literal_in_return_expression() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "octal-return-reject".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "permission_bits".to_string(),
            c_source: "int permission_bits(int value) { return value + 0644; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "unsupported_syntax"
                    && error.message.contains("leading-zero integer literal")),
            "{:?}",
            result.errors
        );
    }

    #[test]
    fn legacy_translation_accepts_hex_and_plain_zero_literals() {
        let spec = SliceSpec {
        target_id: "demo".to_string(),
        slice_id: "hex-zero-accept".to_string(),
        source_commit: "1234567".to_string(),
        function_name: "mask_low_bits".to_string(),
        c_source: "int mask_low_bits(int value) { int mask = 0xFF; if (value == 0) { return 0; } return value & mask; }".to_string(),
        fixture_hash: "fixture-sha".to_string(),
        build_profile: profile(true),
        ..SliceSpec::default()
    };

        let result = translate_slice(&spec);

        assert!(
            !result
                .errors
                .iter()
                .any(|error| error.message.contains("leading-zero integer literal")),
            "{:?}",
            result.errors
        );
    }

    #[test]
    fn legacy_translation_rejects_bare_char_type_as_type_uncertainty() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "bare-char-reject".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "is_negative_char".to_string(),
            c_source: "int is_negative_char(char value) { if (value < 0) { return 1; } return 0; }"
                .to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(true),
            ..SliceSpec::default()
        };

        let result = translate_slice(&spec);

        assert!(
            result
                .errors
                .iter()
                .any(|error| error.kind == "type_uncertainty"),
            "{:?}",
            result.errors
        );
        assert!(result
            .type_map
            .uncertainties
            .iter()
            .any(|uncertainty| uncertainty.c_type == "char"));
        assert!(!result
            .rust_code
            .contains("pub fn is_negative_char(value: u8)"));
    }
}
