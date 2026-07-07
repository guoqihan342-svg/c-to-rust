fn emit_binary_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Add => Ok("+"),
        IrBinOp::Sub => Ok("-"),
        IrBinOp::Mul => Ok("*"),
        IrBinOp::Div => Ok("/"),
        IrBinOp::Mod => Ok("%"),
        IrBinOp::BitAnd => Ok("&"),
        IrBinOp::BitOr => Ok("|"),
        IrBinOp::BitXor => Ok("^"),
        IrBinOp::Shl => Ok("<<"),
        IrBinOp::Shr => Ok(">>"),
        _ => Err(format!("binary op {op:?} is unsupported")),
    }
}

fn emit_binary_result_expr(
    op: &IrBinOp,
    op_token: &str,
    lhs: &str,
    rhs: &str,
    result_ty: &IrType,
) -> String {
    if let Some(method) = unsigned_wrapping_method(op, result_ty) {
        format!("{lhs}.{method}({rhs})")
    } else if let Some((method, message)) = signed_checked_method(op, result_ty) {
        format!("{lhs}.{method}({rhs}).expect(\"{message}\")")
    } else if let Some((method, message)) = checked_div_rem_method(op, result_ty) {
        format!("{lhs}.{method}({rhs}).expect(\"{message}\")")
    } else if let Some(method) = checked_shift_method(op, result_ty) {
        format!(
            "{lhs}.{method}(core::convert::TryFrom::try_from({rhs}).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\")"
        )
    } else {
        format!("({lhs} {op_token} {rhs})")
    }
}

fn unsigned_wrapping_method(op: &IrBinOp, result_ty: &IrType) -> Option<&'static str> {
    if !is_unsigned_integer_type(result_ty) {
        return None;
    }
    match op {
        IrBinOp::Add => Some("wrapping_add"),
        IrBinOp::Sub => Some("wrapping_sub"),
        IrBinOp::Mul => Some("wrapping_mul"),
        _ => None,
    }
}

fn signed_checked_method(op: &IrBinOp, result_ty: &IrType) -> Option<(&'static str, &'static str)> {
    if !is_signed_integer_type(result_ty) {
        return None;
    }
    match op {
        IrBinOp::Add => Some(("checked_add", "signed addition overflow")),
        IrBinOp::Sub => Some(("checked_sub", "signed subtraction overflow")),
        IrBinOp::Mul => Some(("checked_mul", "signed multiplication overflow")),
        _ => None,
    }
}

fn checked_div_rem_method(
    op: &IrBinOp,
    result_ty: &IrType,
) -> Option<(&'static str, &'static str)> {
    if !is_integer_type(result_ty) {
        return None;
    }
    let signed = is_signed_integer_type(result_ty);
    match (op, signed) {
        (IrBinOp::Div, true) => Some(("checked_div", "division by zero or signed overflow")),
        (IrBinOp::Div, false) => Some(("checked_div", "division by zero")),
        (IrBinOp::Mod, true) => Some(("checked_rem", "modulo by zero or signed overflow")),
        (IrBinOp::Mod, false) => Some(("checked_rem", "modulo by zero")),
        _ => None,
    }
}

fn checked_shift_method(op: &IrBinOp, result_ty: &IrType) -> Option<&'static str> {
    if !is_integer_type(result_ty) {
        return None;
    }
    match op {
        IrBinOp::Shl => Some("checked_shl"),
        IrBinOp::Shr => Some("checked_shr"),
        _ => None,
    }
}

fn emit_comparison_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Eq => Ok("=="),
        IrBinOp::Neq => Ok("!="),
        IrBinOp::Lt => Ok("<"),
        IrBinOp::Le => Ok("<="),
        IrBinOp::Gt => Ok(">"),
        IrBinOp::Ge => Ok(">="),
        _ => Err(format!("binary op {op:?} is not a comparison")),
    }
}

fn emit_negated_comparison_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Eq => Ok("!="),
        IrBinOp::Neq => Ok("=="),
        IrBinOp::Lt => Ok(">="),
        IrBinOp::Le => Ok(">"),
        IrBinOp::Gt => Ok("<="),
        IrBinOp::Ge => Ok("<"),
        _ => Err(format!("binary op {op:?} is not a comparison")),
    }
}

fn validate_binary_operand_types(
    op: &str,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
) -> Result<(), String> {
    let result_ty =
        emit_scalar_type(result_ty).map_err(|detail| format!("binary result has {detail}"))?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "binary lhs type is unsupported".to_string())?;
    let rhs_ty = expr_type(rhs).ok_or_else(|| "binary rhs type is unsupported".to_string())?;
    let lhs_ty = emit_scalar_type(lhs_ty).map_err(|detail| format!("binary lhs has {detail}"))?;
    let rhs_ty = emit_scalar_type(rhs_ty).map_err(|detail| format!("binary rhs has {detail}"))?;

    match op {
        "+" | "-" | "*" | "/" | "%" | "&" | "|" | "^" => {
            if lhs_ty == result_ty && rhs_ty == result_ty {
                Ok(())
            } else {
                Err(format!(
                    "usual arithmetic conversion requires explicit IntegralCast/IntegralPromotion before typed IR emission; binary operand types must match result type for {op}: lhs={lhs_ty}, rhs={rhs_ty}, result={result_ty}"
                ))
            }
        }
        "<<" | ">>" => {
            if lhs_ty == result_ty {
                Ok(())
            } else {
                Err(format!(
                    "shift lhs type must match result type for {op}: lhs={lhs_ty}, result={result_ty}"
                ))
            }
        }
        _ => Err(format!("binary op {op} is unsupported")),
    }
}

fn validate_binary_runtime_contract(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    policy: &EmitPolicy,
) -> Result<(), String> {
    match op {
        IrBinOp::Div if static_integer_value(rhs) == Some(0) => {
            Err("division by zero literal is unsupported".to_string())
        }
        IrBinOp::Mod if static_integer_value(rhs) == Some(0) => {
            Err("modulo by zero literal is unsupported".to_string())
        }
        IrBinOp::Shl | IrBinOp::Shr => {
            validate_shift_runtime_contract(op, lhs, rhs, result_ty, policy)
        }
        _ => Ok(()),
    }
}

fn validate_shift_runtime_contract(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    policy: &EmitPolicy,
) -> Result<(), String> {
    let width = integer_width_bits(result_ty)
        .ok_or_else(|| format!("shift result type {} is unsupported", type_label(result_ty)))?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "shift lhs type is unsupported".to_string())?;
    let lhs_width = integer_width_bits(lhs_ty)
        .ok_or_else(|| format!("shift lhs type {} is unsupported", type_label(lhs_ty)))?;
    if lhs_width != width {
        return Err(format!(
            "shift lhs width {lhs_width} does not match result width {width}"
        ));
    }
    if let Some(count) = static_integer_value(rhs) {
        if count < 0 {
            return Err(format!(
                "negative shift count literal {count} is unsupported"
            ));
        }
        if count >= i128::from(width) {
            return Err(format!(
                "shift count literal {count} must be less than width {width}"
            ));
        }
    }
    if matches!(op, IrBinOp::Shr)
        && is_signed_integer_type(result_ty)
        && policy.signed_right_shift != SignedRightShiftPolicy::ImplementationDefinedArithmetic
    {
        return Err(format!(
            "signed right shift for {} is implementation-defined without an explicit contract",
            type_label(result_ty)
        ));
    }
    Ok(())
}

fn static_integer_value(expr: &IrExpr) -> Option<i128> {
    match expr {
        IrExpr::LitInt { value, .. } => Some(i128::from(*value)),
        IrExpr::Cast { expr, .. } => static_integer_value(expr),
        IrExpr::Unary {
            op: IrUnOp::Neg,
            operand,
            ..
        } => static_integer_value(operand).and_then(i128::checked_neg),
        _ => None,
    }
}

fn integer_width_bits(ty: &IrType) -> Option<u16> {
    match ty.kind {
        IrTypeKind::Integer { width, .. } => Some(width),
        _ => None,
    }
}
