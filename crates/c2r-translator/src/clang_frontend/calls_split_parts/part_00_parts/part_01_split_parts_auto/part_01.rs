
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
        | ClangExprSkeleton::AddrOf { operand, .. }
        | ClangExprSkeleton::MutableVoidPointerAddress { operand, .. } => {
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
