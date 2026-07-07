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
    if let Some(reason) = bounded_call_args_rejection_reason(&args) {
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
    if !clang_type_is_const_void_pointer(&target) {
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
    match &operand {
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
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "{callee} destination BitCast operand {} is not mutable unsigned 8-bit pointer",
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
        ("size_t", _) | (_, "size_t") | ("__size_t", _) | (_, "__size_t")
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
                Some("ParmVarDecl") => {
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

#[cfg(feature = "typed-ir")]
fn clang_type_is_function_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. } if matches!(pointee.kind, ClangTypeKind::Function)
    )
}

#[cfg(feature = "typed-ir")]
fn bounded_call_args_rejection_reason(args: &[ClangExprSkeleton]) -> Option<String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, ClangExprSkeleton::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Some(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    if args
        .iter()
        .any(clang_single_chain_nested_call_with_scalar_inc_dec_leaf)
        && args.len() != 1
    {
        return Some(
            "side-effect nested call arguments cannot be combined with other call arguments"
                .to_string(),
        );
    }
    if args.len() == 1 && clang_scalar_inc_dec_call_arg(&args[0]) {
        return None;
    }
    for (index, arg) in args.iter().enumerate() {
        if let Some(reason) = bounded_call_arg_rejection_reason(arg, true) {
            return Some(format!("argument {index}: {reason}"));
        }
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_scalar_inc_dec_call_arg(expr: &ClangExprSkeleton) -> bool {
    let ClangExprSkeleton::IncDec { target, ty, .. } = expr else {
        return false;
    };
    let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = target.as_ref() else {
        return false;
    };
    target_ty == ty && matches!(target_ty.kind, ClangTypeKind::Integer { .. })
}

#[cfg(feature = "typed-ir")]
fn clang_single_chain_nested_call_with_scalar_inc_dec_leaf(expr: &ClangExprSkeleton) -> bool {
    let ClangExprSkeleton::Call { args, ty, .. } = expr else {
        return false;
    };
    if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
        return false;
    }
    let [arg] = args.as_slice() else {
        return false;
    };
    clang_scalar_inc_dec_call_arg(arg)
        || clang_single_chain_nested_call_with_scalar_inc_dec_leaf(arg)
}

#[cfg(feature = "typed-ir")]
fn bounded_call_arg_rejection_reason(
    expr: &ClangExprSkeleton,
    allow_immediate_nested_call: bool,
) -> Option<String> {
    match expr {
        ClangExprSkeleton::DeclRef { .. }
        | ClangExprSkeleton::IntegerLiteral { .. }
        | ClangExprSkeleton::SizeOfType { .. }
        | ClangExprSkeleton::AlignOfType { .. } => None,
        ClangExprSkeleton::NullPtr { .. } => {
            Some("call arguments cannot use null pointer value semantics".to_string())
        }
        ClangExprSkeleton::Binary { lhs, rhs, .. } => bounded_call_arg_rejection_reason(lhs, false)
            .or_else(|| bounded_call_arg_rejection_reason(rhs, false)),
        ClangExprSkeleton::Unary { operand, .. }
        | ClangExprSkeleton::Cast { expr: operand, .. }
        | ClangExprSkeleton::LValueToRValue { expr: operand, .. } => {
            bounded_call_arg_rejection_reason(operand, false)
        }
        ClangExprSkeleton::ArrayToPointerDecay { .. } => Some(
            "call arguments cannot use array-to-pointer decay before explicit lowering evidence"
                .to_string(),
        ),
        ClangExprSkeleton::FunctionToPointerDecay { .. } => None,
        ClangExprSkeleton::Conditional { .. } => {
            Some("conditional call arguments are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            bounded_call_arg_rejection_reason(base, false)
                .or_else(|| bounded_call_arg_rejection_reason(index, false))
        }
        ClangExprSkeleton::Member { .. } => {
            Some("member access call arguments are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::ArrayLiteral { .. } => {
            Some("array initializer lists are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::Call { args, ty, .. } if allow_immediate_nested_call => {
            if clang_strlen_leaf_call_arg(expr) {
                return None;
            }
            if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                if clang_mutable_record_pointer_record_name(ty).is_some() {
                    return bounded_record_pointer_constructor_call_arg_rejection_reason(args, ty);
                }
                return Some(format!(
                    "nested call result type {} is outside the bounded call subset",
                    ty.spelled
                ));
            }
            if args
                .iter()
                .any(clang_single_chain_nested_call_with_scalar_inc_dec_leaf)
                && args.len() != 1
            {
                return Some(
                    "side-effect nested call arguments cannot be combined with other call arguments"
                        .to_string(),
                );
            }
            if args.len() == 1
                && (clang_scalar_inc_dec_call_arg(&args[0])
                    || clang_single_chain_nested_call_with_scalar_inc_dec_leaf(&args[0]))
            {
                return None;
            }
            for (index, arg) in args.iter().enumerate() {
                if let Some(reason) = bounded_call_arg_rejection_reason(arg, false) {
                    return Some(format!("nested call argument {index}: {reason}"));
                }
            }
            None
        }
        ClangExprSkeleton::Call { .. } => {
            Some("nested call expressions are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::IncDec { .. } => {
            Some("call arguments cannot use increment/decrement value semantics".to_string())
        }
        ClangExprSkeleton::Deref { .. } => {
            Some("call arguments cannot use dereference value semantics".to_string())
        }
        ClangExprSkeleton::AddrOf { .. } => None,
        ClangExprSkeleton::Unsupported { node, reason } => {
            Some(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

#[cfg(feature = "typed-ir")]
fn bounded_record_pointer_constructor_call_arg_rejection_reason(
    args: &[ClangExprSkeleton],
    ty: &ClangTypeSkeleton,
) -> Option<String> {
    let return_record = clang_mutable_record_pointer_record_name(ty)?;
    let Some(first_arg) = args.first() else {
        return Some(
            "record pointer constructor call requires an address-of local record first argument"
                .to_string(),
        );
    };
    let ClangExprSkeleton::AddrOf {
        operand,
        ty: first_arg_ty,
    } = first_arg
    else {
        return Some(
            "record pointer constructor call first argument must be address-of local record"
                .to_string(),
        );
    };
    let Some(first_record) = clang_mutable_record_pointer_record_name(first_arg_ty) else {
        return Some(format!(
            "record pointer constructor call first argument target {} must be a mutable record pointer",
            first_arg_ty.spelled
        ));
    };
    if first_record != return_record {
        return Some(format!(
            "record pointer constructor call first argument record {first_record} does not match return record {return_record}"
        ));
    }
    let ClangExprSkeleton::DeclRef { ty: operand_ty, .. } = operand.as_ref() else {
        return Some(
            "record pointer constructor call first argument must address a direct record variable"
                .to_string(),
        );
    };
    if !matches!(&operand_ty.kind, ClangTypeKind::Record { name } if name == return_record) {
        return Some(format!(
            "record pointer constructor call first argument operand {} must be record {return_record}",
            operand_ty.spelled
        ));
    }
    for (index, arg) in args.iter().enumerate().skip(1) {
        if clang_strlen_leaf_call_arg(arg) {
            continue;
        }
        if let Some(reason) = bounded_call_arg_rejection_reason(arg, false) {
            return Some(format!(
                "record pointer constructor call argument {index}: {reason}"
            ));
        }
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_strlen_leaf_call_arg(expr: &ClangExprSkeleton) -> bool {
    let ClangExprSkeleton::Call { callee, args, ty } = expr else {
        return false;
    };
    if callee != "strlen"
        || !(matches!(&ty.kind, ClangTypeKind::Integer { .. }) || clang_type_is_size_t_spelling(ty))
    {
        return false;
    }
    let [ClangExprSkeleton::DeclRef { ty: arg_ty, .. }] = args.as_slice() else {
        return false;
    };
    clang_type_is_readonly_unsigned_8_bit_pointer(arg_ty)
        || clang_type_is_const_char_pointer_spelling(arg_ty)
}

#[cfg(feature = "typed-ir")]
fn clang_mutable_record_pointer_record_name(ty: &ClangTypeSkeleton) -> Option<&str> {
    let ClangTypeKind::Pointer { pointee, .. } = &ty.kind else {
        return None;
    };
    if clang_type_is_const(pointee) {
        return None;
    }
    let ClangTypeKind::Record { name } = &pointee.kind else {
        return None;
    };
    Some(name.as_str())
}
