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
        ClangExprSkeleton::AddrOf { .. } => None,
        ClangExprSkeleton::Unsupported { node, reason } => {
            Some(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

#[cfg(feature = "typed-ir")]
fn clang_array_decay_direct_call_arg_rejection_reason(
    target: &ClangTypeSkeleton,
    expr: &ClangExprSkeleton,
) -> Option<String> {
    let target_element = match &target.kind {
        ClangTypeKind::Pointer { pointee, .. }
            if clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { .. }) =>
        {
            pointee.as_ref()
        }
        _ => {
            return Some(format!(
                "array-to-pointer decay call argument target {} must be a readonly integer pointer",
                target.spelled
            ));
        }
    };
    let ClangExprSkeleton::DeclRef { name, ty: array_ty } = expr else {
        return Some(
            "array-to-pointer decay call argument must be a direct fixed array variable"
                .to_string(),
        );
    };
    let ClangTypeKind::Array {
        element,
        len: Some(_),
    } = &array_ty.kind
    else {
        return Some(format!(
            "array-to-pointer decay call argument {name} has unsupported array type {}",
            array_ty.spelled
        ));
    };
    let (
        ClangTypeKind::Integer {
            signed: target_signed,
            width: target_width,
        },
        ClangTypeKind::Integer {
            signed: array_signed,
            width: array_width,
        },
    ) = (&target_element.kind, &element.kind)
    else {
        return Some(format!(
            "array-to-pointer decay call argument {name} has unsupported array element type {}",
            element.spelled
        ));
    };
    if target_signed != array_signed || target_width != array_width {
        return Some(format!(
            "array-to-pointer decay call argument element type {} does not match target element type {}",
            element.spelled, target_element.spelled
        ));
    }
    None
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
