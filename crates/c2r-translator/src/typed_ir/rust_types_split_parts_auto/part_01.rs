
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
