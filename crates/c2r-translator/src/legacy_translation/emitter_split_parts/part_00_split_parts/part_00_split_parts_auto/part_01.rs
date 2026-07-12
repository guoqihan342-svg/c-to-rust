
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
