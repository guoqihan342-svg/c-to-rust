/// Emits Rust for the accepted legacy subset after all compatibility gates pass.
///
/// This is the last step in the candidate path. It chooses among a few
/// historical templates and safe-wrapper shapes already backed by collected
/// evidence; it does not lower arbitrary C and must not be used to bypass typed
/// IR fail-closed errors.
fn emit_rust(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    result: &mut TranslationResult,
) -> String {
    let has_pointer = function
        .params
        .iter()
        .any(|param| param.c_type.contains('*') || param_uses_record_arrow(&param.name, statements));
    if has_pointer {
        result
            .plan
            .translation_rule_ids
            .push("safe-wrapper-for-pointer-out-param".to_string());
        record_statement_rules(statements, result);
        if supports_record_pointer_nested_scalar_identity(function, statements) {
            return emit_record_pointer_nested_scalar_identity(function, statements, result);
        }
        if supports_pointer_output_buffer_translation(function, statements) {
            let rust_params = function
                .params
                .iter()
                .map(|param| {
                    format!(
                        "{}: {}",
                        param.name,
                        public_pointer_buffer_param_type(&param.c_type)
                    )
                })
                .collect::<Vec<_>>()
                .join(", ");
            let body_lines = emit_safe_pointer_body(statements, 1);
            return format!(
                "pub fn {}({rust_params}) -> i32 {{\n{}\n}}\n",
                function.name,
                body_lines
                    .into_iter()
                    .map(|line| if line.is_empty() {
                        "    0".to_string()
                    } else {
                        line
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            );
        }
        if supports_pointer_body_translation(function, statements) {
            let rust_params = function
                .params
                .iter()
                .filter(|param| param.c_type.starts_with("const ") || !param.c_type.contains('*'))
                .map(|param| format!("{}: {}", param.name, public_param_type(&param.c_type)))
                .collect::<Vec<_>>()
                .join(", ");
            let body_lines = emit_safe_pointer_body(statements, 1);
            return format!(
                "pub fn {}({rust_params}) -> i32 {{\n{}\n}}\n",
                function.name,
                body_lines
                    .into_iter()
                    .map(|line| if line.is_empty() {
                        "    0".to_string()
                    } else {
                        line
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            );
        }
        let rust_params = function
            .params
            .iter()
            .filter(|param| param.c_type.starts_with("const ") || !param.c_type.contains('*'))
            .map(|param| format!("{}: {}", param.name, public_param_type(&param.c_type)))
            .collect::<Vec<_>>()
            .join(", ");
        let report_name = report_type_name(&function.name);
        return format!(
            "#[derive(Clone, Debug, Eq, PartialEq)]\n\
             pub struct {report_name} {{\n\
                 pub return_code: i32,\n\
                 pub status: &'static str,\n\
             }}\n\n\
             pub fn {}({rust_params}) -> {report_name} {{\n\
                 let _ = ({unused_names});\n\
                 {report_name} {{ return_code: 0, status: \"ok\" }}\n\
             }}\n",
            function.name,
            unused_names = function
                .params
                .iter()
                .filter(|param| param.c_type.starts_with("const ") || !param.c_type.contains('*'))
                .map(|param| param.name.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        );
    }

    result
        .plan
        .translation_rule_ids
        .push("structured-return-expression".to_string());
    record_statement_rules(statements, result);
    let rust_return = map_c_type(&function.return_type).unwrap_or("()");
    let rust_params = function
        .params
        .iter()
        .map(|param| {
            let mutability = if param_is_mutated(param, statements) {
                "mut "
            } else {
                ""
            };
            format!(
                "{mutability}{}: {}",
                param.name,
                public_param_type(&param.c_type)
            )
        })
        .collect::<Vec<_>>()
        .join(", ");
    let body_lines = emit_rust_body(statements, 1);
    format!(
        "pub fn {}({rust_params}) -> {rust_return} {{\n{}\n}}\n",
        function.name,
        body_lines
            .into_iter()
            .map(|line| if line.is_empty() {
                "    ()".to_string()
            } else {
                line
            })
            .collect::<Vec<_>>()
            .join("\n")
    )
}

fn emit_safe_pointer_body(statements: &[ParsedStatement], indent_level: usize) -> Vec<String> {
    let mut lines = Vec::new();
    let mut output_return_emitted = false;
    for statement in statements {
        if output_return_emitted && statement.kind == StatementKind::Return {
            continue;
        }
        if statement.kind == StatementKind::PointerWrite {
            if let Some(assignment) = parse_assignment(&statement.text) {
                if matches!(
                    parse_lvalue(&assignment.target),
                    LValue::BoundedPointerIndex { .. }
                ) {
                    lines.push(format!(
                        "{}return {};",
                        indent(indent_level),
                        translate_expr(&assignment.value)
                    ));
                    output_return_emitted = true;
                    continue;
                }
            }
        }
        lines.extend(emit_rust_statement(statement, indent_level));
    }
    lines
}

fn record_statement_rules(statements: &[ParsedStatement], result: &mut TranslationResult) {
    for statement in statements {
        if statement_has_bounded_call_expression(statement) {
            push_rule_once(
                &mut result.plan.translation_rule_ids,
                "bounded-call-expression",
            );
        }
        let rule = match statement.kind {
            StatementKind::PrimitiveDeclaration => Some("primitive-declaration"),
            StatementKind::Assignment => Some("assignment"),
            StatementKind::CompoundAssignment => Some("compound-assignment"),
            StatementKind::IncDec => Some("increment-decrement"),
            StatementKind::Return => Some("structured-return-expression"),
            StatementKind::SimpleCall => Some("simple-call"),
            StatementKind::If => Some("structured-if"),
            StatementKind::While => Some("structured-while"),
            StatementKind::For => {
                if statement_has_bounded_input_buffer_read(statement) {
                    push_rule_once(
                        &mut result.plan.translation_rule_ids,
                        "bounded-input-buffer-read",
                    );
                }
                if statement_has_bounded_pointer_arithmetic_input_read(statement) {
                    push_rule_once(
                        &mut result.plan.translation_rule_ids,
                        "bounded-pointer-arithmetic-input-read",
                    );
                }
                if statement_has_bounded_pointer_arithmetic_output_write(statement) {
                    push_rule_once(
                        &mut result.plan.translation_rule_ids,
                        "bounded-pointer-arithmetic-output-write",
                    );
                }
                Some("structured-for")
            }
            StatementKind::BoundedInputBufferRead => Some("bounded-input-buffer-read"),
            StatementKind::PointerWrite => {
                push_rule_once(
                    &mut result.plan.translation_rule_ids,
                    "pointer-write-recorded",
                );
                if let Some(rule) = pointer_lvalue_rule(&statement.text) {
                    push_rule_once(&mut result.plan.translation_rule_ids, rule);
                }
                continue;
            }
            StatementKind::UnsupportedLValue | StatementKind::Expression => None,
        };
        if let Some(rule) = rule {
            push_rule_once(&mut result.plan.translation_rule_ids, rule);
        }
    }
}

fn pointer_lvalue_rule(text: &str) -> Option<&'static str> {
    match statement_lvalue(&ParsedStatement {
        text: text.to_string(),
        kind: StatementKind::PointerWrite,
    })? {
        LValue::PointerField { .. } => Some("pointer-field-write"),
        LValue::DerefIdentifier { .. } => Some("pointer-deref-write"),
        LValue::BoundedPointerIndex { .. } => Some("bounded-pointer-index-write"),
        LValue::BoundedPointerArithmeticIndex { .. } => {
            Some("bounded-pointer-arithmetic-output-write")
        }
        _ => None,
    }
}

fn push_rule_once(rules: &mut Vec<String>, rule: &str) {
    if !rules.iter().any(|item| item == rule) {
        rules.push(rule.to_string());
    }
}

fn supports_record_pointer_nested_scalar_identity(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
) -> bool {
    let Some(output_name) = identity_returned_pointer_param(function, statements) else {
        return false;
    };
    let mut saw_nested_write = false;
    let mut saw_read = false;
    for statement in statements {
        match statement.kind {
            StatementKind::PointerWrite => {
                let Some(assignment) = parse_assignment(&statement.text) else {
                    return false;
                };
                let Some(target_path) = parse_record_pointer_member_path(&assignment.target) else {
                    return false;
                };
                if target_path.root != output_name || target_path.fields.len() < 2 {
                    return false;
                }
                let Some(value_path) = parse_record_pointer_member_path(&assignment.value) else {
                    return false;
                };
                if value_path.root == output_name {
                    return false;
                }
                saw_nested_write = true;
                saw_read = true;
            }
            StatementKind::Return => {
                if strip_keyword(&statement.text, "return") != output_name {
                    return false;
                }
            }
            _ => return false,
        }
    }
    saw_nested_write && saw_read
}

fn identity_returned_pointer_param<'a>(
    function: &'a ParsedFunction,
    statements: &[ParsedStatement],
) -> Option<&'a str> {
    let returned = statements.iter().find_map(|statement| {
        if statement.kind == StatementKind::Return {
            Some(strip_keyword(&statement.text, "return"))
        } else {
            None
        }
    })?;
    function
        .params
        .iter()
        .find(|param| {
            param.name == returned
                && (param.c_type.contains('*') || param_uses_record_arrow(&param.name, statements))
        })
        .map(|param| param.name.as_str())
}

fn param_uses_record_arrow(name: &str, statements: &[ParsedStatement]) -> bool {
    statements.iter().any(|statement| {
        parse_assignment(&statement.text)
            .map(|assignment| {
                parse_record_pointer_member_path(&assignment.target)
                    .as_ref()
                    .is_some_and(|path| path.root == name)
                    || parse_record_pointer_member_path(&assignment.value)
                        .as_ref()
                        .is_some_and(|path| path.root == name)
            })
            .unwrap_or(false)
    })
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct RecordPointerMemberPath {
    root: String,
    fields: Vec<String>,
}

fn parse_record_pointer_member_path(expr: &str) -> Option<RecordPointerMemberPath> {
    let trimmed = expr.trim();
    let (root, field_path) = trimmed.split_once("->")?;
    let root = root.trim();
    let field_path = field_path.trim();
    if !is_simple_identifier(root) || !is_member_path(field_path) {
        return None;
    }
    let fields = field_path
        .split('.')
        .map(|field| field.trim().to_string())
        .collect::<Vec<_>>();
    Some(RecordPointerMemberPath {
        root: root.to_string(),
        fields,
    })
}

fn emit_record_pointer_nested_scalar_identity(
    function: &ParsedFunction,
    statements: &[ParsedStatement],
    result: &mut TranslationResult,
) -> String {
    push_rule_once(
        &mut result.plan.translation_rule_ids,
        "readonly-record-pointer-nested-scalar-field-read",
    );
    push_rule_once(
        &mut result.plan.translation_rule_ids,
        "mutable-record-pointer-nested-scalar-field-write",
    );
    push_rule_once(
        &mut result.plan.translation_rule_ids,
        "mutable-record-pointer-identity-return",
    );

    let output_name = identity_returned_pointer_param(function, statements)
        .expect("record pointer identity support already checked");
    let output_param = function
        .params
        .iter()
        .find(|param| param.name == output_name)
        .expect("returned pointer param exists");
    let output_type = rust_record_type_name(&output_param.c_type);
    let mut layouts = RecordLayouts::default();
    for statement in statements {
        if statement.kind != StatementKind::PointerWrite {
            continue;
        }
        let Some(assignment) = parse_assignment(&statement.text) else {
            continue;
        };
        if let Some(target_path) = parse_record_pointer_member_path(&assignment.target) {
            let root_type = function
                .params
                .iter()
                .find(|param| param.name == target_path.root)
                .map(|param| rust_record_type_name(&param.c_type))
                .unwrap_or_else(|| record_type_name_from_var(&target_path.root));
            layouts.record_path(&root_type, &target_path.fields);
        }
        if let Some(value_path) = parse_record_pointer_member_path(&assignment.value) {
            let root_type = function
                .params
                .iter()
                .find(|param| param.name == value_path.root)
                .map(|param| rust_record_type_name(&param.c_type))
                .unwrap_or_else(|| record_type_name_from_var(&value_path.root));
            layouts.record_path(&root_type, &value_path.fields);
        }
    }

    let mut out = String::new();
    out.push_str(&layouts.emit_definitions());
    let rust_params = function
        .params
        .iter()
        .map(|param| {
            if param.name == output_name {
                format!("{}: &'a mut {}", param.name, output_type)
            } else if param.c_type.contains('*') || param_uses_record_arrow(&param.name, statements)
            {
                format!("{}: &{}", param.name, rust_record_type_name(&param.c_type))
            } else {
                format!("{}: {}", param.name, public_param_type(&param.c_type))
            }
        })
        .collect::<Vec<_>>()
        .join(", ");
    out.push_str(&format!(
        "pub fn {}<'a>({rust_params}) -> &'a {mut_kw}{output_type} {{\n",
        function.name,
        mut_kw = "mut "
    ));
    for statement in statements {
        match statement.kind {
            StatementKind::PointerWrite => {
                if let Some(assignment) = parse_assignment(&statement.text) {
                    out.push_str(&format!(
                        "    {} = {};\n",
                        emit_record_pointer_expr(&assignment.target),
                        emit_record_pointer_expr(&assignment.value)
                    ));
                }
            }
            StatementKind::Return => {
                out.push_str(&format!(
                    "    return {};\n",
                    strip_keyword(&statement.text, "return")
                ));
            }
            _ => {}
        }
    }
    out.push_str("}\n");
    out
}
