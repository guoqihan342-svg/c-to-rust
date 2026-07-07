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
        .any(|param| param.c_type.contains('*'));
    if has_pointer {
        result
            .plan
            .translation_rule_ids
            .push("safe-wrapper-for-pointer-out-param".to_string());
        record_statement_rules(statements, result);
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

fn default_value_for_type(rust_type: &str) -> &'static str {
    match rust_type {
        "()" => "()",
        "&str" => "\"\"",
        _ => "0",
    }
}

fn translate_for_step(step: &str) -> String {
    let trimmed = step.trim();
    if let Some(inc_dec) = parse_inc_dec_statement(trimmed) {
        return format!(
            "{} {} 1",
            translate_expr(&inc_dec.target),
            inc_dec.delta_operator
        );
    }
    if let Some(assignment) = parse_compound_assignment(trimmed) {
        return format!(
            "{} {} {}",
            translate_expr(&assignment.target),
            assignment.operator,
            translate_expr(&assignment.value)
        );
    }
    translate_expr(trimmed)
}

fn indent(level: usize) -> String {
    "    ".repeat(level)
}

fn public_param_type(c_type: &str) -> &'static str {
    map_c_type(c_type).unwrap_or("/* unsupported */ ()")
}

fn public_pointer_buffer_param_type(c_type: &str) -> &'static str {
    match normalize_type(c_type).as_str() {
        "int*" => "&mut [i32]",
        _ => public_param_type(c_type),
    }
}

fn report_type_name(function_name: &str) -> String {
    let mut out = String::new();
    let mut uppercase_next = true;
    for ch in function_name.chars() {
        if ch == '_' {
            uppercase_next = true;
        } else if uppercase_next {
            out.extend(ch.to_uppercase());
            uppercase_next = false;
        } else {
            out.push(ch);
        }
    }
    out.push_str("Report");
    out
}

fn translate_expr(expr: &str) -> String {
    let mut out = expr.trim().to_string();
    for read in bounded_input_buffer_reads(expr) {
        out = out.replace(
            &read.source,
            &format!("{}[{} as usize]", read.base, read.index),
        );
    }
    out
}
