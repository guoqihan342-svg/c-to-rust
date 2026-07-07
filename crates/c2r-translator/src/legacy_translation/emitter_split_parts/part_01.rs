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
