#[cfg(feature = "typed-ir")]
fn expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, false)
}

#[cfg(feature = "typed-ir")]
fn value_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, true)
}

#[cfg(feature = "typed-ir")]
fn condition_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, true)
}

#[cfg(feature = "typed-ir")]
fn while_condition_expr_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(expr, "kind").as_deref() == Some("UnaryOperator")
        && string_field(expr, "opcode").as_deref() == Some("--")
        && expr.get("isPostfix").and_then(Value::as_bool) == Some(false)
    {
        let skeleton = inc_dec_expr_skeleton_from_ast(expr, true, true)?;
        let ClangExprSkeleton::IncDec {
            target,
            op: ClangIncDecOperator::Dec,
            prefix: true,
            ty,
        } = &skeleton
        else {
            return Ok(skeleton);
        };
        let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = target.as_ref() else {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: "while prefix decrement condition must target a simple integer variable"
                    .to_string(),
            });
        };
        if !matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
            || !compound_assignment_types_match(target_ty, ty)
        {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: format!(
                    "while prefix decrement target type {} is unsupported",
                    target_ty.canonical
                ),
            });
        }
        return Ok(skeleton);
    }
    condition_expr_skeleton_from_ast(expr)
}
