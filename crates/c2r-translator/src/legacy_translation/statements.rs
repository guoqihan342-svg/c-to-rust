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
