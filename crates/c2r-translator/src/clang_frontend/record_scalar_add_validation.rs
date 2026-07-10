#[cfg(feature = "typed-ir")]
fn validate_record_scalar_add_target(
    function: &IrFunction,
    target: &NestedRecordTarget<'_>,
) -> Result<(), ClangFrontendError> {
    let pointer_params = function
        .params
        .iter()
        .filter(|param| matches!(param.ty.kind, IrTypeKind::Pointer { .. }))
        .collect::<Vec<_>>();
    if pointer_params.len() != 1 || pointer_params[0].name != target.root_name {
        return record_scalar_add_error(
            "record scalar add target must be the unique pointer parameter",
        );
    }
    let IrTypeKind::Pointer { pointee } = &target.root_ty.kind else {
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
fn validate_record_scalar_add_source(
    function: &IrFunction,
    source: &RecordFieldRead<'_>,
) -> Result<(), ClangFrontendError> {
    let param = function
        .params
        .iter()
        .find(|param| param.name == source.root_name)
        .ok_or_else(|| record_scalar_add_frontend_error("source is not a parameter"))?;
    let IrTypeKind::Record {
        fields: Some(fields),
        ..
    } = &param.ty.kind
    else {
        return record_scalar_add_error(
            "record scalar add source requires a complete by-value record inventory",
        );
    };
    if !record_scalar_add_types_match(&param.ty, source.root_ty) {
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
