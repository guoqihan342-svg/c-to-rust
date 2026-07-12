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
    if args
        .iter()
        .any(clang_is_mutable_void_pointer_address_call_arg)
    {
        if let Some(reason) =
            clang_mutable_void_pointer_address_signature_rejection_reason(callee_node, &args)
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
            if let Some(address_record) = clang_mutable_record_pointer_record_name(ty) {
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
                    return Ok(operand);
                }
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: format!(
                        "direct-call argument mutable void * BitCast operand {} does not match address target record {address_record}",
                        operand_ty.spelled
                    ),
                });
            }
            match clang_mutable_void_pointer_address_skeleton(addr_operand, ty, &target) {
                Ok(address) => Ok(address),
                Err(reason) => Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason,
                }),
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
