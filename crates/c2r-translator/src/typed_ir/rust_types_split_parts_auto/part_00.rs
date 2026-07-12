use super::ir::{IrExpr, IrGlobal, IrIncDecOp, IrRecordField, IrType, IrTypeKind};

pub(super) fn expr_type(expr: &IrExpr) -> Option<&IrType> {
    match expr {
        IrExpr::LitInt { ty, .. }
        | IrExpr::NullPtr { ty, .. }
        | IrExpr::Var { ty, .. }
        | IrExpr::Binary { ty, .. }
        | IrExpr::Unary { ty, .. }
        | IrExpr::Conditional { ty, .. }
        | IrExpr::Index { ty, .. }
        | IrExpr::ArrayLiteral { ty, .. }
        | IrExpr::Call { ty, .. }
        | IrExpr::Member { ty, .. }
        | IrExpr::IncDec { ty, .. }
        | IrExpr::Deref { ty, .. }
        | IrExpr::AddrOf { ty, .. } => Some(ty),
        IrExpr::MutableVoidPointerAddress { target, .. } => Some(target),
        IrExpr::Cast { target, .. }
        | IrExpr::LValueToRValue { target, .. }
        | IrExpr::ArrayToPointerDecay { target, .. }
        | IrExpr::FunctionToPointerDecay { target, .. } => Some(target),
        IrExpr::Unsupported { .. } => None,
    }
}

pub(super) fn null_pointer_comparison_var<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a str, &'a IrType)> {
    match (lhs, rhs) {
        (
            IrExpr::Var {
                name,
                ty: pointer_ty,
                ..
            },
            IrExpr::NullPtr { ty: null_ty, .. },
        ) if matches!(pointer_ty.kind, IrTypeKind::Pointer { .. })
            && matches!(null_ty.kind, IrTypeKind::Pointer { .. }) =>
        {
            Some((name.as_str(), pointer_ty))
        }
        (
            IrExpr::NullPtr { ty: null_ty, .. },
            IrExpr::Var {
                name,
                ty: pointer_ty,
                ..
            },
        ) if matches!(pointer_ty.kind, IrTypeKind::Pointer { .. })
            && matches!(null_ty.kind, IrTypeKind::Pointer { .. }) =>
        {
            Some((name.as_str(), pointer_ty))
        }
        _ => None,
    }
}

pub(super) fn is_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { .. })
}

pub(super) fn is_unsigned_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { signed: false, .. })
}

pub(super) fn is_unsigned_8_bit_integer_type(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    )
}

pub(super) fn is_signed_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { signed: true, .. })
}

pub(super) fn readonly_pointer_slice_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } if pointee.is_const && is_integer_type(pointee) => {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

pub(super) fn readonly_record_pointer_pointee_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee }
            if pointee.is_const && matches!(pointee.kind, IrTypeKind::Record { .. }) =>
        {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

pub(super) fn mutable_record_pointer_pointee_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee }
            if !pointee.is_const && matches!(pointee.kind, IrTypeKind::Record { .. }) =>
        {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

pub(super) fn is_incomplete_record_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Record { fields: None, .. })
}

pub(super) fn is_incomplete_record_pointer_type(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => is_incomplete_record_type(pointee),
        _ => false,
    }
}

pub(super) fn record_pointer_pointee_type(ty: &IrType) -> Option<&IrType> {
    readonly_record_pointer_pointee_type(ty).or_else(|| mutable_record_pointer_pointee_type(ty))
}

pub(super) fn record_pointer_types_match_ignoring_spelling(lhs: &IrType, rhs: &IrType) -> bool {
    lhs == rhs
        || (same_type_name(&lhs.canonical, &rhs.canonical)
            && matches!(
                (&lhs.kind, &rhs.kind),
                (IrTypeKind::Pointer { .. }, IrTypeKind::Pointer { .. })
            )
            && lhs.is_const == rhs.is_const
            && match (
                record_pointer_pointee_type(lhs),
                record_pointer_pointee_type(rhs),
            ) {
                (Some(lhs_pointee), Some(rhs_pointee)) => {
                    record_types_match_ignoring_spelling(lhs_pointee, rhs_pointee)
                }
                _ => false,
            })
}

fn record_types_match_ignoring_spelling(lhs: &IrType, rhs: &IrType) -> bool {
    lhs == rhs
        || (same_type_name(&lhs.canonical, &rhs.canonical)
            && lhs.is_const == rhs.is_const
            && match (&lhs.kind, &rhs.kind) {
                (
                    IrTypeKind::Record {
                        name: lhs_name,
                        fields: lhs_fields,
                    },
                    IrTypeKind::Record {
                        name: rhs_name,
                        fields: rhs_fields,
                    },
                ) => {
                    lhs_name == rhs_name
                        && record_field_lists_match_ignoring_spelling(lhs_fields, rhs_fields)
                }
                _ => false,
            })
}

fn record_field_lists_match_ignoring_spelling(
    lhs: &Option<Vec<IrRecordField>>,
    rhs: &Option<Vec<IrRecordField>>,
) -> bool {
    match (lhs.as_deref(), rhs.as_deref()) {
        (Some(lhs_fields), Some(rhs_fields)) => {
            lhs_fields.len() == rhs_fields.len()
                && lhs_fields
                    .iter()
                    .zip(rhs_fields.iter())
                    .all(|(lhs_field, rhs_field)| {
                        lhs_field.name == rhs_field.name
                            && types_match_ignoring_spelling(&lhs_field.ty, &rhs_field.ty)
                    })
        }
        (None, None) | (Some(_), None) | (None, Some(_)) => true,
    }
}

pub(super) fn types_match_ignoring_spelling(lhs: &IrType, rhs: &IrType) -> bool {
    lhs == rhs
        || (same_type_name(&lhs.canonical, &rhs.canonical)
            && lhs.is_const == rhs.is_const
            && lhs.width_bits == rhs.width_bits
            && match (&lhs.kind, &rhs.kind) {
                (
                    IrTypeKind::Integer {
                        signed: lhs_signed,
                        width: lhs_width,
                    },
                    IrTypeKind::Integer {
                        signed: rhs_signed,
                        width: rhs_width,
                    },
                ) => lhs_signed == rhs_signed && lhs_width == rhs_width,
                (IrTypeKind::Void, IrTypeKind::Void) => true,
                (IrTypeKind::Pointer { .. }, IrTypeKind::Pointer { .. }) => {
                    pointer_types_match_ignoring_spelling(lhs, rhs)
                }
                (
                    IrTypeKind::Array {
                        element: lhs_element,
                        len: lhs_len,
                    },
                    IrTypeKind::Array {
                        element: rhs_element,
                        len: rhs_len,
                    },
                ) => lhs_len == rhs_len && types_match_ignoring_spelling(lhs_element, rhs_element),
                (IrTypeKind::Record { .. }, IrTypeKind::Record { .. }) => {
                    record_types_match_ignoring_spelling(lhs, rhs)
                }
                (IrTypeKind::Function, IrTypeKind::Function) => true,
                (
                    IrTypeKind::Unsupported { reason: lhs_reason },
                    IrTypeKind::Unsupported { reason: rhs_reason },
                ) => lhs_reason == rhs_reason,
                _ => false,
            })
}

fn pointer_types_match_ignoring_spelling(lhs: &IrType, rhs: &IrType) -> bool {
    let (
        IrTypeKind::Pointer {
            pointee: lhs_pointee,
        },
        IrTypeKind::Pointer {
            pointee: rhs_pointee,
        },
    ) = (&lhs.kind, &rhs.kind)
    else {
        return false;
    };
    types_match_ignoring_spelling(lhs_pointee, rhs_pointee)
}

fn same_type_name(lhs: &str, rhs: &str) -> bool {
    !lhs.trim().is_empty() && lhs.trim() == rhs.trim()
}

pub(super) fn is_readonly_8_bit_pointer_type(ty: &IrType) -> bool {
    matches!(readonly_pointer_slice_element_type(ty), Some(pointee) if is_8_bit_integer_type(pointee))
}

pub(super) fn is_supported_nullable_pointer_type(ty: &IrType) -> bool {
    readonly_pointer_slice_element_type(ty).is_some()
        || readonly_record_pointer_pointee_type(ty).is_some()
}

pub(super) fn validate_nullable_pointer_type(name: &str, ty: &IrType) -> Result<(), String> {
    if is_supported_nullable_pointer_type(ty) {
        return Ok(());
    }
    Err(format!(
        "nullable pointer param {name} has unsupported type {}",
        type_label(ty)
    ))
}

pub(super) fn mutable_pointer_slice_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } if !pointee.is_const && is_integer_type(pointee) => {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

pub(super) fn fixed_integer_array_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Array {
            element,
            len: Some(_),
        } if is_integer_type(element) => Some(element.as_ref()),
        _ => None,
    }
}

pub(super) fn readonly_global_array_element_type(global: &IrGlobal) -> Result<&IrType, String> {
    let IrTypeKind::Array { element, len } = &global.ty.kind else {
        return Err(format!(
            "global {} has unsupported type {}",
            global.name,
            type_label(&global.ty)
        ));
    };
    if !global.ty.is_const {
        return Err(format!("global {} is not readonly const", global.name));
    }
    if len.is_none() {
        return Err(format!("global {} array length is unknown", global.name));
    }
    if !is_integer_type(element) {
        return Err(format!(
            "global {} element type {} is unsupported",
            global.name,
            type_label(element)
        ));
    }
    Ok(element.as_ref())
}
