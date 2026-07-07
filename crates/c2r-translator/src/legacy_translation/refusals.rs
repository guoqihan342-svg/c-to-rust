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
