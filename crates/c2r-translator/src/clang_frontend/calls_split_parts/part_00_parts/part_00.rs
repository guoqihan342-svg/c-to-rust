#[cfg(feature = "typed-ir")]
fn call_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    call_expr_skeleton_from_ast_with_memory_statement_args(expr, false)
}

#[cfg(feature = "typed-ir")]
fn call_stmt_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    call_expr_skeleton_from_ast_with_memory_statement_args(expr, true)
}

#[cfg(feature = "typed-ir")]
fn call_expr_skeleton_from_ast_with_memory_statement_args(
    expr: &Value,
    allow_memory_statement_args: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let children = inner(expr);
    let Some((callee_node, arg_nodes)) = children.split_first() else {
        return Err(ClangFrontendError {
            kind: "invalid_call_expr".to_string(),
            message: "CallExpr is missing callee".to_string(),
        });
    };
    let callee = match direct_call_callee_name(callee_node) {
        Ok(callee) => callee,
        Err(reason) => {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "CallExpr".to_string(),
                reason,
            });
        }
    };
    let mut args = Vec::with_capacity(arg_nodes.len());
    for (index, arg_node) in arg_nodes.iter().enumerate() {
        let arg = match (allow_memory_statement_args, callee.as_str(), index) {
            (true, "memset", 0) => memory_destination_arg_skeleton_from_ast(arg_node, "memset")?,
            (true, "memcpy", 0) => memory_destination_arg_skeleton_from_ast(arg_node, "memcpy")?,
            (true, "memcpy", 1) => memcpy_source_arg_skeleton_from_ast(arg_node)?,
            _ => direct_call_arg_skeleton_from_ast(arg_node)?,
        };
        args.push(arg);
    }
    if args
        .iter()
        .any(clang_is_direct_record_scalar_member_call_arg)
    {
        if let Some(reason) =
            clang_direct_record_scalar_member_call_signature_rejection_reason(callee_node, &args)
        {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "CallExpr".to_string(),
                reason,
            });
        }
    }
    let rejection_reason = match (allow_memory_statement_args, callee.as_str()) {
        (true, "memset") => bounded_memset_statement_args_rejection_reason(&args),
        (true, "memcpy") => bounded_memcpy_statement_args_rejection_reason(&args),
        _ => bounded_call_args_rejection_reason(&args),
    };
    if let Some(reason) = rejection_reason {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "CallExpr".to_string(),
            reason,
        });
    }
    Ok(ClangExprSkeleton::Call {
        callee,
        args,
        ty: expr_type(expr)?,
    })
}

#[cfg(feature = "typed-ir")]
fn direct_call_arg_skeleton_from_ast(arg: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(arg, "kind").as_deref() != Some("ImplicitCastExpr")
        || string_field(arg, "castKind").as_deref() != Some("BitCast")
    {
        return expr_skeleton_from_ast_with_options(arg, true);
    }

    let target = expr_type(arg)?;
    let target_is_const_void_pointer = clang_type_is_const_void_pointer(&target);
    let target_is_mutable_void_pointer = clang_type_is_mutable_void_pointer(&target);
    if !target_is_const_void_pointer && !target_is_mutable_void_pointer {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "direct-call argument BitCast target {} is outside the readonly byte pointer to const void * subset",
                target.spelled
            ),
        });
    }

    let operand = inner(arg).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_clang_expr".to_string(),
        message: "ImplicitCastExpr BitCast is missing operand".to_string(),
    })?;
    let operand = expr_skeleton_from_ast_with_options(operand, true)?;
    if target_is_const_void_pointer {
        return match &operand {
            ClangExprSkeleton::DeclRef { ty, .. }
                if clang_type_is_readonly_8_bit_pointer(ty)
                    || clang_type_is_const_char_pointer_spelling(ty) =>
            {
                Ok(operand)
            }
            ClangExprSkeleton::DeclRef { ty, .. } => Ok(ClangExprSkeleton::Unsupported {
                node: "ImplicitCastExpr".to_string(),
                reason: format!(
                    "direct-call argument BitCast operand {} is not a readonly 8-bit pointer",
                    ty.spelled
                ),
            }),
            ClangExprSkeleton::Unsupported { node, reason } => Ok(ClangExprSkeleton::Unsupported {
                node: node.clone(),
                reason: reason.clone(),
            }),
            _ => Ok(ClangExprSkeleton::Unsupported {
                node: "ImplicitCastExpr".to_string(),
                reason: "direct-call argument BitCast operand must be a direct pointer parameter"
                    .to_string(),
            }),
        };
    }

    match &operand {
        ClangExprSkeleton::AddrOf {
            operand: addr_operand,
            ty,
        } => {
            let Some(address_record) = clang_mutable_record_pointer_record_name(ty) else {
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: format!(
                        "direct-call argument mutable void * BitCast address target {} is not a mutable record pointer",
                        ty.spelled
                    ),
                });
            };
            let ClangExprSkeleton::DeclRef {
                ty: operand_ty, ..
            } = addr_operand.as_ref()
            else {
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason:
                        "direct-call argument mutable void * BitCast operand must address a direct record variable"
                            .to_string(),
                });
            };
            if matches!(&operand_ty.kind, ClangTypeKind::Record { name } if name == address_record)
            {
                Ok(operand)
            } else {
                Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: format!(
                        "direct-call argument mutable void * BitCast operand {} does not match address target record {address_record}",
                        operand_ty.spelled
                    ),
                })
            }
        }
        ClangExprSkeleton::Unsupported { node, reason } => Ok(ClangExprSkeleton::Unsupported {
            node: node.clone(),
            reason: reason.clone(),
        }),
        _ => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason:
                "direct-call argument mutable void * BitCast operand must be address-of local record"
                    .to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn memory_destination_arg_skeleton_from_ast(
    arg: &Value,
    callee: &str,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(arg, "kind").as_deref() != Some("ImplicitCastExpr")
        || string_field(arg, "castKind").as_deref() != Some("BitCast")
    {
        return expr_skeleton_from_ast_with_options(arg, true);
    }

    let target = expr_type(arg)?;
    if !clang_type_is_mutable_void_pointer(&target) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "{callee} destination BitCast target {} is not mutable void *",
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
            if clang_type_is_mutable_unsigned_8_bit_pointer(ty) =>
        {
            Ok(operand)
        }
        ClangExprSkeleton::DeclRef { ty, .. }
            if callee == "memset" && clang_mutable_record_pointer_record_name(ty).is_some() =>
        {
            Ok(operand)
        }
        ClangExprSkeleton::ArrayToPointerDecay { target, expr }
            if callee == "memset" || callee == "memcpy" =>
        {
            if let Some(reason) =
                clang_memory_destination_array_decay_rejection_reason(callee, target, expr)
            {
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
                "{callee} destination BitCast operand {} is not a supported mutable byte or record pointer",
                ty.spelled
            ),
        }),
        ClangExprSkeleton::Unsupported { node, reason } => Ok(ClangExprSkeleton::Unsupported {
            node: node.clone(),
            reason: reason.clone(),
        }),
        _ => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "{callee} destination BitCast operand must be a direct pointer parameter"
            ),
        }),
    }
}

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
