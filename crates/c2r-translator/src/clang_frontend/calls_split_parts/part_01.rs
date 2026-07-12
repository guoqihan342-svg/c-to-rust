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

#[cfg(feature = "typed-ir")]
fn split_direct_call_signature_params(params: &str) -> Vec<&str> {
    if params.trim().is_empty() {
        return Vec::new();
    }
    let mut result = Vec::new();
    let mut depth = 0usize;
    let mut start = 0usize;
    for (index, ch) in params.char_indices() {
        match ch {
            '(' | '[' => depth += 1,
            ')' | ']' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                result.push(params[start..index].trim());
                start = index + ch.len_utf8();
            }
            _ => {}
        }
    }
    result.push(params[start..].trim());
    result
}

#[cfg(feature = "typed-ir")]
fn clang_null_pointer_call_arg_rejection_reason(ty: &ClangTypeSkeleton) -> Option<String> {
    if matches!(&ty.kind, ClangTypeKind::Pointer { .. }) {
        return None;
    }
    Some(format!(
        "null pointer call argument type {} is not a pointer",
        ty.spelled
    ))
}

#[cfg(feature = "typed-ir")]
fn clang_nested_call_pointer_result_allowed(ty: &ClangTypeSkeleton) -> bool {
    if clang_type_is_const_char_pointer_spelling(ty) {
        return true;
    }
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if matches!(
                &pointee.kind,
                ClangTypeKind::Void | ClangTypeKind::Integer { .. }
            )
    )
}

#[cfg(feature = "typed-ir")]
fn clang_array_decay_direct_call_arg_rejection_reason(
    target: &ClangTypeSkeleton,
    expr: &ClangExprSkeleton,
) -> Option<String> {
    if matches!(expr, ClangExprSkeleton::ArrayLiteral { .. }) {
        return clang_byte_string_array_decay_call_arg_rejection_reason(target, expr);
    }

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
fn clang_byte_string_array_decay_call_arg_rejection_reason(
    target: &ClangTypeSkeleton,
    expr: &ClangExprSkeleton,
) -> Option<String> {
    if let Err(reason) = clang_byte_string_array_literal_values(expr) {
        return Some(reason);
    }
    let target_element = match &target.kind {
        ClangTypeKind::Pointer { pointee, .. } if clang_type_is_byte_pointer_element(pointee) => {
            pointee.as_ref()
        }
        _ => {
            return Some(format!(
                "string literal array-to-pointer decay target {} must be an 8-bit integer pointer",
                target.spelled
            ));
        }
    };
    if !clang_type_is_byte_pointer_element(target_element) {
        return Some(format!(
            "string literal array-to-pointer decay target element {} is unsupported",
            target_element.spelled
        ));
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_byte_string_array_literal_values(expr: &ClangExprSkeleton) -> Result<Vec<u8>, String> {
    let ClangExprSkeleton::ArrayLiteral { elements, ty } = expr else {
        return Err(
            "string literal array-to-pointer decay requires a byte array literal".to_string(),
        );
    };
    let ClangTypeKind::Array {
        element,
        len: Some(len),
    } = &ty.kind
    else {
        return Err(format!(
            "string literal array-to-pointer decay source {} must be a complete byte array",
            ty.spelled
        ));
    };
    if *len != elements.len() {
        return Err(format!(
            "string literal array-to-pointer decay source {} length does not match element count",
            ty.spelled
        ));
    }
    if !clang_type_is_byte_pointer_element(element) {
        return Err(format!(
            "string literal array-to-pointer decay element type {} is unsupported",
            element.spelled
        ));
    }

    let mut bytes = Vec::with_capacity(elements.len());
    for element in elements {
        let ClangExprSkeleton::IntegerLiteral { value, ty, .. } = element else {
            return Err(
                "string literal array-to-pointer decay requires integer literal elements"
                    .to_string(),
            );
        };
        if !clang_type_is_byte_pointer_element(ty) {
            return Err(format!(
                "string literal array-to-pointer decay element literal type {} is unsupported",
                ty.spelled
            ));
        }
        let byte = u8::try_from(*value).map_err(|_| {
            format!(
                "string literal array-to-pointer decay element value {value} exceeds u8"
            )
        })?;
        bytes.push(byte);
    }
    if bytes.last().copied() != Some(0) {
        return Err(
            "string literal array-to-pointer decay byte array must be NUL terminated"
                .to_string(),
        );
    }
    Ok(bytes)
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_byte_pointer_element(ty: &ClangTypeSkeleton) -> bool {
    if matches!(ty.kind, ClangTypeKind::Integer { width: 8, .. }) {
        return true;
    }
    let spelling = ty
        .spelled
        .trim()
        .strip_prefix("const ")
        .unwrap_or_else(|| ty.spelled.trim())
        .trim();
    matches!(
        spelling,
        "char" | "signed char" | "unsigned char" | "int8_t" | "uint8_t"
    )
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
