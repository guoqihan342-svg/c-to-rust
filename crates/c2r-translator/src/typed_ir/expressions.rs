fn emit_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match expr {
        IrExpr::LitInt { value, ty, .. } => emit_integer_literal(*value, ty),
        IrExpr::NullPtr { .. } => {
            Err("null pointer literal is only supported in pointer null comparisons".to_string())
        }
        IrExpr::Var { name, ty, .. } => {
            if let Some(global) = context.readonly_global(name) {
                validate_global_expr_type(global, ty)?;
                return context.global_rust_name(name);
            }
            if !symbols.contains(name) {
                return Err(format!("var {name} is not declared"));
            }
            emit_value_type(ty).map_err(|detail| format!("var {name} has {detail}"))?;
            emit_identifier(name, "var")
        }
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            if let Some(expr) = emit_short_circuit_value_expr(op, lhs, rhs, ty, symbols, context)? {
                return Ok(expr);
            }
            if let Some(expr) = emit_comparison_value_expr(op, lhs, rhs, ty, symbols, context)? {
                return Ok(expr);
            }
            let op_token = emit_binary_op(op)?;
            validate_binary_operand_types(op_token, lhs, rhs, ty)?;
            validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)?;
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("binary rhs {detail}"))?;
            Ok(emit_binary_result_expr(op, op_token, &lhs, &rhs, ty))
        }
        IrExpr::Unary {
            op, operand, ty, ..
        } => match op {
            IrUnOp::Neg => {
                validate_signed_unary_minus_operand(operand, ty)?;
                let operand = emit_expr(operand, symbols, context)
                    .map_err(|detail| format!("unary minus operand {detail}"))?;
                Ok(format!("(-{operand})"))
            }
            IrUnOp::Not => emit_logical_not_value_expr(operand, ty, symbols, context),
            IrUnOp::BitNot => {
                validate_expr_matches_type(operand, ty, "bitnot operand")?;
                let operand = emit_expr(operand, symbols, context)
                    .map_err(|detail| format!("bitnot operand {detail}"))?;
                Ok(format!("!{operand}"))
            }
        },
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
            ..
        } => emit_conditional_value_expr(condition, then_expr, else_expr, ty, symbols, context),
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!("cast target {} is unsupported", type_label(target)));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| "cast source type is unsupported".to_string())?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target =
                emit_scalar_type(target).map_err(|detail| format!("cast target has {detail}"))?;
            let expr = emit_expr(expr, symbols, context)
                .map_err(|detail| format!("cast expr {detail}"))?;
            Ok(format!("({expr} as {target})"))
        }
        IrExpr::LValueToRValue { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "lvalue-to-rvalue target {} is unsupported",
                    type_label(target)
                ));
            }
            let source_type = expr_type(expr)
                .ok_or_else(|| "lvalue-to-rvalue source type is unsupported".to_string())?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "lvalue-to-rvalue source {} is unsupported",
                    type_label(source_type)
                ));
            }
            validate_expr_matches_type(expr, target, "lvalue-to-rvalue expr")?;
            emit_expr(expr, symbols, context)
                .map_err(|detail| format!("lvalue-to-rvalue expr {detail}"))
        }
        IrExpr::ArrayToPointerDecay { .. } => {
            Err("array-to-pointer decay requires explicit lowering evidence".to_string())
        }
        IrExpr::FunctionToPointerDecay { .. } => Err(
            "function-to-pointer decay creates a function pointer value and requires explicit function-pointer lowering evidence".to_string(),
        ),
        IrExpr::Index {
            base, index, ty, ..
        } => emit_index_expr(base, index, ty, symbols, context),
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => emit_member_expr(base, field, ty, *is_arrow, symbols, context),
        IrExpr::ArrayLiteral { .. } => Err(
            "array literal expression is only supported as a declaration initializer".to_string(),
        ),
        IrExpr::Call {
            callee, args, ty, ..
        } => emit_call_expr(callee, args, ty, symbols, context),
        IrExpr::IncDec { .. } => Err("inc/dec expression is unsupported".to_string()),
        IrExpr::Deref { ptr, ty, .. } => {
            emit_readonly_pointer_deref_expr(ptr, ty, symbols, context)
        }
        IrExpr::AddrOf { .. } => Err("address-of expression is unsupported".to_string()),
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported expression {node}: {reason}"))
        }
    }
}

fn emit_readonly_pointer_deref_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(expr) = emit_readonly_pointer_add_deref_expr(ptr, ty, symbols, context)? {
        return Ok(expr);
    }
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Err("deref pointer must be Var".to_string());
    };
    if !symbols.contains(ptr_name) {
        return Err(format!("deref pointer {ptr_name} is not declared"));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereferenced in the bounded emitter"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "deref pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("deref element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "deref pointer")?;
    Ok(format!("{ptr_name}[0usize]"))
}

fn emit_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    is_arrow: bool,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if is_arrow {
        if let Some(expr) =
            emit_mutable_record_pointer_member_expr(base, field, ty, symbols, context)?
        {
            return Ok(expr);
        }
        return emit_readonly_record_pointer_member_expr(base, field, ty, symbols, context);
    }
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("member expression base must be a record variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!("member base {base_name} is not declared"));
    }
    if !matches!(base_ty.kind, IrTypeKind::Record { .. }) {
        return Err(format!(
            "member base {base_name} has unsupported type {}",
            type_label(base_ty)
        ));
    }
    emit_scalar_type(ty).map_err(|detail| format!("member field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "member base")?;
    let field = emit_identifier(field, "member field")?;
    Ok(format!("{base_name}.{field}"))
}

fn emit_mutable_record_pointer_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Ok(None);
    };
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Ok(None);
    }
    if !symbols.contains(base_name) {
        return Err(format!("arrow member base {base_name} is not declared"));
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_scalar_type(ty)
        .map_err(|detail| format!("mutable arrow member field {field} has {detail}"))?;
    if !context.is_mutable_record_pointer_read_field(base_name, field) {
        return Err(format!(
            "mutable record pointer field {base_name}.{field} lacks definite assignment evidence"
        ));
    }
    let base_name = emit_identifier(base_name, "mutable arrow member base")?;
    let field = emit_identifier(field, "mutable arrow member field")?;
    Ok(Some(format!("{base_name}.{field}")))
}

fn emit_readonly_record_pointer_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("arrow member expression base must be a record pointer variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!("arrow member base {base_name} is not declared"));
    }
    readonly_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_scalar_type(ty).map_err(|detail| format!("arrow member field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "arrow member base")?;
    let field = emit_identifier(field, "arrow member field")?;
    if context.is_nullable_pointer_param(&base_name) {
        return Ok(format!("{base_name}.unwrap().{field}"));
    }
    Ok(format!("{base_name}.{field}"))
}

fn emit_readonly_pointer_add_deref_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: add_ty,
        ..
    } = ptr
    else {
        return Ok(None);
    };
    let Some((base, index)) = readonly_pointer_add_operands(lhs, rhs) else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("deref pointer add base must be Var".to_string());
    };
    if add_ty != base_ty {
        return Err(format!(
            "deref pointer add result type {} does not match base type {}",
            type_label(add_ty),
            type_label(base_ty)
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!(
            "deref pointer add base {base_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(base_name) {
        return Err(format!(
            "nullable pointer param {base_name} cannot be offset-dereferenced in the bounded emitter"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "deref pointer add base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("deref element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let index_ty = expr_type(index)
        .ok_or_else(|| "deref pointer add index type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "deref pointer add index type {} is unsupported",
            type_label(index_ty)
        ));
    }
    validate_readonly_pointer_add_index_expr(index)?;
    let base = emit_identifier(base_name, "deref pointer add base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("deref pointer add index {detail}"))?;
    Ok(Some(format!("{base}[{index} as usize]")))
}

fn validate_readonly_pointer_add_index_expr(expr: &IrExpr) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } | IrExpr::Var { ty, .. } => {
            if is_integer_type(ty) {
                Ok(())
            } else {
                Err(format!(
                    "deref pointer add index type {} is unsupported",
                    type_label(ty)
                ))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "deref pointer add index cast target {} is unsupported",
                    type_label(target)
                ));
            }
            validate_readonly_pointer_add_index_expr(expr)
        }
        IrExpr::LValueToRValue { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "deref pointer add index lvalue-to-rvalue target {} is unsupported",
                    type_label(target)
                ));
            }
            validate_readonly_pointer_add_index_expr(expr)
        }
        IrExpr::ArrayToPointerDecay { .. } => {
            Err("deref pointer add index cannot use array-to-pointer decay".to_string())
        }
        IrExpr::FunctionToPointerDecay { .. } => {
            Err("deref pointer add index cannot use function-to-pointer decay".to_string())
        }
        IrExpr::Call { callee, .. } => Err(format!(
            "deref pointer add index call expression {callee} is unsupported"
        )),
        IrExpr::Conditional { .. } => {
            Err("deref pointer add index cannot use conditional expression".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("deref pointer add index cannot use increment/decrement".to_string())
        }
        IrExpr::Deref { .. } => Err("deref pointer add index cannot use dereference".to_string()),
        IrExpr::Binary { .. } => {
            Err("deref pointer add index cannot use compound expression".to_string())
        }
        IrExpr::Unary { .. } => {
            Err("deref pointer add index cannot use unary expression".to_string())
        }
        IrExpr::Index { .. } => {
            Err("deref pointer add index cannot use index expression".to_string())
        }
        IrExpr::Member { .. } => {
            Err("deref pointer add index cannot use member expression".to_string())
        }
        IrExpr::AddrOf { .. } => {
            Err("deref pointer add index cannot use address-of expression".to_string())
        }
        IrExpr::NullPtr { .. } => {
            Err("deref pointer add index cannot use null pointer".to_string())
        }
        IrExpr::ArrayLiteral { .. } => {
            Err("deref pointer add index cannot use array literal".to_string())
        }
        IrExpr::Unsupported { node, reason, .. } => Err(format!(
            "deref pointer add index unsupported expression {node}: {reason}"
        )),
    }
}

fn readonly_pointer_add_operands<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a IrExpr, &'a IrExpr)> {
    match (expr_type(lhs), expr_type(rhs)) {
        (Some(lhs_ty), Some(rhs_ty))
            if readonly_pointer_slice_element_type(lhs_ty).is_some() && is_integer_type(rhs_ty) =>
        {
            Some((lhs, rhs))
        }
        (Some(lhs_ty), Some(rhs_ty))
            if is_integer_type(lhs_ty) && readonly_pointer_slice_element_type(rhs_ty).is_some() =>
        {
            Some((rhs, lhs))
        }
        _ => None,
    }
}

fn mutable_pointer_add_operands<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a IrExpr, &'a IrExpr)> {
    match (expr_type(lhs), expr_type(rhs)) {
        (Some(lhs_ty), Some(rhs_ty))
            if mutable_pointer_slice_element_type(lhs_ty).is_some() && is_integer_type(rhs_ty) =>
        {
            Some((lhs, rhs))
        }
        (Some(lhs_ty), Some(rhs_ty))
            if is_integer_type(lhs_ty) && mutable_pointer_slice_element_type(rhs_ty).is_some() =>
        {
            Some((rhs, lhs))
        }
        _ => None,
    }
}

fn emit_call_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let callee = emit_identifier(callee, "call callee")?;
    if callee == "assert" {
        return emit_c_assert_call_expr(args, ty, symbols, context);
    }
    if callee == "abs" {
        return emit_c_abs_call_expr(args, ty, symbols, context);
    }
    if callee == "strlen" {
        return emit_c_strlen_call_expr(args, ty, symbols, context);
    }
    if callee == "strnlen" {
        return emit_c_strnlen_call_expr(args, ty, symbols, context);
    }
    if callee == "memcmp" {
        return emit_c_memcmp_call_expr(args, ty, symbols, context);
    }
    if reserved_c_macro_or_stdlib_callee(&callee) {
        return Err(format!(
            "call callee \"{callee}\" is reserved C macro/stdlib/extern surface and requires explicit lowering or extern binding"
        ));
    }
    if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        return Err(format!(
            "call result has pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ));
    }
    if !is_void_type(ty) {
        emit_scalar_type(ty).map_err(|detail| format!("call result has {detail}"))?;
    }
    validate_bounded_call_args(args, context)?;
    let args = args
        .iter()
        .enumerate()
        .map(|(index, arg)| {
            emit_call_arg_expr(arg, symbols, context)
                .map_err(|detail| format!("call arg[{index}] {detail}"))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    Ok(format!("{callee}({args})"))
}

fn emit_call_arg_expr(
    arg: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match arg {
        IrExpr::FunctionToPointerDecay { target, expr, .. } => {
            emit_function_pointer_decay_call_arg(target, expr)
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if mutable_record_pointer_pointee_type(ty).is_some() => {
            emit_record_pointer_return_call_arg_expr(callee, args, ty, symbols, context)
        }
        IrExpr::Var { name, ty, .. } if emit_opaque_void_pointer_type(ty).is_some() => {
            emit_opaque_pointer_call_arg_var(name, symbols, context)
        }
        IrExpr::Var { name, ty, .. }
            if should_emit_raw_direct_call_pointer_param(name, ty, context) =>
        {
            emit_raw_direct_call_pointer_arg_var(name, ty, symbols, context)
        }
        IrExpr::AddrOf { operand, ty, .. } => {
            emit_local_record_address_call_arg(operand, ty, symbols)
        }
        _ => emit_expr(arg, symbols, context),
    }
}

fn emit_record_pointer_return_call_arg_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    validate_record_pointer_return_nested_call_arg(callee, args, ty, Some(context))?;
    let callee = emit_identifier(callee, "record pointer return call argument callee")?;
    let args = args
        .iter()
        .enumerate()
        .map(|(index, arg)| {
            emit_record_pointer_return_call_inner_arg_expr(arg, symbols, context)
                .map_err(|detail| format!("record pointer return call arg[{index}] {detail}"))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    Ok(format!("{callee}({args})"))
}

fn emit_record_pointer_return_call_inner_arg_expr(
    arg: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match arg {
        IrExpr::Var { name, ty, .. } if is_readonly_8_bit_pointer_type(ty) => {
            emit_readonly_byte_pointer_const_void_call_arg_var(name, symbols, context)
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if callee == "strlen" => emit_c_strlen_call_expr(args, ty, symbols, context),
        _ => emit_call_arg_expr(arg, symbols, context),
    }
}

fn emit_local_record_address_call_arg(
    operand: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
) -> Result<String, String> {
    let name = validate_local_record_address_call_arg(operand, ty)?;
    if !symbols.contains(name) {
        return Err(format!("address-of call argument {name} is not declared"));
    }
    let name = emit_identifier(name, "address-of call argument")?;
    Ok(format!("&mut {name}"))
}

fn emit_raw_direct_call_pointer_arg_var(
    name: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "raw direct call pointer argument {name} is not declared"
        ));
    }
    validate_raw_direct_call_pointer_arg(name, ty, context)?;
    emit_identifier(name, "raw direct call pointer argument")
}

fn emit_opaque_pointer_call_arg_var(
    name: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "opaque pointer call argument {name} is not declared"
        ));
    }
    if !context.is_opaque_pointer_call_arg_param(name) {
        return Err(format!(
            "opaque pointer call argument {name} requires direct call argument provenance"
        ));
    }
    emit_identifier(name, "opaque pointer call argument")
}

fn emit_readonly_byte_pointer_const_void_call_arg_var(
    name: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !symbols.contains(name) {
        return Err(format!(
            "readonly byte pointer call argument {name} is not declared"
        ));
    }
    let name = emit_identifier(name, "readonly byte pointer call argument")?;
    let receiver = if context.is_nullable_pointer_param(&name) {
        format!("{name}.unwrap()")
    } else {
        name
    };
    Ok(format!("{receiver}.as_ptr() as *const core::ffi::c_void"))
}

fn emit_function_pointer_decay_call_arg(target: &IrType, expr: &IrExpr) -> Result<String, String> {
    let name = validate_function_pointer_decay_call_arg(target, expr)?;
    emit_identifier(name, "function pointer decay argument")
}

fn validate_function_pointer_decay_call_arg<'a>(
    target: &IrType,
    expr: &'a IrExpr,
) -> Result<&'a str, String> {
    let Some(target_signature) = emit_function_pointer_param_type(target)? else {
        return Err(format!(
            "function-to-pointer decay target {} is outside the simple function pointer argument subset",
            type_label(target)
        ));
    };
    let IrTypeKind::Pointer { pointee } = &target.kind else {
        return Err(format!(
            "function-to-pointer decay target {} is not a function pointer",
            type_label(target)
        ));
    };
    let IrExpr::Var { name, ty, .. } = expr else {
        return Err(
            "function-to-pointer decay argument must be a direct function name".to_string(),
        );
    };
    if !matches!(ty.kind, IrTypeKind::Function) {
        return Err(format!(
            "function-to-pointer decay argument {name} has unsupported source type {}",
            type_label(ty)
        ));
    }
    let source_signature = emit_function_pointer_signature_type(&ty.spelled).map_err(|detail| {
        format!(
            "function-to-pointer decay argument {name} source type {} is unsupported: {detail}",
            type_label(ty)
        )
    })?;
    let pointee_signature =
        emit_function_pointer_signature_type(&pointee.spelled).map_err(|detail| {
            format!(
                "function-to-pointer decay target pointee {} is unsupported: {detail}",
                type_label(pointee)
            )
        })?;
    if source_signature != target_signature || source_signature != pointee_signature {
        return Err(format!(
            "function-to-pointer decay argument {name} signature {source_signature} does not match target {target_signature}"
        ));
    }
    Ok(name)
}

fn emit_c_assert_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_void_type(ty) {
        return Err(format!(
            "C assert model requires void result type, got {}",
            type_label(ty)
        ));
    }
    let [condition] = args else {
        return Err(format!(
            "C assert model requires exactly one condition argument, got {}",
            args.len()
        ));
    };
    validate_bounded_call_arg_with_context(condition, false, Some(context))
        .map_err(|detail| format!("C assert condition {detail}"))?;
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("C assert condition {detail}"))?;
    Ok(format!("assert!({condition})"))
}

fn emit_c_abs_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_c_int_type(ty) {
        return Err(format!(
            "C abs(int) model requires i32 result type, got {}",
            type_label(ty)
        ));
    }
    let [arg] = args else {
        return Err(format!(
            "C abs(int) model requires exactly one i32 argument, got {}",
            args.len()
        ));
    };
    validate_bounded_call_arg_with_context(arg, false, Some(context))
        .map_err(|detail| format!("C abs argument {detail}"))?;
    let arg_ty = expr_type(arg).ok_or_else(|| "C abs argument type is unsupported".to_string())?;
    if !is_c_int_type(arg_ty) {
        return Err(format!(
            "C abs(int) argument must be i32, got {}",
            type_label(arg_ty)
        ));
    }
    let arg =
        emit_expr(arg, symbols, context).map_err(|detail| format!("C abs argument {detail}"))?;
    Ok(format!(
        "{arg}.checked_abs().expect(\"C abs(int) precondition violated\")"
    ))
}

fn emit_c_strlen_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let name = validate_c_strlen_call_shape(args, ty)?;
    let name = emit_identifier(name, "C strlen argument")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C strlen argument {name} is not a function parameter or local binding"
        ));
    }
    let receiver = if context.is_nullable_pointer_param(&name) {
        format!("{name}.unwrap()")
    } else {
        name
    };
    Ok(format!(
        "{receiver}.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")"
    ))
}

fn validate_c_strlen_call_shape<'a>(args: &'a [IrExpr], ty: &IrType) -> Result<&'a str, String> {
    if !is_c_strlen_result_type(ty) {
        return Err(format!(
            "C strlen model requires size_t/usize result type, got {}",
            type_label(ty)
        ));
    }
    let [arg] = args else {
        return Err(format!(
            "C strlen model requires exactly one string pointer argument, got {}",
            args.len()
        ));
    };
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err("C strlen argument must be a direct readonly pointer parameter".to_string());
    };
    let pointee = readonly_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "C strlen argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "C strlen argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}

fn emit_c_strnlen_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let (name, max) = validate_c_strnlen_call_shape(args, ty)?;
    let name = emit_identifier(name, "C strnlen argument")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C strnlen argument {name} is not a function parameter or local binding"
        ));
    }
    let max =
        emit_expr(max, symbols, context).map_err(|detail| format!("C strnlen size {detail}"))?;
    Ok(format!(
        "{{ let bytes = {name}.get(..({max} as usize)).expect(\"C strnlen precondition violated\"); bytes.iter().position(|&byte| byte == 0).unwrap_or(bytes.len()) }}"
    ))
}

fn validate_c_strnlen_call_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a IrExpr), String> {
    if !is_c_strlen_result_type(ty) {
        return Err(format!(
            "C strnlen model requires size_t/usize result type, got {}",
            type_label(ty)
        ));
    }
    let [arg, max] = args else {
        return Err(format!(
            "C strnlen model requires exactly one string pointer and one size argument, got {}",
            args.len()
        ));
    };
    let name = validate_direct_readonly_8_bit_pointer_arg(arg, "C strnlen")?;
    let max_ty =
        expr_type(max).ok_or_else(|| "C strnlen size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(max_ty) {
        return Err(format!(
            "C strnlen size argument must be size_t/usize, got {}",
            type_label(max_ty)
        ));
    }
    validate_bounded_call_arg(max, false).map_err(|detail| format!("C strnlen size {detail}"))?;
    Ok((name, max))
}

fn emit_c_memcmp_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let (left, right, count) = validate_c_memcmp_call_shape(args, ty)?;
    let left = emit_identifier(left, "C memcmp left argument")?;
    let right = emit_identifier(right, "C memcmp right argument")?;
    if !symbols.contains(&left) {
        return Err(format!(
            "C memcmp left argument {left} is not a function parameter or local binding"
        ));
    }
    if !symbols.contains(&right) {
        return Err(format!(
            "C memcmp right argument {right} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memcmp size {detail}"))?;
    Ok(format!(
        "{{ let left_bytes = {left}.get(..({count} as usize)).expect(\"C memcmp precondition violated\"); let right_bytes = {right}.get(..({count} as usize)).expect(\"C memcmp precondition violated\"); left_bytes.iter().zip(right_bytes.iter()).find_map(|(&left_byte, &right_byte)| ((left_byte as u8) != (right_byte as u8)).then_some(((left_byte as u8) as i32) - ((right_byte as u8) as i32))).unwrap_or(0) }}"
    ))
}

fn validate_c_memcmp_call_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a str, &'a IrExpr), String> {
    if !is_c_int_type(ty) {
        return Err(format!(
            "C memcmp model requires i32 result type, got {}",
            type_label(ty)
        ));
    }
    let [left, right, count] = args else {
        return Err(format!(
            "C memcmp model requires exactly two readonly byte pointers and one size argument, got {}",
            args.len()
        ));
    };
    let left = validate_direct_readonly_8_bit_pointer_arg(left, "C memcmp left")?;
    let right = validate_direct_readonly_8_bit_pointer_arg(right, "C memcmp right")?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memcmp size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memcmp size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memcmp size {detail}"))?;
    Ok((left, right, count))
}

fn validate_direct_readonly_8_bit_pointer_arg<'a>(
    arg: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err(format!(
            "{context} argument must be a direct readonly pointer parameter"
        ));
    };
    let pointee = readonly_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "{context} argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "{context} argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}
