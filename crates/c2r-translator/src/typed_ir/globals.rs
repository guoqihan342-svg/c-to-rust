fn emit_global_const(global: &IrGlobal) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &global.ty.kind else {
        return Err(format!(
            "global {} has non-array type {}",
            global.name,
            type_label(&global.ty)
        ));
    };
    if !global.ty.is_const {
        return Err(format!("global {} is not readonly const", global.name));
    }
    let Some(len) = len else {
        return Err(format!("global {} array length is unknown", global.name));
    };
    let element_ty = emit_scalar_type(element)
        .map_err(|detail| format!("global {} element has {detail}", global.name))?;
    let values = match &global.init {
        IrGlobalInit::IntegerArray(values) => {
            if values.len() != *len {
                return Err(format!(
                    "global {} initializer length {} does not match array length {len}",
                    global.name,
                    values.len()
                ));
            }
            values
                .iter()
                .map(|value| emit_integer_literal(*value, element))
                .collect::<Result<Vec<_>, _>>()?
                .join(", ")
        }
        IrGlobalInit::Zeroed => {
            let zero = emit_integer_literal(0, element)?;
            return Ok(format!(
                "const {}: [{element_ty}; {len}] = [{zero}; {len}];\n",
                emit_global_const_identifier(&global.name)?
            ));
        }
    };
    Ok(format!(
        "const {}: [{element_ty}; {len}] = [{values}];\n",
        emit_global_const_identifier(&global.name)?
    ))
}

fn emit_return_type(ty: &IrType) -> Result<Option<String>, String> {
    if is_void_type(ty) {
        Ok(None)
    } else if let Some(pointee) = mutable_record_pointer_pointee_type(ty) {
        emit_value_type(pointee).map(|ty| Some(format!("&mut {ty}")))
    } else if let Some(function_pointer_ty) = emit_function_pointer_param_type(ty)? {
        Ok(Some(function_pointer_ty))
    } else if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        Err(format!(
            "pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ))
    } else if let IrTypeKind::Record {
        fields: Some(_), ..
    } = &ty.kind
    {
        emit_value_type(ty).map(Some)
    } else {
        emit_scalar_type(ty).map(Some)
    }
}

fn emit_function_return_type(function: &IrFunction) -> Result<Option<String>, String> {
    if let Some(pointer_ty) = emit_direct_record_pointer_field_return_type(function)? {
        return Ok(Some(pointer_ty));
    }
    emit_return_type(&function.return_type)
}

fn emit_direct_record_pointer_field_return_type(
    function: &IrFunction,
) -> Result<Option<String>, String> {
    let Some(pointer_ty) = emit_record_pointer_field_type(&function.return_type) else {
        return Ok(None);
    };
    let Some(IrStmt::Return {
        value:
            Some(IrExpr::Member {
                base,
                ty,
                is_arrow: true,
                ..
            }),
        ..
    }) = function.body.last()
    else {
        return Ok(None);
    };
    if ty != &function.return_type {
        return Ok(None);
    }
    let IrExpr::Var { ty: base_ty, .. } = base.as_ref() else {
        return Ok(None);
    };
    readonly_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "record pointer field return base has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    Ok(Some(pointer_ty))
}

fn emit_scalar_type(ty: &IrType) -> Result<String, String> {
    match &ty.kind {
        IrTypeKind::Integer { signed, width } => {
            if is_size_t_type(ty) {
                return Ok("usize".to_string());
            }
            match (*signed, *width) {
                (true, 8) => Ok("i8".to_string()),
                (true, 16) => Ok("i16".to_string()),
                (true, 32) => Ok("i32".to_string()),
                (true, 64) => Ok("i64".to_string()),
                (false, 8) => Ok("u8".to_string()),
                (false, 16) => Ok("u16".to_string()),
                (false, 32) => Ok("u32".to_string()),
                (false, 64) => Ok("u64".to_string()),
                _ => Err(format!("integer type {} is unsupported", type_label(ty))),
            }
        }
        IrTypeKind::Void => Err("void type is only supported as a return type".to_string()),
        IrTypeKind::Pointer { .. } => {
            Err(format!("pointer type {} is unsupported", type_label(ty)))
        }
        IrTypeKind::Array { .. } => Err(format!("array type {} is unsupported", type_label(ty))),
        IrTypeKind::Record { name, .. } => Err(format!("record type {name} is unsupported")),
        IrTypeKind::Function => Err(format!("function type {} is unsupported", type_label(ty))),
        IrTypeKind::Unsupported { reason } => {
            Err(format!("unsupported type {}: {reason}", type_label(ty)))
        }
    }
}

fn emit_fixed_array_type(ty: &IrType) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &ty.kind else {
        return Err(format!("type {} is not an array", type_label(ty)));
    };
    let Some(len) = len else {
        return Err(format!("array type {} has unknown length", type_label(ty)));
    };
    let element_ty =
        emit_scalar_type(element).map_err(|detail| format!("array element has {detail}"))?;
    Ok(format!("[{element_ty}; {len}]"))
}

fn emit_array_literal(
    elements: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &ty.kind else {
        return Err(format!("{path} type {} is not an array", type_label(ty)));
    };
    let Some(len) = len else {
        return Err(format!("{path} array length is unknown"));
    };
    if elements.len() != *len {
        return Err(format!(
            "{path} element count {} does not match array length {len}",
            elements.len()
        ));
    }
    emit_scalar_type(element).map_err(|detail| format!("{path} element has {detail}"))?;
    let emitted = elements
        .iter()
        .enumerate()
        .map(|(index, element_expr)| {
            validate_expr_matches_type(element_expr, element, &format!("{path} element[{index}]"))?;
            let emitted = emit_expr(element_expr, symbols, context)
                .map_err(|detail| format!("{path} element[{index}] {detail}"))?;
            Ok(emitted)
        })
        .collect::<Result<Vec<_>, String>>()?
        .join(", ");
    Ok(format!("[{emitted}]"))
}
