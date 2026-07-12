
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
    if nested_call_count > 0
        && args
            .iter()
            .any(clang_is_direct_record_scalar_member_call_arg)
    {
        return Some(
            "direct record scalar member call argument cannot be combined with an additional call"
                .to_string(),
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
