#[cfg(feature = "typed-ir")]
fn implicit_cast_expr_skeleton_from_ast(
    expr: &Value,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let cast_kind = string_field(expr, "castKind");
    let operand_ast = inner(expr).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_clang_expr".to_string(),
        message: "ImplicitCastExpr is missing operand".to_string(),
    })?;
    if cast_kind.as_deref() == Some("IntegralToBoolean") {
        let operand = expr_skeleton_from_ast_with_options(operand_ast, true)?;
        return integral_to_boolean_skeleton_from_cast(expr, &operand, "ImplicitCastExpr");
    }
    let preserve_integral_conversion =
        (preserve_integral_casts || cast_kind.as_deref() == Some("NoOp"))
            && is_integral_conversion_cast_expr(expr);
    let operand = expr_skeleton_from_ast_with_options(
        operand_ast,
        preserve_integral_casts || preserve_integral_conversion,
    )?;
    if cast_kind.as_deref() == Some("FunctionToPointerDecay") {
        return Ok(ClangExprSkeleton::FunctionToPointerDecay {
            target: expr_type(expr)?,
            expr: Box::new(operand),
        });
    }
    if cast_kind.as_deref() == Some("NullToPointer") {
        return null_pointer_skeleton_from_cast(expr, &operand, "ImplicitCastExpr");
    }
    if cast_kind.as_deref() == Some("BitCast")
        && matches!(operand, ClangExprSkeleton::NullPtr { .. })
    {
        let target = expr_type(expr)?;
        if matches!(target.kind, ClangTypeKind::Pointer { .. }) {
            return Ok(ClangExprSkeleton::NullPtr { ty: target });
        }
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "null pointer BitCast target {} is not a pointer",
                target.spelled
            ),
        });
    }
    if cast_kind.as_deref() == Some("ArrayToPointerDecay") {
        return Ok(ClangExprSkeleton::ArrayToPointerDecay {
            target: expr_type(expr)?,
            expr: Box::new(operand),
        });
    }
    if preserve_integral_conversion {
        return Ok(ClangExprSkeleton::Cast {
            target: expr_type(expr)?,
            expr: Box::new(operand),
            implicit: true,
        });
    }
    if preserve_integral_casts && is_integer_lvalue_to_rvalue_cast_expr(expr) {
        return Ok(ClangExprSkeleton::LValueToRValue {
            target: expr_type(expr)?,
            expr: Box::new(operand),
        });
    }
    match cast_kind.as_deref() {
        Some("LValueToRValue" | "NoOp") => Ok(operand),
        Some(cast_kind) => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "castKind {cast_kind} is outside the current clang lowering skeleton"
            ),
        }),
        None => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: "missing castKind is outside the current clang lowering skeleton".to_string(),
        }),
    }
}
