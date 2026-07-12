#[cfg(feature = "typed-ir")]
fn memcpy_source_arg_skeleton_from_ast(
    arg: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(arg, "kind").as_deref() != Some("ImplicitCastExpr")
        || string_field(arg, "castKind").as_deref() != Some("BitCast")
    {
        return expr_skeleton_from_ast_with_options(arg, true);
    }

    let target = expr_type(arg)?;
    if !clang_type_is_const_void_pointer(&target) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "memcpy source BitCast target {} is not const void *",
                target.spelled
            ),
        });
    }

    let operand = inner(arg).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_clang_expr".to_string(),
        message: "ImplicitCastExpr BitCast is missing operand".to_string(),
    })?;
    let operand = expr_skeleton_from_ast_with_options(operand, true)?;
    match &operand {
        ClangExprSkeleton::DeclRef { ty, .. }
            if clang_type_is_readonly_unsigned_8_bit_pointer(ty) =>
        {
            Ok(operand)
        }
        ClangExprSkeleton::ArrayToPointerDecay { target, expr } => {
            if let Some(reason) = clang_memcpy_source_array_decay_rejection_reason(target, expr) {
                Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason,
                })
            } else {
                Ok(operand)
            }
        }
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "memcpy source BitCast operand {} is not readonly unsigned 8-bit pointer",
                ty.spelled
            ),
        }),
        ClangExprSkeleton::Unsupported { node, reason } => Ok(ClangExprSkeleton::Unsupported {
            node: node.clone(),
            reason: reason.clone(),
        }),
        _ => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: "memcpy source BitCast operand must be a direct pointer parameter".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_void_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee) && matches!(&pointee.kind, ClangTypeKind::Void)
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_const_void_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if clang_type_is_const(pointee) && matches!(&pointee.kind, ClangTypeKind::Void)
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_unsigned_8_bit_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { signed: false, width: 8 })
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_readonly_unsigned_8_bit_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { signed: false, width: 8 })
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_readonly_8_bit_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { width: 8, .. })
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_const_char_pointer_spelling(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        (ty.spelled.trim(), ty.canonical.trim(),),
        ("const char *", _) | (_, "const char *")
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_size_t_spelling(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        (ty.spelled.trim(), ty.canonical.trim()),
        ("size_t", _)
            | (_, "size_t")
            | ("__size_t", _)
            | (_, "__size_t")
            | ("unsigned long", _)
            | (_, "unsigned long")
            | ("unsigned long long", _)
            | (_, "unsigned long long")
    )
}

#[cfg(feature = "typed-ir")]
fn direct_call_callee_name(callee: &Value) -> Result<String, String> {
    match string_field(callee, "kind").as_deref() {
        Some("ImplicitCastExpr") => {
            match string_field(callee, "castKind").as_deref() {
                Some("FunctionToPointerDecay") | Some("NoOp") => {}
                Some(cast_kind) => {
                    return Err(format!(
                        "callee castKind {cast_kind} is not a direct function identifier"
                    ));
                }
                None => {
                    return Err(
                        "callee cast without castKind is not a direct function identifier"
                            .to_string(),
                    );
                }
            }
            let operand = inner(callee).first().ok_or_else(|| {
                "callee cast without operand is not a direct function identifier".to_string()
            })?;
            direct_call_callee_name(operand)
        }
        Some("ParenExpr") => {
            let operand = inner(callee).first().ok_or_else(|| {
                "parenthesized callee without operand is not a direct function identifier"
                    .to_string()
            })?;
            direct_call_callee_name(operand)
        }
        Some("DeclRefExpr") => {
            let referenced_decl = callee
                .get("referencedDecl")
                .ok_or_else(|| "callee is not a direct function identifier".to_string())?;
            let name = string_field(referenced_decl, "name")
                .ok_or_else(|| "callee is missing referenced function name".to_string())?;
            match string_field(referenced_decl, "kind").as_deref() {
                Some("FunctionDecl") => Ok(name),
                Some("ParmVarDecl") | Some("VarDecl") => {
                    let ty = expr_type(callee).map_err(|error| error.message)?;
                    if clang_type_is_function_pointer(&ty) {
                        Ok(name)
                    } else {
                        Err("callee is not a direct function identifier".to_string())
                    }
                }
                _ => Err("callee is not a direct function identifier".to_string()),
            }
        }
        Some(kind) => Err(format!(
            "callee node {kind} is not a direct function identifier"
        )),
        None => Err("callee node without kind is not a direct function identifier".to_string()),
    }
}
