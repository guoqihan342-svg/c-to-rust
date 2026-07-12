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
        ClangExprSkeleton::NullPtr { ty } => clang_null_pointer_call_arg_rejection_reason(ty),
        ClangExprSkeleton::Binary { lhs, rhs, .. } => bounded_call_arg_rejection_reason(lhs, false)
            .or_else(|| bounded_call_arg_rejection_reason(rhs, false)),
        ClangExprSkeleton::Unary { operand, .. }
        | ClangExprSkeleton::Cast { expr: operand, .. }
        | ClangExprSkeleton::LValueToRValue { expr: operand, .. } => {
            bounded_call_arg_rejection_reason(operand, false)
        }
        ClangExprSkeleton::ArrayToPointerDecay { target, expr } => {
            clang_array_decay_direct_call_arg_rejection_reason(target, expr)
        }
        ClangExprSkeleton::FunctionToPointerDecay { .. } => None,
        ClangExprSkeleton::Conditional { .. } => {
            Some("conditional call arguments are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            bounded_call_arg_rejection_reason(base, false)
                .or_else(|| bounded_call_arg_rejection_reason(index, false))
        }
        ClangExprSkeleton::Member {
            base,
            field,
            ty,
            is_arrow,
        } => clang_direct_record_scalar_member_call_arg_rejection_reason(
            base, field, ty, *is_arrow,
        ),
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
                if !clang_nested_call_pointer_result_allowed(ty) {
                    return Some(format!(
                        "nested call result type {} is outside the bounded call subset",
                        ty.spelled
                    ));
                }
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
                        return Some(format!("nested call argument {index}: {reason}"));
                    }
                }
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
        ClangExprSkeleton::AddrOf { .. }
        | ClangExprSkeleton::MutableVoidPointerAddress { .. } => None,
        ClangExprSkeleton::Unsupported { node, reason } => {
            Some(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

#[cfg(feature = "typed-ir")]
fn clang_direct_record_scalar_member_call_arg_rejection_reason(
    base: &ClangExprSkeleton,
    field: &str,
    ty: &ClangTypeSkeleton,
    is_arrow: bool,
) -> Option<String> {
    if !matches!(ty.kind, ClangTypeKind::Integer { .. }) {
        return Some(format!(
            "direct record call argument field {field} must be a fixed-width integer scalar, got {}",
            ty.spelled
        ));
    }
    let ClangExprSkeleton::DeclRef { ty: base_ty, .. } = base else {
        return Some(
            "direct record scalar member call argument base must be a direct DeclRef root"
                .to_string(),
        );
    };
    let base_is_supported = if is_arrow {
        matches!(
            &base_ty.kind,
            ClangTypeKind::Pointer { pointee, .. }
                if matches!(pointee.kind, ClangTypeKind::Record { .. })
        )
    } else {
        matches!(base_ty.kind, ClangTypeKind::Record { .. })
    };
    if !base_is_supported {
        return Some(format!(
            "direct record scalar member call argument base has unsupported type {}",
            base_ty.spelled
        ));
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_is_direct_record_scalar_member_call_arg(expr: &ClangExprSkeleton) -> bool {
    match expr {
        ClangExprSkeleton::Member { .. } => true,
        ClangExprSkeleton::Cast { expr, .. }
        | ClangExprSkeleton::LValueToRValue { expr, .. } => {
            clang_is_direct_record_scalar_member_call_arg(expr)
        }
        _ => false,
    }
}

#[cfg(feature = "typed-ir")]
fn clang_direct_record_scalar_member_call_signature_rejection_reason(
    callee_node: &Value,
    args: &[ClangExprSkeleton],
) -> Option<String> {
    if !clang_direct_call_targets_function_decl(callee_node) {
        return Some(
            "direct record scalar member call must target a direct FunctionDecl".to_string(),
        );
    }
    let Some(type_object) = callee_node.get("type") else {
        return Some(
            "direct record scalar member call callee lacks a verifiable signature".to_string(),
        );
    };
    let candidates = clang_type_candidate_spellings(type_object);
    if candidates.is_empty() {
        return Some(
            "direct record scalar member call callee lacks a verifiable signature".to_string(),
        );
    }
    let mut verified_candidate = false;
    let mut last_unverifiable = None;
    for candidate in candidates {
        match validate_direct_record_scalar_member_signature_candidate(&candidate, args) {
            Ok(()) => verified_candidate = true,
            Err((true, reason)) => return Some(reason),
            Err((false, reason)) => last_unverifiable = Some(reason),
        }
    }
    if verified_candidate {
        return None;
    }
    Some(last_unverifiable.unwrap_or_else(|| {
        "direct record scalar member call callee lacks a verifiable signature".to_string()
    }))
}

#[cfg(feature = "typed-ir")]
fn clang_direct_call_targets_function_decl(callee: &Value) -> bool {
    match string_field(callee, "kind").as_deref() {
        Some("ImplicitCastExpr" | "ParenExpr") => inner(callee)
            .first()
            .is_some_and(clang_direct_call_targets_function_decl),
        Some("DeclRefExpr") => callee
            .get("referencedDecl")
            .and_then(|decl| string_field(decl, "kind"))
            .as_deref()
            == Some("FunctionDecl"),
        _ => false,
    }
}

#[cfg(feature = "typed-ir")]
fn validate_direct_record_scalar_member_signature_candidate(
    candidate: &str,
    args: &[ClangExprSkeleton],
) -> Result<(), (bool, String)> {
    let callee_ty = type_from_qual_type_with_target_abi(candidate, None).map_err(|error| {
        (
            false,
            format!(
                "direct record scalar member call callee signature {candidate} is unsupported: {}",
                error.message
            ),
        )
    })?;
    let function_ty = match &callee_ty.kind {
        ClangTypeKind::Pointer { pointee, .. }
            if matches!(pointee.kind, ClangTypeKind::Function) =>
        {
            pointee.as_ref()
        }
        ClangTypeKind::Function => &callee_ty,
        _ => {
            return Err((
                false,
                format!(
                    "direct record scalar member call callee has unsupported signature {candidate}"
                ),
            ));
        }
    };
    let (_, params_text) = split_function_qual_type(&function_ty.spelled)
        .or_else(|| split_function_qual_type(&function_ty.canonical))
        .ok_or_else(|| {
            (
                false,
                format!(
                    "direct record scalar member call callee signature {candidate} is not verifiable"
                ),
            )
        })?;
    let params = split_direct_call_signature_params(params_text);
    if params.contains(&"...") {
        return Err((
            true,
            "direct record scalar member call cannot target a variadic signature".to_string(),
        ));
    }
    let params = if params.len() == 1 && params[0] == "void" {
        Vec::new()
    } else {
        params
    };
    if params.len() != args.len() {
        return Err((
            true,
            format!(
                "direct record scalar member call signature expects {} arguments but CallExpr has {}",
                params.len(),
                args.len()
            ),
        ));
    }
    for (index, (param, arg)) in params.iter().zip(args).enumerate() {
        if !clang_is_direct_record_scalar_member_call_arg(arg) {
            continue;
        }
        let param_ty = match type_from_qual_type_with_target_abi(param, None) {
            Ok(ty) if !matches!(ty.kind, ClangTypeKind::Unsupported { .. }) => ty,
            Ok(_) => {
                return Err((
                    false,
                    format!(
                        "direct record scalar member call parameter {index} type {param} is not verifiable"
                    ),
                ));
            }
            Err(error) => {
                return Err((
                    false,
                    format!(
                        "direct record scalar member call parameter {index} type is unsupported: {}",
                        error.message
                    ),
                ));
            }
        };
        let Some(arg_ty) = clang_expr_skeleton_type(arg) else {
            return Err((
                false,
                format!(
                    "direct record scalar member call argument {index} lacks a verifiable type"
                ),
            ));
        };
        if !matches!(param_ty.kind, ClangTypeKind::Integer { .. })
            || !matches!(arg_ty.kind, ClangTypeKind::Integer { .. })
            || param_ty.kind != arg_ty.kind
        {
            return Err((
                true,
                format!(
                    "direct record scalar member call argument {index} type {} does not match parameter type {}",
                    arg_ty.spelled, param_ty.spelled
                ),
            ));
        }
    }
    Ok(())
}
