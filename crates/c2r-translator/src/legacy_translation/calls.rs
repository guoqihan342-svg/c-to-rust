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
