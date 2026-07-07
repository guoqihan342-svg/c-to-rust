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
