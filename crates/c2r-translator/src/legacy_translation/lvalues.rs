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
