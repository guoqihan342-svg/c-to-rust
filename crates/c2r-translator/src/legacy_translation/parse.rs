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
