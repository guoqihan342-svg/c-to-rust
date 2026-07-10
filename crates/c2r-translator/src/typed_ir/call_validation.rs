fn reserved_c_macro_or_stdlib_callee(callee: &str) -> bool {
    matches!(
        callee,
        // Keep modeled macro names here as a fail-closed backstop; modeled
        // forms must be intercepted before this reserved-surface guard.
        "assert"
            | "abs"
            | "labs"
            | "llabs"
            | "fabs"
            | "fabsf"
            | "fabsl"
            | "static_assert"
            | "_Static_assert"
            | "sizeof"
            | "offsetof"
            | "malloc"
            | "calloc"
            | "realloc"
            | "free"
            | "memcpy"
            | "memmove"
            | "memset"
            | "strlen"
            | "strnlen"
            | "strnlen_s"
            | "printf"
            | "fprintf"
            | "sprintf"
            | "snprintf"
            | "puts"
            | "putchar"
            | "getchar"
            | "exit"
            | "abort"
    )
}

fn validate_bounded_call_args(args: &[IrExpr], context: &EmitContext) -> Result<(), String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, IrExpr::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Err(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    if nested_call_count > 0 && args.iter().any(is_direct_record_scalar_member_call_arg) {
        return Err(
            "direct record scalar member call argument cannot be combined with an additional call"
                .to_string(),
        );
    }
    let mutable_record_borrows = args
        .iter()
        .enumerate()
        .filter_map(|(index, arg)| match arg {
            IrExpr::Var { name, ty, .. }
                if validate_mutable_record_pointer_call_arg(name, ty, context).is_ok() =>
            {
                Some((index, name.as_str()))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    if mutable_record_borrows.len() > 1 {
        return Err(
            "one direct call cannot borrow multiple mutable record pointer parameters"
                .to_string(),
        );
    }
    for (borrow_index, borrowed_name) in &mutable_record_borrows {
        if args.iter().enumerate().any(|(index, arg)| {
            index != *borrow_index && expr_mentions_var(arg, borrowed_name)
        }) {
            return Err(format!(
                "mutable record pointer call argument {borrowed_name} cannot have a sibling argument that reads the same record"
            ));
        }
    }
    let side_effect_args = side_effect_call_args(args)?;
    for (index, arg) in args.iter().enumerate() {
        if !side_effect_args.is_empty() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            for (_, assigned_var) in &side_effect_args {
                if expr_mentions_var(arg, assigned_var) {
                    return Err(format!(
                        "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                    ));
                }
            }
            validate_bounded_call_arg_with_context(arg, false, Some(context))
        } else {
            validate_bounded_call_arg_with_context(arg, true, Some(context))
        }
        .map_err(|detail| format!("call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn is_direct_record_scalar_member_call_arg(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Member { .. } => true,
        IrExpr::Cast { expr, .. } | IrExpr::LValueToRValue { expr, .. } => {
            is_direct_record_scalar_member_call_arg(expr)
        }
        _ => false,
    }
}

fn validate_bounded_side_effect_call_args(args: &[IrExpr]) -> Result<Vec<(usize, &str)>, String> {
    let side_effect_args = side_effect_call_args(args)?;
    for (side_effect_index, assigned_var) in &side_effect_args {
        for (index, arg) in args.iter().enumerate() {
            if index == *side_effect_index {
                continue;
            }
            if expr_mentions_var(arg, assigned_var) {
                return Err(format!(
                    "side-effect call argument cannot be combined with sibling argument reading modified variable {assigned_var}"
                ));
            }
        }
    }
    Ok(side_effect_args)
}

fn validate_bounded_call_arg(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
) -> Result<(), String> {
    validate_bounded_call_arg_with_context(expr, allow_immediate_nested_call, None)
}

fn validate_bounded_call_arg_with_context(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                if emit_opaque_void_pointer_type(ty).is_some() {
                    return Ok(());
                }
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::Var { name, ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                if emit_opaque_void_pointer_type(ty).is_some() {
                    return Ok(());
                }
                if let Some(context) = context {
                    if validate_mutable_record_pointer_call_arg(name, ty, context).is_ok() {
                        return Ok(());
                    }
                    if validate_raw_direct_call_pointer_arg(name, ty, context).is_ok() {
                        return Ok(());
                    }
                }
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::NullPtr { ty, .. } => validate_null_pointer_call_arg(ty),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_bounded_call_arg_with_context(lhs, false, context)?;
            validate_bounded_call_arg_with_context(rhs, false, context)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. } => {
            validate_bounded_call_arg_with_context(operand, false, context)
        }
        IrExpr::ArrayToPointerDecay { target, expr, .. } => {
            validate_array_decay_direct_call_arg(target, expr).map(|_| ())
        }
        IrExpr::FunctionToPointerDecay { target, expr, .. } => {
            validate_function_pointer_decay_call_arg(target, expr).map(|_| ())
        }
        IrExpr::Conditional { .. } => {
            Err("conditional call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Index { base, index, .. } => {
            validate_bounded_call_arg_with_context(base, false, context)?;
            validate_bounded_call_arg_with_context(index, false, context)
        }
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => validate_direct_record_scalar_member_call_arg(
            base, field, ty, *is_arrow, context,
        ),
        IrExpr::ArrayLiteral { .. } => {
            Err("array literal arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if allow_immediate_nested_call => {
            validate_bounded_nested_call_arg(callee, args, ty, context)
        }
        IrExpr::Call { .. } => {
            Err("nested call expressions are outside the bounded call subset".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("call arguments cannot use increment/decrement value semantics".to_string())
        }
        IrExpr::Deref { .. } => {
            Err("call arguments cannot use dereference value semantics".to_string())
        }
        IrExpr::AddrOf { operand, ty, .. } => {
            validate_local_record_address_call_arg(operand, ty).map(|_| ())
        }
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

fn validate_mutable_record_pointer_call_arg(
    name: &str,
    ty: &IrType,
    context: &EmitContext,
) -> Result<(), String> {
    if !context.is_mutable_record_pointer_write_param(name) {
        return Err(format!(
            "mutable record pointer call argument {name} lacks ownership evidence"
        ));
    }
    mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "mutable record pointer call argument {name} has unsupported type {}",
            type_label(ty)
        )
    })?;
    if context.is_nullable_pointer_param(name) {
        return Err(format!(
            "nullable mutable record pointer {name} cannot be passed to a direct call"
        ));
    }
    Ok(())
}

fn validate_direct_record_scalar_member_call_arg(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    is_arrow: bool,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    if !is_integer_type(ty) {
        return Err(format!(
            "direct record call argument field {field} must be a fixed-width integer scalar, got {}",
            type_label(ty)
        ));
    }
    emit_scalar_type(ty)
        .map_err(|detail| format!("direct record call argument field {field} has {detail}"))?;
    let IrExpr::Var {
        name: root_name,
        ty: root_ty,
        ..
    } = base
    else {
        return Err(
            "direct record scalar member call argument base must be a direct DeclRef root"
                .to_string(),
        );
    };

    let record_ty = if is_arrow {
        let context = context.ok_or_else(|| {
            "direct record pointer scalar member call argument requires readonly/noalias context"
                .to_string()
        })?;
        if context.is_nullable_pointer_param(root_name) {
            return Err(format!(
                "nullable record pointer param {root_name} cannot be a direct scalar member call argument"
            ));
        }
        readonly_record_pointer_read_pointee_type(root_name, root_ty, context).ok_or_else(|| {
            format!(
                "record pointer call argument base {root_name} lacks readonly/noalias read proof for {}",
                type_label(root_ty)
            )
        })?
    } else {
        root_ty
    };
    let IrTypeKind::Record {
        name: record_name,
        fields: Some(fields),
    } = &record_ty.kind
    else {
        return Err(format!(
            "direct record scalar member call argument base {root_name} is not a complete record type"
        ));
    };
    let declared = fields
        .iter()
        .find(|declared| declared.name == field)
        .ok_or_else(|| format!("complete record {record_name} has no field {field}"))?;
    if !is_integer_type(&declared.ty) {
        return Err(format!(
            "direct record call argument field {record_name}.{field} is not a fixed-width integer scalar"
        ));
    }
    emit_scalar_type(&declared.ty).map_err(|detail| {
        format!("direct record call argument field {record_name}.{field} has {detail}")
    })?;
    if !types_match_ignoring_spelling(ty, &declared.ty) {
        return Err(format!(
            "direct record call argument field {record_name}.{field} type {} does not match declared type {}",
            type_label(ty),
            type_label(&declared.ty)
        ));
    }
    Ok(())
}

fn validate_null_pointer_call_arg(ty: &IrType) -> Result<(), String> {
    if matches!(&ty.kind, IrTypeKind::Pointer { .. }) {
        return Ok(());
    }
    Err(format!(
        "null pointer call argument type {} is not a pointer",
        type_label(ty)
    ))
}

fn validate_raw_direct_call_pointer_arg(
    name: &str,
    ty: &IrType,
    context: &EmitContext,
) -> Result<(), String> {
    if !should_emit_raw_direct_call_pointer_param(name, ty, context) {
        return Err(format!(
            "raw direct call pointer argument {name} lacks direct call provenance"
        ));
    }
    emit_raw_direct_call_pointer_param_type(ty).ok_or_else(|| {
        format!(
            "raw direct call pointer argument {name} has unsupported type {}",
            type_label(ty)
        )
    })?;
    Ok(())
}

fn validate_array_decay_direct_call_arg<'a>(
    target: &IrType,
    expr: &'a IrExpr,
) -> Result<ArrayDecayDirectCallArg<'a>, String> {
    if matches!(expr, IrExpr::ArrayLiteral { .. }) {
        let bytes = byte_string_array_literal_values(expr)?;
        let target_element = byte_string_pointer_element_type(target)?;
        emit_scalar_type(target_element).map_err(|detail| {
            format!("string literal array-to-pointer decay target element has {detail}")
        })?;
        return Ok(ArrayDecayDirectCallArg::ByteStringLiteral(bytes));
    }

    let target_element = readonly_pointer_slice_element_type(target).ok_or_else(|| {
        format!(
            "array-to-pointer decay call argument target {} must be a readonly integer pointer",
            type_label(target)
        )
    })?;
    let IrExpr::Var {
        name,
        ty: array_ty,
        ..
    } = expr
    else {
        return Err(
            "array-to-pointer decay call argument must be a direct fixed array variable"
                .to_string(),
        );
    };
    let array_element = fixed_integer_array_element_type(array_ty).ok_or_else(|| {
        format!(
            "array-to-pointer decay call argument {name} has unsupported array type {}",
            type_label(array_ty)
        )
    })?;
    let target_element = emit_scalar_type(target_element).map_err(|detail| {
        format!("array-to-pointer decay call argument target element has {detail}")
    })?;
    let array_element = emit_scalar_type(array_element).map_err(|detail| {
        format!("array-to-pointer decay call argument array element has {detail}")
    })?;
    if target_element != array_element {
        return Err(format!(
            "array-to-pointer decay call argument element type {array_element} does not match target element type {target_element}"
        ));
    }
    Ok(ArrayDecayDirectCallArg::Binding(name))
}

enum ArrayDecayDirectCallArg<'a> {
    Binding(&'a str),
    ByteStringLiteral(Vec<u8>),
}

fn byte_string_pointer_element_type(target: &IrType) -> Result<&IrType, String> {
    let IrTypeKind::Pointer { pointee } = &target.kind else {
        return Err(format!(
            "string literal array-to-pointer decay target {} must be an 8-bit integer pointer",
            type_label(target)
        ));
    };
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "string literal array-to-pointer decay target element {} is unsupported",
            type_label(pointee)
        ));
    }
    Ok(pointee)
}

fn byte_string_array_literal_values(expr: &IrExpr) -> Result<Vec<u8>, String> {
    let IrExpr::ArrayLiteral { elements, ty, .. } = expr else {
        return Err(
            "string literal array-to-pointer decay requires a byte array literal".to_string(),
        );
    };
    let IrTypeKind::Array {
        element,
        len: Some(len),
    } = &ty.kind
    else {
        return Err(format!(
            "string literal array-to-pointer decay source {} must be a complete byte array",
            type_label(ty)
        ));
    };
    if *len != elements.len() {
        return Err(format!(
            "string literal array-to-pointer decay source {} length does not match element count",
            type_label(ty)
        ));
    }
    if !is_8_bit_integer_type(element) {
        return Err(format!(
            "string literal array-to-pointer decay element type {} is unsupported",
            type_label(element)
        ));
    }

    let mut bytes = Vec::with_capacity(elements.len());
    for element in elements {
        let IrExpr::LitInt { value, ty, .. } = element else {
            return Err(
                "string literal array-to-pointer decay requires integer literal elements"
                    .to_string(),
            );
        };
        if !is_8_bit_integer_type(ty) {
            return Err(format!(
                "string literal array-to-pointer decay element literal type {} is unsupported",
                type_label(ty)
            ));
        }
        let byte = u8::try_from(*value).map_err(|_| {
            format!("string literal array-to-pointer decay element value {value} exceeds u8")
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

fn validate_local_record_address_call_arg<'a>(
    operand: &'a IrExpr,
    ty: &IrType,
) -> Result<&'a str, String> {
    let pointee = mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "address-of call argument target {} must be a mutable record pointer",
            type_label(ty)
        )
    })?;
    let IrExpr::Var {
        name,
        ty: operand_ty,
        ..
    } = operand
    else {
        return Err(
            "address-of call argument operand must be a direct record variable".to_string(),
        );
    };
    let IrTypeKind::Record { fields, .. } = &operand_ty.kind else {
        return Err(format!(
            "address-of call argument {name} has unsupported operand type {}",
            type_label(operand_ty)
        ));
    };
    if !matches!(fields, Some(fields) if !fields.is_empty()) {
        return Err(format!(
            "address-of call argument {name} requires complete record field inventory"
        ));
    }
    validate_record_value_type_matches(operand_ty, pointee, "address-of call argument")?;
    Ok(name)
}

fn validate_bounded_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    emit_identifier(callee, "nested call callee")?;
    if callee == "strlen" {
        validate_c_strlen_call_shape(args, ty)?;
        return Ok(());
    }
    if callee == "strnlen" {
        validate_c_strnlen_call_shape(args, ty)?;
        return Ok(());
    }
    if callee == "memcmp" {
        validate_c_memcmp_call_shape(args, ty)?;
        return Ok(());
    }
    if mutable_record_pointer_pointee_type(ty).is_some() {
        return validate_record_pointer_return_nested_call_arg(callee, args, ty, context);
    }
    if pointer_return_nested_call_arg_type_allowed(ty) {
        return validate_pointer_return_nested_call_arg(callee, args, ty, context);
    }
    emit_scalar_type(ty).map_err(|detail| format!("nested call result has {detail}"))?;
    validate_bounded_nested_call_plain_args(args, context)
}

fn pointer_return_nested_call_arg_type_allowed(ty: &IrType) -> bool {
    is_readonly_8_bit_pointer_type(ty) || emit_opaque_void_pointer_type(ty).is_some()
}

fn validate_pointer_return_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    emit_identifier(callee, "pointer return nested call callee")?;
    if !pointer_return_nested_call_arg_type_allowed(ty) {
        return Err(format!(
            "pointer return nested call result {} is unsupported",
            type_label(ty)
        ));
    }
    validate_bounded_nested_call_plain_args(args, context)
}

fn validate_bounded_nested_call_plain_args(
    args: &[IrExpr],
    context: Option<&EmitContext>,
) -> Result<(), String> {
    let side_effect_args = validate_bounded_side_effect_call_args(args)?;
    if !side_effect_args.is_empty() {
        for (index, arg) in args.iter().enumerate() {
            if side_effect_args
                .iter()
                .any(|(side_effect_index, _)| *side_effect_index == index)
            {
                continue;
            }
            validate_bounded_call_arg_with_context(arg, false, context)
                .map_err(|detail| format!("nested call arg[{index}] {detail}"))?;
        }
        return Ok(());
    }
    for (index, arg) in args.iter().enumerate() {
        validate_bounded_call_arg_with_context(arg, false, context)
            .map_err(|detail| format!("nested call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn validate_record_pointer_return_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    context: Option<&EmitContext>,
) -> Result<(), String> {
    emit_identifier(callee, "record pointer return nested call callee")?;
    let return_pointee = mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "record pointer return nested call result {} must be a mutable record pointer",
            type_label(ty)
        )
    })?;
    let Some(first_arg) = args.first() else {
        return Err(
            "record pointer return nested call requires an address-of local record first argument"
                .to_string(),
        );
    };
    let IrExpr::AddrOf {
        operand,
        ty: first_arg_ty,
        ..
    } = first_arg
    else {
        return Err(
            "record pointer return nested call first argument must be address-of local record"
                .to_string(),
        );
    };
    let first_pointee = mutable_record_pointer_pointee_type(first_arg_ty).ok_or_else(|| {
        format!(
            "record pointer return nested call first argument target {} must be a mutable record pointer",
            type_label(first_arg_ty)
        )
    })?;
    validate_record_value_type_matches(
        first_pointee,
        return_pointee,
        "record pointer return nested call first argument",
    )?;
    validate_local_record_address_call_arg(operand, first_arg_ty)
        .map_err(|detail| format!("record pointer return nested call first argument {detail}"))?;
    for (index, arg) in args.iter().enumerate().skip(1) {
        if validate_record_pointer_return_call_inner_arg(arg).is_ok() {
            continue;
        }
        validate_bounded_call_arg_with_context(arg, false, context)
            .map_err(|detail| format!("record pointer return nested call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn validate_record_pointer_return_call_inner_arg(arg: &IrExpr) -> Result<(), String> {
    match arg {
        IrExpr::Var { ty, .. } if is_readonly_8_bit_pointer_type(ty) => Ok(()),
        IrExpr::Call {
            callee, args, ty, ..
        } if callee == "strlen" => validate_c_strlen_call_shape(args, ty).map(|_| ()),
        _ => Err("not a record pointer return call inner special case".to_string()),
    }
}

fn find_call_callee(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Call { callee, .. } => Some(callee),
        IrExpr::Binary { lhs, rhs, .. } => find_call_callee(lhs).or_else(|| find_call_callee(rhs)),
        IrExpr::Unary { operand, .. } => find_call_callee(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => find_call_callee(condition)
            .or_else(|| find_call_callee(then_expr))
            .or_else(|| find_call_callee(else_expr)),
        IrExpr::Cast { expr, .. }
        | IrExpr::LValueToRValue { expr, .. }
        | IrExpr::ArrayToPointerDecay { expr, .. }
        | IrExpr::FunctionToPointerDecay { expr, .. } => find_call_callee(expr),
        IrExpr::Index { base, index, .. } => {
            find_call_callee(base).or_else(|| find_call_callee(index))
        }
        IrExpr::Member { base, .. } => find_call_callee(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().find_map(find_call_callee),
        IrExpr::IncDec { target, .. } => find_call_callee(target),
        IrExpr::Deref { ptr, .. } => find_call_callee(ptr),
        IrExpr::AddrOf { operand, .. } => find_call_callee(operand),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => None,
    }
}
