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
    let side_effect_args = match clang_side_effect_call_args(args) {
        Ok(side_effect_args) => side_effect_args,
        Err(reason) => return Some(reason),
    };
    if !side_effect_args.is_empty() {
        for (side_effect_index, assigned_var) in &side_effect_args {
            for (index, arg) in args.iter().enumerate() {
                if index == *side_effect_index {
                    continue;
                }
                if clang_expr_mentions_decl(arg, assigned_var) {
                    return Some(format!(
                        "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                    ));
                }
            }
        }
        for (index, arg) in args.iter().enumerate() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            if let Some(reason) = bounded_call_arg_rejection_reason(arg, false) {
                return Some(format!("argument {index}: {reason}"));
            }
        }
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
fn bounded_memset_statement_args_rejection_reason(args: &[ClangExprSkeleton]) -> Option<String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, ClangExprSkeleton::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Some(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    let side_effect_args = match clang_side_effect_call_args(args) {
        Ok(side_effect_args) => side_effect_args,
        Err(reason) => return Some(reason),
    };
    if !side_effect_args.is_empty() {
        for (side_effect_index, assigned_var) in &side_effect_args {
            for (index, arg) in args.iter().enumerate() {
                if index == *side_effect_index {
                    continue;
                }
                if clang_expr_mentions_decl(arg, assigned_var) {
                    return Some(format!(
                        "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                    ));
                }
            }
        }
        for (index, arg) in args.iter().enumerate() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            if let Some(reason) = bounded_memset_statement_arg_rejection_reason(index, arg, false) {
                return Some(format!("argument {index}: {reason}"));
            }
        }
        return None;
    }
    for (index, arg) in args.iter().enumerate() {
        if let Some(reason) = bounded_memset_statement_arg_rejection_reason(index, arg, true) {
            return Some(format!("argument {index}: {reason}"));
        }
    }
    None
}

#[cfg(feature = "typed-ir")]
fn bounded_memset_statement_arg_rejection_reason(
    index: usize,
    arg: &ClangExprSkeleton,
    allow_immediate_nested_call: bool,
) -> Option<String> {
    if index == 0 {
        if let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = arg {
            return clang_memory_destination_array_decay_rejection_reason("memset", target, expr);
        }
    }
    bounded_call_arg_rejection_reason(arg, allow_immediate_nested_call)
}

#[cfg(feature = "typed-ir")]
fn bounded_memcpy_statement_args_rejection_reason(args: &[ClangExprSkeleton]) -> Option<String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, ClangExprSkeleton::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Some(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    let side_effect_args = match clang_side_effect_call_args(args) {
        Ok(side_effect_args) => side_effect_args,
        Err(reason) => return Some(reason),
    };
    if !side_effect_args.is_empty() {
        for (side_effect_index, assigned_var) in &side_effect_args {
            for (index, arg) in args.iter().enumerate() {
                if index == *side_effect_index {
                    continue;
                }
                if clang_expr_mentions_decl(arg, assigned_var) {
                    return Some(format!(
                        "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                    ));
                }
            }
        }
        for (index, arg) in args.iter().enumerate() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            if let Some(reason) = bounded_memcpy_statement_arg_rejection_reason(index, arg, false) {
                return Some(format!("argument {index}: {reason}"));
            }
        }
        return None;
    }
    for (index, arg) in args.iter().enumerate() {
        if let Some(reason) = bounded_memcpy_statement_arg_rejection_reason(index, arg, true) {
            return Some(format!("argument {index}: {reason}"));
        }
    }
    None
}

#[cfg(feature = "typed-ir")]
fn bounded_memcpy_statement_arg_rejection_reason(
    index: usize,
    arg: &ClangExprSkeleton,
    allow_immediate_nested_call: bool,
) -> Option<String> {
    if index == 0 {
        if let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = arg {
            return clang_memory_destination_array_decay_rejection_reason("memcpy", target, expr);
        }
    }
    if index == 1 {
        if let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = arg {
            return clang_memcpy_source_array_decay_rejection_reason(target, expr);
        }
    }
    bounded_call_arg_rejection_reason(arg, allow_immediate_nested_call)
}

#[cfg(feature = "typed-ir")]
fn clang_memory_destination_array_decay_rejection_reason(
    callee: &str,
    target: &ClangTypeSkeleton,
    expr: &ClangExprSkeleton,
) -> Option<String> {
    let target_element = match &target.kind {
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { signed: false, width: 8 }) =>
        {
            pointee.as_ref()
        }
        _ => {
            return Some(format!(
                "{callee} destination array-to-pointer decay target {} must be a mutable unsigned 8-bit pointer",
                target.spelled
            ));
        }
    };
    let ClangExprSkeleton::DeclRef { name, ty: array_ty } = expr else {
        return Some(format!(
            "{callee} destination array-to-pointer decay must be a direct fixed byte array variable"
        ));
    };
    let ClangTypeKind::Array {
        element,
        len: Some(_),
    } = &array_ty.kind
    else {
        return Some(format!(
            "{callee} destination array-to-pointer decay {name} has unsupported array type {}",
            array_ty.spelled
        ));
    };
    if !matches!(
        &element.kind,
        ClangTypeKind::Integer {
            signed: false,
            width: 8
        }
    ) {
        return Some(format!(
            "{callee} destination array-to-pointer decay {name} must be a fixed unsigned 8-bit integer array, got {}",
            array_ty.spelled
        ));
    }
    if element.spelled != target_element.spelled && element.canonical != target_element.canonical {
        return Some(format!(
            "{callee} destination array-to-pointer decay element type {} does not match target element type {}",
            element.spelled, target_element.spelled
        ));
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_memcpy_source_array_decay_rejection_reason(
    target: &ClangTypeSkeleton,
    expr: &ClangExprSkeleton,
) -> Option<String> {
    let target_element = match &target.kind {
        ClangTypeKind::Pointer { pointee, .. }
            if matches!(&pointee.kind, ClangTypeKind::Integer { signed: false, width: 8 }) =>
        {
            pointee.as_ref()
        }
        _ => {
            return Some(format!(
                "memcpy source array-to-pointer decay target {} must be an unsigned 8-bit pointer",
                target.spelled
            ));
        }
    };
    let ClangExprSkeleton::DeclRef { name, ty: array_ty } = expr else {
        return Some(
            "memcpy source array-to-pointer decay must be a direct fixed byte array variable"
                .to_string(),
        );
    };
    let ClangTypeKind::Array {
        element,
        len: Some(_),
    } = &array_ty.kind
    else {
        return Some(format!(
            "memcpy source array-to-pointer decay {name} has unsupported array type {}",
            array_ty.spelled
        ));
    };
    if !matches!(
        &element.kind,
        ClangTypeKind::Integer {
            signed: false,
            width: 8
        }
    ) {
        return Some(format!(
            "memcpy source array-to-pointer decay {name} must be a fixed unsigned 8-bit integer array, got {}",
            array_ty.spelled
        ));
    }
    if element.spelled != target_element.spelled && element.canonical != target_element.canonical {
        return Some(format!(
            "memcpy source array-to-pointer decay element type {} does not match target element type {}",
            element.spelled, target_element.spelled
        ));
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_scalar_inc_dec_call_arg_assigned_name(expr: &ClangExprSkeleton) -> Option<&str> {
    let ClangExprSkeleton::IncDec { target, ty, .. } = expr else {
        return None;
    };
    let ClangExprSkeleton::DeclRef {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return None;
    };
    (target_ty == ty && matches!(target_ty.kind, ClangTypeKind::Integer { .. }))
        .then_some(name.as_str())
}

#[cfg(feature = "typed-ir")]
fn clang_side_effect_call_args(
    args: &[ClangExprSkeleton],
) -> Result<Vec<(usize, &str)>, String> {
    let mut found = Vec::new();
    for (index, arg) in args.iter().enumerate() {
        let Some(assigned_var) = clang_side_effect_expr_assigned_name(arg)? else {
            continue;
        };
        if found
            .iter()
            .any(|(_, existing_var)| *existing_var == assigned_var)
        {
            return Err(format!(
                "call arguments cannot modify variable {assigned_var} more than once"
            ));
        }
        found.push((index, assigned_var));
    }
    Ok(found)
}

#[cfg(feature = "typed-ir")]
fn clang_side_effect_expr_assigned_name(
    expr: &ClangExprSkeleton,
) -> Result<Option<&str>, String> {
    if let Some(name) = clang_scalar_inc_dec_call_arg_assigned_name(expr) {
        return Ok(Some(name));
    }
    let ClangExprSkeleton::Call { args, ty, .. } = expr else {
        return Ok(None);
    };
    if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
        return Ok(None);
    }
    let found = clang_side_effect_call_args(args)?;
    match found.as_slice() {
        [] => Ok(None),
        [(_, name)] => Ok(Some(*name)),
        _ => Err(
            "nested call argument cannot use increment/decrement value semantics for more than one variable"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn clang_expr_mentions_decl(expr: &ClangExprSkeleton, expected: &str) -> bool {
    match expr {
        ClangExprSkeleton::DeclRef { name, .. } => name == expected,
        ClangExprSkeleton::Binary { lhs, rhs, .. } => {
            clang_expr_mentions_decl(lhs, expected) || clang_expr_mentions_decl(rhs, expected)
        }
        ClangExprSkeleton::Unary { operand, .. }
        | ClangExprSkeleton::Cast { expr: operand, .. }
        | ClangExprSkeleton::LValueToRValue { expr: operand, .. }
        | ClangExprSkeleton::ArrayToPointerDecay { expr: operand, .. }
        | ClangExprSkeleton::FunctionToPointerDecay { expr: operand, .. }
        | ClangExprSkeleton::AddrOf { operand, .. } => {
            clang_expr_mentions_decl(operand, expected)
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            clang_expr_mentions_decl(condition, expected)
                || clang_expr_mentions_decl(then_expr, expected)
                || clang_expr_mentions_decl(else_expr, expected)
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            clang_expr_mentions_decl(base, expected) || clang_expr_mentions_decl(index, expected)
        }
        ClangExprSkeleton::ArrayLiteral { elements, .. } => elements
            .iter()
            .any(|element| clang_expr_mentions_decl(element, expected)),
        ClangExprSkeleton::Call { args, .. } => args
            .iter()
            .any(|arg| clang_expr_mentions_decl(arg, expected)),
        ClangExprSkeleton::Member { base, .. } => clang_expr_mentions_decl(base, expected),
        ClangExprSkeleton::IncDec { target, .. } => clang_expr_mentions_decl(target, expected),
        ClangExprSkeleton::Deref { ptr, .. } => clang_expr_mentions_decl(ptr, expected),
        ClangExprSkeleton::IntegerLiteral { .. }
        | ClangExprSkeleton::SizeOfType { .. }
        | ClangExprSkeleton::AlignOfType { .. }
        | ClangExprSkeleton::NullPtr { .. }
        | ClangExprSkeleton::Unsupported { .. } => false,
    }
}
