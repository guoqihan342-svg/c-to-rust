
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
