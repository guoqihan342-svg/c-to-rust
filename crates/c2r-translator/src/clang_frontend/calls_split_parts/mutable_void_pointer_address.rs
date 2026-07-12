#[cfg(feature = "typed-ir")]
fn clang_mutable_void_pointer_address_skeleton(
    operand: &ClangExprSkeleton,
    source_pointer: &ClangTypeSkeleton,
    target: &ClangTypeSkeleton,
) -> Result<ClangExprSkeleton, String> {
    let ClangTypeKind::Pointer { pointee, .. } = &source_pointer.kind else {
        return Err(format!(
            "direct-call mutable void * address source {} is not a pointer",
            source_pointer.spelled
        ));
    };
    if clang_type_is_const(pointee) || !matches!(pointee.kind, ClangTypeKind::Integer { .. }) {
        return Err(format!(
            "direct-call mutable void * address source {} is not a mutable fixed-width integer pointer",
            source_pointer.spelled
        ));
    }
    let terminal = clang_mutable_record_scalar_lvalue_type(operand)?;
    if pointee.kind != terminal.kind {
        return Err(format!(
            "direct-call mutable void * address source {} does not match scalar lvalue type {}",
            pointee.spelled, terminal.spelled
        ));
    }
    Ok(ClangExprSkeleton::MutableVoidPointerAddress {
        operand: Box::new(operand.clone()),
        source_pointer: source_pointer.clone(),
        target: target.clone(),
    })
}

#[cfg(feature = "typed-ir")]
fn clang_mutable_record_scalar_lvalue_type(
    expr: &ClangExprSkeleton,
) -> Result<&ClangTypeSkeleton, String> {
    match expr {
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: true,
            ..
        } => {
            let ClangExprSkeleton::DeclRef { ty: root_ty, .. } = base.as_ref() else {
                return Err(
                    "direct-call mutable void * scalar address must start at one direct record pointer root"
                        .to_string(),
                );
            };
            if clang_mutable_record_pointer_record_name(root_ty).is_none() {
                return Err(format!(
                    "direct-call mutable void * scalar address root {} is not a mutable record pointer",
                    root_ty.spelled
                ));
            }
            Ok(ty)
        }
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: false,
            ..
        } => {
            let base_ty = clang_mutable_record_scalar_lvalue_type(base)?;
            if !matches!(base_ty.kind, ClangTypeKind::Record { .. }) {
                return Err(format!(
                    "direct-call mutable void * scalar address dot base {} is not a record",
                    base_ty.spelled
                ));
            }
            Ok(ty)
        }
        _ => Err(
            "direct-call mutable void * address operand must be a bounded record scalar member path"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn clang_is_mutable_void_pointer_address_call_arg(expr: &ClangExprSkeleton) -> bool {
    matches!(expr, ClangExprSkeleton::MutableVoidPointerAddress { .. })
}

#[cfg(feature = "typed-ir")]
fn clang_mutable_void_pointer_address_signature_rejection_reason(
    callee_node: &Value,
    args: &[ClangExprSkeleton],
) -> Option<String> {
    if !clang_direct_call_targets_function_decl(callee_node) {
        return Some(
            "mutable void * scalar address call must target a direct FunctionDecl".to_string(),
        );
    }
    let Some(type_object) = callee_node.get("type") else {
        return Some(
            "mutable void * scalar address call callee lacks a verifiable signature".to_string(),
        );
    };
    let candidates = clang_type_candidate_spellings(type_object);
    if candidates.is_empty() {
        return Some(
            "mutable void * scalar address call callee lacks a verifiable signature".to_string(),
        );
    }
    let mut verified_candidate = false;
    let mut last_unverifiable = None;
    for candidate in candidates {
        match validate_mutable_void_pointer_address_signature_candidate(&candidate, args) {
            Ok(()) => verified_candidate = true,
            Err((true, reason)) => return Some(reason),
            Err((false, reason)) => last_unverifiable = Some(reason),
        }
    }
    if verified_candidate {
        return None;
    }
    Some(last_unverifiable.unwrap_or_else(|| {
        "mutable void * scalar address call callee lacks a verifiable signature".to_string()
    }))
}

#[cfg(feature = "typed-ir")]
fn validate_mutable_void_pointer_address_signature_candidate(
    candidate: &str,
    args: &[ClangExprSkeleton],
) -> Result<(), (bool, String)> {
    let callee_ty = type_from_qual_type_with_target_abi(candidate, None).map_err(|error| {
        (
            false,
            format!(
                "mutable void * scalar address call callee signature {candidate} is unsupported: {}",
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
                    "mutable void * scalar address call callee has unsupported signature {candidate}"
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
                    "mutable void * scalar address call callee signature {candidate} is not verifiable"
                ),
            )
        })?;
    let params = split_direct_call_signature_params(params_text);
    if params.contains(&"...") {
        return Err((
            true,
            "mutable void * scalar address call cannot target a variadic signature".to_string(),
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
                "mutable void * scalar address call signature expects {} arguments but CallExpr has {}",
                params.len(),
                args.len()
            ),
        ));
    }
    for (index, (param, arg)) in params.iter().zip(args).enumerate() {
        if !clang_is_mutable_void_pointer_address_call_arg(arg) {
            continue;
        }
        let param_ty = type_from_qual_type_with_target_abi(param, None).map_err(|error| {
            (
                false,
                format!(
                    "mutable void * scalar address call parameter {index} type is unsupported: {}",
                    error.message
                ),
            )
        })?;
        if !clang_type_is_mutable_void_pointer(&param_ty) {
            return Err((
                true,
                format!(
                    "mutable void * scalar address argument {index} requires a mutable void * parameter, got {}",
                    param_ty.spelled
                ),
            ));
        }
    }
    Ok(())
}
