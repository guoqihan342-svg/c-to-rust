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
