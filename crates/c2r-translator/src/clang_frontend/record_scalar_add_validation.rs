#[cfg(feature = "typed-ir")]
fn validate_record_scalar_add_target(
    function: &IrFunction,
    target: &NestedRecordTarget<'_>,
) -> Result<(), ClangFrontendError> {
    let target_root_ty = record_scalar_add_target_root_type(function, target)?;
    if !record_scalar_add_types_match(target_root_ty, target.root_ty) {
        return record_scalar_add_error("record scalar add target root parameter type drifted");
    }
    let IrTypeKind::Pointer { pointee } = &target_root_ty.kind else {
        return record_scalar_add_error("record scalar add target root must be a record pointer");
    };
    let IrTypeKind::Record {
        fields: Some(root_fields),
        ..
    } = &pointee.kind
    else {
        return record_scalar_add_error(
            "record scalar add target requires a complete record inventory",
        );
    };
    if pointee.is_const {
        return record_scalar_add_error("record scalar add target record must be mutable");
    }
    let nested = root_fields
        .iter()
        .find(|field| field.name == target.nested_field)
        .ok_or_else(|| record_scalar_add_frontend_error("target nested field is not declared"))?;
    if !record_scalar_add_types_match(&nested.ty, target.nested_ty) {
        return record_scalar_add_error("record scalar add target nested field type drifted");
    }
    let IrTypeKind::Record {
        fields: Some(nested_fields),
        ..
    } = &nested.ty.kind
    else {
        return record_scalar_add_error(
            "record scalar add target nested field requires a complete record inventory",
        );
    };
    let leaf = nested_fields
        .iter()
        .find(|field| field.name == target.leaf_field)
        .ok_or_else(|| record_scalar_add_frontend_error("target leaf field is not declared"))?;
    if !record_scalar_add_types_match(&leaf.ty, target.leaf_ty) || !is_exact_u32(&leaf.ty) {
        return record_scalar_add_error("record scalar add target leaf type drifted from u32");
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn record_scalar_add_target_root_type<'a>(
    function: &'a IrFunction,
    target: &NestedRecordTarget<'_>,
) -> Result<&'a IrType, ClangFrontendError> {
    if let Some(param) = function
        .params
        .iter()
        .find(|param| param.name == target.root_name)
    {
        return Ok(&param.ty);
    }

    let Some(IrStmt::Decl {
        name,
        ty,
        init:
            Some(IrExpr::AddrOf {
                operand,
                ty: address_ty,
                ..
            }),
        ..
    }) = function.body.first()
    else {
        return record_scalar_add_error(
            "record scalar add target root must be a parameter or first direct interior alias",
        );
    };
    let IrExpr::Member {
        base,
        ty: field_ty,
        is_arrow: true,
        ..
    } = operand.as_ref()
    else {
        return record_scalar_add_error(
            "record scalar add local target must directly alias one owner field",
        );
    };
    let IrExpr::Var {
        name: owner_name,
        ty: owner_ty,
        ..
    } = base.as_ref()
    else {
        return record_scalar_add_error(
            "record scalar add local target owner must be a direct parameter",
        );
    };
    let owner_param = function
        .params
        .iter()
        .find(|param| param.name == *owner_name)
        .ok_or_else(|| {
            record_scalar_add_frontend_error(
                "record scalar add local target owner is not a parameter",
            )
        })?;
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return record_scalar_add_error("record scalar add local target must be a pointer");
    };
    if name != target.root_name
        || !record_scalar_add_types_match(ty, target.root_ty)
        || !record_scalar_add_types_match(ty, address_ty)
        || !record_scalar_add_types_match(owner_ty, &owner_param.ty)
        || !record_scalar_add_types_match(pointee, field_ty)
    {
        return record_scalar_add_error("record scalar add local target alias provenance drifted");
    }
    Ok(ty)
}

#[cfg(feature = "typed-ir")]
fn validate_record_scalar_add_source(
    function: &IrFunction,
    source: &RecordFieldRead<'_>,
) -> Result<(), ClangFrontendError> {
    let source_root_ty = record_scalar_add_source_root_type(function, source)?;
    let IrTypeKind::Record {
        fields: Some(fields),
        ..
    } = &source_root_ty.kind
    else {
        return record_scalar_add_error(
            "record scalar add source requires a complete by-value record inventory",
        );
    };
    if !record_scalar_add_types_match(source_root_ty, source.root_ty) {
        return record_scalar_add_error("record scalar add source record type drifted");
    }
    let declared = fields
        .iter()
        .find(|field| field.name == source.field)
        .ok_or_else(|| record_scalar_add_frontend_error("source field is not declared"))?;
    if !record_scalar_add_types_match(&declared.ty, source.field_ty)
        || !is_exact_u32(&declared.ty)
    {
        return record_scalar_add_error("record scalar add source field type drifted from u32");
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn record_scalar_add_source_root_type<'a>(
    function: &'a IrFunction,
    source: &RecordFieldRead<'_>,
) -> Result<&'a IrType, ClangFrontendError> {
    if let Some(param) = function
        .params
        .iter()
        .find(|param| param.name == source.root_name)
    {
        return Ok(&param.ty);
    }

    let matching_locals = function
        .body
        .iter()
        .filter_map(|stmt| match stmt {
            IrStmt::Decl {
                name,
                ty,
                init: Some(init),
                ..
            } if name == source.root_name => {
                let (read_ty, expr) = match init {
                    IrExpr::LValueToRValue { target, expr, .. } => {
                        (Some(target), expr.as_ref())
                    }
                    direct => (None, direct),
                };
                Some((ty, read_ty, expr))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    let [(local_ty, read_ty, IrExpr::Var { name, ty: input_ty, .. })] =
        matching_locals.as_slice()
    else {
        return record_scalar_add_error(
            "record scalar add source must be a parameter or one direct local parameter copy",
        );
    };
    let input_param = function
        .params
        .iter()
        .find(|param| param.name == *name)
        .ok_or_else(|| {
            record_scalar_add_frontend_error(
                "record scalar add local source input is not a parameter",
            )
        })?;
    if !record_scalar_add_types_match(local_ty, source.root_ty)
        || read_ty.is_some_and(|read_ty| !record_scalar_add_types_match(local_ty, read_ty))
        || !record_scalar_add_types_match(local_ty, input_ty)
        || !record_scalar_add_types_match(local_ty, &input_param.ty)
    {
        return record_scalar_add_error("record scalar add local source provenance drifted");
    }
    Ok(local_ty)
}

#[cfg(feature = "typed-ir")]
fn validate_record_scalar_add_extent(
    function: &IrFunction,
    extent_name: &str,
    extent_ty: &IrType,
) -> Result<(), ClangFrontendError> {
    let param = function
        .params
        .iter()
        .find(|param| param.name == extent_name)
        .ok_or_else(|| record_scalar_add_frontend_error("extent is not a parameter"))?;
    if !record_scalar_add_types_match(&param.ty, extent_ty) || !is_exact_u32(&param.ty) {
        return record_scalar_add_error("record scalar add extent type drifted from u32");
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn is_exact_u32(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    )
}

#[cfg(feature = "typed-ir")]
fn record_scalar_add_types_match(lhs: &IrType, rhs: &IrType) -> bool {
    lhs.kind == rhs.kind && lhs.is_const == rhs.is_const && lhs.width_bits == rhs.width_bits
}

#[cfg(feature = "typed-ir")]
fn record_scalar_add_error<T>(message: &str) -> Result<T, ClangFrontendError> {
    Err(record_scalar_add_frontend_error(message))
}

#[cfg(feature = "typed-ir")]
fn record_scalar_add_frontend_error(message: &str) -> ClangFrontendError {
    ClangFrontendError {
        kind: "unsupported_record_scalar_add".to_string(),
        message: message.to_string(),
    }
}
