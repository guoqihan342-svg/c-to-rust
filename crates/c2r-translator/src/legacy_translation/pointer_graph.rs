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
