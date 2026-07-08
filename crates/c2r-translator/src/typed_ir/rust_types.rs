use super::ir::{IrExpr, IrGlobal, IrIncDecOp, IrType, IrTypeKind};

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

pub(super) fn validate_global_expr_type(global: &IrGlobal, ty: &IrType) -> Result<(), String> {
    if &global.ty == ty {
        Ok(())
    } else {
        Err(format!(
            "global {} type {} does not match expression type {}",
            global.name,
            type_label(&global.ty),
            type_label(ty)
        ))
    }
}

pub(super) fn is_c_int_type(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    )
}

pub(super) fn is_c_bool_type(ty: &IrType) -> bool {
    ty.canonical == "_Bool"
        && matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 8
            }
        )
}

pub(super) fn is_void_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Void)
}

pub(super) fn is_c_memset_discarded_result_type(ty: &IrType) -> bool {
    is_void_type(ty) || is_mutable_void_pointer(ty)
}

pub(super) fn is_c_memcpy_discarded_result_type(ty: &IrType) -> bool {
    is_void_type(ty) || is_mutable_void_pointer(ty)
}

pub(super) fn is_mutable_void_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            !pointee.is_const && matches!(pointee.kind, IrTypeKind::Void)
        }
        _ => false,
    }
}

pub(super) fn is_const_void_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            pointee.is_const && matches!(pointee.kind, IrTypeKind::Void)
        }
        _ => false,
    }
}

pub(super) fn is_size_t_type(ty: &IrType) -> bool {
    is_size_t_type_name(&ty.spelled) || is_size_t_type_name(&ty.canonical)
}

pub(super) fn is_size_t_type_name(name: &str) -> bool {
    matches!(name, "size_t" | "__size_t" | "usize")
}

pub(super) fn type_label(ty: &IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        ty.spelled.clone()
    } else if !ty.canonical.trim().is_empty() {
        ty.canonical.clone()
    } else {
        format!("{:?}", ty.kind)
    }
}

pub(super) fn emit_identifier(name: &str, context: &str) -> Result<String, String> {
    if is_rust_identifier(name) && !is_rust_keyword(name) {
        Ok(name.to_string())
    } else {
        Err(format!("{context} identifier {name:?} is unsupported"))
    }
}

pub(super) fn emit_global_const_identifier(name: &str) -> Result<String, String> {
    let mut output = String::new();
    let mut previous_was_underscore = false;
    for character in name.chars() {
        if character.is_ascii_alphanumeric() {
            output.push(character.to_ascii_uppercase());
            previous_was_underscore = false;
        } else if character == '_' && !previous_was_underscore {
            output.push('_');
            previous_was_underscore = true;
        } else {
            return Err(format!("global identifier {name:?} is unsupported"));
        }
    }
    while output.ends_with('_') {
        output.pop();
    }
    if output.is_empty()
        || output
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_digit())
    {
        return Err(format!("global identifier {name:?} is unsupported"));
    }
    Ok(output)
}

pub(super) fn emit_record_type_name(name: &str) -> Result<String, String> {
    if !is_rust_identifier(name) || is_rust_keyword(name) {
        return Err(format!("record type name {name:?} is unsupported"));
    }
    let mut output = String::new();
    let mut uppercase_next = true;
    for character in name.chars() {
        if character == '_' {
            uppercase_next = true;
            continue;
        }
        if !character.is_ascii_alphanumeric() {
            return Err(format!("record type name {name:?} is unsupported"));
        }
        if uppercase_next {
            output.push(character.to_ascii_uppercase());
            uppercase_next = false;
        } else {
            output.push(character);
        }
    }
    if output.is_empty()
        || output
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_digit())
        || is_rust_keyword(&output)
    {
        return Err(format!("record type name {name:?} is unsupported"));
    }
    Ok(output)
}

pub(super) fn is_rust_identifier(name: &str) -> bool {
    if name == "_" {
        return false;
    }
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|character| character == '_' || character.is_ascii_alphanumeric())
}

pub(super) fn is_rust_keyword(name: &str) -> bool {
    matches!(
        name,
        "as" | "async"
            | "await"
            | "break"
            | "const"
            | "continue"
            | "crate"
            | "dyn"
            | "else"
            | "enum"
            | "extern"
            | "false"
            | "fn"
            | "for"
            | "if"
            | "impl"
            | "in"
            | "let"
            | "loop"
            | "match"
            | "mod"
            | "move"
            | "mut"
            | "pub"
            | "ref"
            | "return"
            | "self"
            | "Self"
            | "static"
            | "struct"
            | "super"
            | "trait"
            | "true"
            | "type"
            | "union"
            | "unsafe"
            | "use"
            | "where"
            | "while"
            | "abstract"
            | "become"
            | "box"
            | "do"
            | "final"
            | "macro"
            | "override"
            | "priv"
            | "try"
            | "typeof"
            | "unsized"
            | "virtual"
            | "yield"
    )
}

pub(super) fn is_u8(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    )
}

pub(super) fn is_8_bit_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { width: 8, .. })
}

pub(super) fn is_usize(ty: &IrType) -> bool {
    is_size_t_type(ty)
        || matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        )
}

pub(super) fn is_c_strlen_result_type(ty: &IrType) -> bool {
    is_c_size_argument_type(ty)
}

pub(super) fn is_c_size_argument_type(ty: &IrType) -> bool {
    is_size_t_type(ty) || is_desugared_c_size_integer_type(ty)
}

fn is_desugared_c_size_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { signed: false, .. })
        && (is_desugared_c_size_integer_type_name(&ty.spelled)
            || is_desugared_c_size_integer_type_name(&ty.canonical))
}

fn is_desugared_c_size_integer_type_name(name: &str) -> bool {
    matches!(name, "unsigned long" | "unsigned long long")
}

pub(super) fn is_u8_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => is_u8(pointee),
        _ => false,
    }
}

pub(super) fn is_post_inc_var(expr: &IrExpr, expected_name: &str) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if var_name(target) == Some(expected_name)
    )
}

pub(super) fn is_post_inc_expr(expr: &IrExpr) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if matches!(target.as_ref(), IrExpr::Var { .. })
    )
}

pub(super) fn var_name(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}
