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
