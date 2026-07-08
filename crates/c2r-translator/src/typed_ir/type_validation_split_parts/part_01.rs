fn validate_comparison_condition_types(
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    op: &str,
) -> Result<(), String> {
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "comparison result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    validate_comparison_cast_operand(lhs, "lhs")?;
    validate_comparison_cast_operand(rhs, "rhs")?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "comparison lhs type is unsupported".to_string())?;
    let rhs_ty = expr_type(rhs).ok_or_else(|| "comparison rhs type is unsupported".to_string())?;
    let lhs_ty =
        emit_scalar_type(lhs_ty).map_err(|detail| format!("comparison lhs has {detail}"))?;
    let rhs_ty =
        emit_scalar_type(rhs_ty).map_err(|detail| format!("comparison rhs has {detail}"))?;
    if lhs_ty == rhs_ty {
        Ok(())
    } else {
        Err(format!(
            "comparison operand types must match for {op}: lhs={lhs_ty}, rhs={rhs_ty}"
        ))
    }
}

fn validate_comparison_cast_operand(expr: &IrExpr, side: &str) -> Result<(), String> {
    let IrExpr::Cast { target, expr, .. } = expr else {
        return Ok(());
    };
    if !is_integer_type(target) {
        return Err(format!(
            "comparison {side} cast target {} is unsupported",
            type_label(target)
        ));
    }
    let source_type = expr_type(expr)
        .ok_or_else(|| format!("comparison {side} cast source type is unsupported"))?;
    if !is_integer_type(source_type) {
        return Err(format!(
            "comparison {side} cast source {} is unsupported",
            type_label(source_type)
        ));
    }
    emit_scalar_type(target)
        .map_err(|detail| format!("comparison {side} cast target has {detail}"))?;
    emit_scalar_type(source_type)
        .map_err(|detail| format!("comparison {side} cast source has {detail}"))?;
    Ok(())
}

fn ends_with_return_value(body: &[IrStmt]) -> bool {
    match body.last() {
        Some(IrStmt::Return { value: Some(_), .. }) => true,
        Some(IrStmt::If {
            then_body,
            else_body,
            ..
        }) => ends_with_return_value(then_body) && ends_with_return_value(else_body),
        _ => false,
    }
}

fn emit_integer_literal_suffix(ty: &IrType) -> Result<String, String> {
    if is_size_t_type(ty) {
        return Ok("usize".to_string());
    }
    match &ty.kind {
        IrTypeKind::Integer { signed, width } => match (*signed, *width) {
            (true, 8) => Ok("i8".to_string()),
            (true, 16) => Ok("i16".to_string()),
            (true, 32) => Ok("i32".to_string()),
            (true, 64) => Ok("i64".to_string()),
            (false, 8) => Ok("u8".to_string()),
            (false, 16) => Ok("u16".to_string()),
            (false, 32) => Ok("u32".to_string()),
            (false, 64) => Ok("u64".to_string()),
            _ => Err(format!(
                "literal integer type {} is unsupported",
                type_label(ty)
            )),
        },
        _ => Err(format!("literal type {} is not an integer", type_label(ty))),
    }
}

fn emit_integer_literal(value: u64, ty: &IrType) -> Result<String, String> {
    validate_integer_literal_range(value, ty)?;
    if is_c_bool_type(ty) {
        return Ok(if value == 0 {
            "false".to_string()
        } else {
            "true".to_string()
        });
    }
    let suffix = emit_integer_literal_suffix(ty)?;
    Ok(format!("{value}{suffix}"))
}

fn zero_literal_for_type(ty: &IrType) -> Result<String, String> {
    emit_integer_literal(0, ty)
}

fn validate_integer_literal_range(value: u64, ty: &IrType) -> Result<(), String> {
    let label = emit_scalar_type(ty)?;
    let max = match &ty.kind {
        IrTypeKind::Integer { signed, width } => {
            if is_size_t_type(ty) {
                usize::MAX as u64
            } else if *signed {
                match width {
                    8 => i8::MAX as u64,
                    16 => i16::MAX as u64,
                    32 => i32::MAX as u64,
                    64 => i64::MAX as u64,
                    _ => return Err(format!("literal integer type {label} is unsupported")),
                }
            } else {
                match width {
                    8 => u8::MAX as u64,
                    16 => u16::MAX as u64,
                    32 => u32::MAX as u64,
                    64 => u64::MAX,
                    _ => return Err(format!("literal integer type {label} is unsupported")),
                }
            }
        }
        _ => return Err(format!("literal type {label} is not an integer")),
    };

    if value <= max {
        Ok(())
    } else {
        Err(format!("literal value {value} does not fit type {label}"))
    }
}
