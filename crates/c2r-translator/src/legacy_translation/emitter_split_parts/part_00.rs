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

#[derive(Default)]
struct RecordLayouts {
    records: Vec<RecordLayout>,
}

#[derive(Clone)]
struct RecordLayout {
    name: String,
    fields: Vec<RecordField>,
}

#[derive(Clone)]
struct RecordField {
    name: String,
    ty: RecordFieldType,
}

#[derive(Clone, Eq, PartialEq)]
enum RecordFieldType {
    Scalar(&'static str),
    Record(String),
}

impl RecordLayouts {
    fn record_path(&mut self, root_type: &str, fields: &[String]) {
        if fields.is_empty() {
            return;
        }
        let mut current_record = root_type.to_string();
        for (index, field) in fields.iter().enumerate() {
            let is_leaf = index + 1 == fields.len();
            if is_leaf {
                let ty = RecordFieldType::Scalar(infer_scalar_field_type(field));
                self.insert_field(&current_record, field, ty);
            } else {
                let nested_record = format!("{current_record}{}", pascal_case(field));
                self.insert_field(
                    &current_record,
                    field,
                    RecordFieldType::Record(nested_record.clone()),
                );
                current_record = nested_record;
            }
        }
    }

    fn insert_field(&mut self, record: &str, field: &str, ty: RecordFieldType) {
        let layout = self.ensure_record(record);
        if let Some(existing) = layout.fields.iter_mut().find(|item| item.name == field) {
            existing.ty = merge_field_type(&existing.ty, &ty);
            return;
        }
        layout.fields.push(RecordField {
            name: field.to_string(),
            ty,
        });
    }

    fn ensure_record(&mut self, name: &str) -> &mut RecordLayout {
        if let Some(index) = self.records.iter().position(|record| record.name == name) {
            return &mut self.records[index];
        }
        self.records.push(RecordLayout {
            name: name.to_string(),
            fields: Vec::new(),
        });
        self.records
            .last_mut()
            .expect("record was just inserted")
    }

    fn emit_definitions(&self) -> String {
        let mut emitted = String::new();
        let mut records = self.records.clone();
        records.sort_by_key(|record| record_depth(&record.name));
        records.reverse();
        for record in records {
            emitted.push_str("#[derive(Clone, Copy, Debug, Eq, PartialEq)]\n");
            emitted.push_str(&format!("pub struct {} {{\n", record.name));
            for field in record.fields {
                let ty = match field.ty {
                    RecordFieldType::Scalar(ty) => ty.to_string(),
                    RecordFieldType::Record(name) => name,
                };
                emitted.push_str(&format!("    pub {}: {},\n", field.name, ty));
            }
            emitted.push_str("}\n\n");
        }
        emitted
    }
}

fn merge_field_type(existing: &RecordFieldType, incoming: &RecordFieldType) -> RecordFieldType {
    if existing == incoming {
        existing.clone()
    } else if matches!(existing, RecordFieldType::Scalar("usize"))
        || matches!(incoming, RecordFieldType::Scalar("usize"))
    {
        RecordFieldType::Scalar("usize")
    } else {
        incoming.clone()
    }
}

fn record_depth(name: &str) -> usize {
    name.chars().filter(|ch| ch.is_ascii_uppercase()).count()
}

fn infer_scalar_field_type(field: &str) -> &'static str {
    if field.ends_with("len") || field.ends_with("size") {
        "usize"
    } else {
        "u32"
    }
}

fn rust_record_type_name(c_type: &str) -> String {
    let normalized = normalize_type(c_type)
        .trim_start_matches("const ")
        .trim_end_matches('*')
        .trim()
        .trim_start_matches("struct ")
        .trim_end_matches("_t")
        .to_string();
    pascal_case(&normalized)
}

fn record_type_name_from_var(name: &str) -> String {
    pascal_case(name)
}

fn pascal_case(value: &str) -> String {
    let mut out = String::new();
    let mut uppercase_next = true;
    for ch in value.chars() {
        if ch == '_' || ch == '-' || ch == ' ' {
            uppercase_next = true;
        } else if uppercase_next {
            out.extend(ch.to_uppercase());
            uppercase_next = false;
        } else {
            out.push(ch);
        }
    }
    out
}

fn emit_record_pointer_expr(expr: &str) -> String {
    if let Some(path) = parse_record_pointer_member_path(expr) {
        let mut out = path.root;
        for field in path.fields {
            out.push('.');
            out.push_str(&field);
        }
        out
    } else {
        translate_expr(expr)
    }
}

fn emit_rust_body(statements: &[ParsedStatement], indent_level: usize) -> Vec<String> {
    if statements.is_empty() {
        return vec![format!("{}()", indent(indent_level))];
    }
    statements
        .iter()
        .flat_map(|statement| emit_rust_statement(statement, indent_level))
        .collect()
}

fn emit_rust_statement(statement: &ParsedStatement, indent_level: usize) -> Vec<String> {
    let prefix = indent(indent_level);
    match statement.kind {
        StatementKind::PrimitiveDeclaration => parse_declaration(&statement.text)
            .map(|declaration| {
                let rust_type = map_c_type(&declaration.c_type).unwrap_or("()");
                let initializer = declaration
                    .initializer
                    .as_deref()
                    .map(translate_expr)
                    .unwrap_or_else(|| default_value_for_type(rust_type).to_string());
                vec![format!(
                    "{prefix}let mut {}: {rust_type} = {initializer};",
                    declaration.name
                )]
            })
            .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))]),
        StatementKind::Assignment | StatementKind::PointerWrite => {
            parse_assignment(&statement.text)
                .map(|assignment| {
                    vec![format!(
                        "{prefix}{} = {};",
                        translate_expr(&assignment.target),
                        translate_expr(&assignment.value)
                    )]
                })
                .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))])
        }
        StatementKind::BoundedInputBufferRead => {
            vec![format!("{prefix}{};", translate_expr(&statement.text))]
        }
        StatementKind::CompoundAssignment => parse_compound_assignment(&statement.text)
            .map(|assignment| {
                vec![format!(
                    "{prefix}{} {} {};",
                    translate_expr(&assignment.target),
                    assignment.operator,
                    translate_expr(&assignment.value)
                )]
            })
            .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))]),
        StatementKind::IncDec => parse_inc_dec_statement(&statement.text)
            .map(|inc_dec| {
                vec![format!(
                    "{prefix}{} {} 1;",
                    translate_expr(&inc_dec.target),
                    inc_dec.delta_operator
                )]
            })
            .unwrap_or_else(|| vec![format!("{prefix}{};", translate_expr(&statement.text))]),
        StatementKind::Return => vec![format!(
            "{prefix}return {};",
            translate_expr(strip_keyword(&statement.text, "return"))
        )],
        StatementKind::SimpleCall
        | StatementKind::UnsupportedLValue
        | StatementKind::Expression => {
            vec![format!("{prefix}{};", translate_expr(&statement.text))]
        }
        StatementKind::If => {
            emit_if_statement(&statement.text, indent_level).unwrap_or_else(|| {
                vec![format!(
                    "{prefix}/* unsupported if lowering: {} */",
                    statement.text
                )]
            })
        }
        StatementKind::While => {
            emit_while_statement(&statement.text, indent_level).unwrap_or_else(|| {
                vec![format!(
                    "{prefix}/* unsupported while lowering: {} */",
                    statement.text
                )]
            })
        }
        StatementKind::For => {
            emit_for_statement(&statement.text, indent_level).unwrap_or_else(|| {
                vec![format!(
                    "{prefix}/* unsupported for lowering: {} */",
                    statement.text
                )]
            })
        }
    }
}

fn emit_if_statement(text: &str, indent_level: usize) -> Option<Vec<String>> {
    let (condition, then_body, else_body) = parse_if_parts(text)?;
    let prefix = indent(indent_level);
    let mut lines = vec![format!("{prefix}if {} {{", translate_expr(&condition))];
    lines.extend(emit_rust_body(
        &parse_statements(&then_body),
        indent_level + 1,
    ));
    if let Some(else_body) = else_body {
        lines.push(format!("{prefix}}} else {{"));
        lines.extend(emit_rust_body(
            &parse_statements(&else_body),
            indent_level + 1,
        ));
    }
    lines.push(format!("{prefix}}}"));
    Some(lines)
}

fn emit_while_statement(text: &str, indent_level: usize) -> Option<Vec<String>> {
    let (condition, body) = parse_loop_parts(text, "while")?;
    let prefix = indent(indent_level);
    let mut lines = vec![format!("{prefix}while {} {{", translate_expr(&condition))];
    lines.extend(emit_rust_body(&parse_statements(&body), indent_level + 1));
    lines.push(format!("{prefix}}}"));
    Some(lines)
}

fn emit_for_statement(text: &str, indent_level: usize) -> Option<Vec<String>> {
    let (init, condition, step, body) = parse_for_parts(text)?;
    let prefix = indent(indent_level);
    let mut lines = vec![format!("{prefix}{{")];
    if !init.trim().is_empty() {
        let init_statement = ParsedStatement {
            kind: classify_statement(&init),
            text: init,
        };
        lines.extend(emit_rust_statement(&init_statement, indent_level + 1));
    }
    let loop_condition = if condition.trim().is_empty() {
        "true".to_string()
    } else {
        translate_expr(&condition)
    };
    lines.push(format!(
        "{}while {loop_condition} {{",
        indent(indent_level + 1)
    ));
    lines.extend(emit_rust_body(&parse_statements(&body), indent_level + 2));
    if !step.trim().is_empty() {
        lines.push(format!(
            "{}{};",
            indent(indent_level + 2),
            translate_for_step(&step)
        ));
    }
    lines.push(format!("{}}}", indent(indent_level + 1)));
    lines.push(format!("{prefix}}}"));
    Some(lines)
}

fn parse_if_parts(text: &str) -> Option<(String, String, Option<String>)> {
    let open = text.find('(')?;
    let close = find_matching_byte(text, open, b'(', b')')?;
    let condition = text[open + 1..close].trim().to_string();
    let then_start = skip_whitespace(text, close + 1);
    let then_end = scan_control_body_end(text, then_start)?;
    let then_body = extract_control_body(text, then_start, then_end)?;
    let after_then = skip_whitespace(text, then_end);
    let else_body = if starts_with_token_at(text, after_then, "else") {
        let else_start = skip_whitespace(text, after_then + "else".len());
        let else_end = scan_control_body_end(text, else_start)?;
        Some(extract_control_body(text, else_start, else_end)?)
    } else {
        None
    };
    Some((condition, then_body, else_body))
}

fn parse_loop_parts(text: &str, keyword: &str) -> Option<(String, String)> {
    if !starts_with_token_at(text, 0, keyword) {
        return None;
    }
    let open = text.find('(')?;
    let close = find_matching_byte(text, open, b'(', b')')?;
    let condition = text[open + 1..close].trim().to_string();
    let body_start = skip_whitespace(text, close + 1);
    let body_end = scan_control_body_end(text, body_start)?;
    Some((condition, extract_control_body(text, body_start, body_end)?))
}

fn parse_for_parts(text: &str) -> Option<(String, String, String, String)> {
    let open = text.find('(')?;
    let close = find_matching_byte(text, open, b'(', b')')?;
    let header = &text[open + 1..close];
    let parts = split_top_level(header, b';');
    if parts.len() != 3 {
        return None;
    }
    let body_start = skip_whitespace(text, close + 1);
    let body_end = scan_control_body_end(text, body_start)?;
    Some((
        parts[0].trim().to_string(),
        parts[1].trim().to_string(),
        parts[2].trim().to_string(),
        extract_control_body(text, body_start, body_end)?,
    ))
}

fn extract_control_body(text: &str, start: usize, end: usize) -> Option<String> {
    if text.as_bytes().get(start) == Some(&b'{') {
        let close = end.checked_sub(1)?;
        return Some(text[start + 1..close].trim().to_string());
    }
    Some(
        text[start..end]
            .trim()
            .trim_end_matches(';')
            .trim()
            .to_string(),
    )
}

fn split_top_level(text: &str, delimiter: u8) -> Vec<String> {
    let mut parts = Vec::new();
    let mut start = 0usize;
    let mut paren_depth = 0usize;
    for (index, byte) in text.as_bytes().iter().enumerate() {
        match *byte {
            b'(' => paren_depth += 1,
            b')' => paren_depth = paren_depth.saturating_sub(1),
            value if value == delimiter && paren_depth == 0 => {
                parts.push(text[start..index].to_string());
                start = index + 1;
            }
            _ => {}
        }
    }
    parts.push(text[start..].to_string());
    parts
}

fn strip_keyword<'a>(text: &'a str, keyword: &str) -> &'a str {
    text.trim()
        .strip_prefix(keyword)
        .unwrap_or(text)
        .trim()
        .trim_end_matches(';')
        .trim()
}
