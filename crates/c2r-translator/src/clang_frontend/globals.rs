#[cfg(feature = "typed-ir")]
fn readonly_globals_from_ast(ast: &Value) -> Result<Vec<IrGlobal>, ClangFrontendError> {
    let enum_constant_inventory = enum_constant_inventory_from_ast(ast);
    readonly_globals_from_ast_with_enum_inventory(ast, &enum_constant_inventory)
}

#[cfg(feature = "typed-ir")]
fn readonly_globals_from_ast_with_enum_inventory(
    ast: &Value,
    enum_constant_inventory: &EnumConstantInventory,
) -> Result<Vec<IrGlobal>, ClangFrontendError> {
    inner(ast)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("VarDecl"))
        .filter_map(|var_decl| {
            readonly_global_from_toplevel_var_decl(var_decl, enum_constant_inventory)
        })
        .collect()
}

#[cfg(feature = "typed-ir")]
fn readonly_global_from_toplevel_var_decl(
    var_decl: &Value,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<Result<IrGlobal, ClangFrontendError>> {
    if string_field(var_decl, "storageClass").as_deref() != Some("static") {
        return None;
    }

    let name = string_field(var_decl, "name")?;
    let clang_ty = type_from_ast_type_object(var_decl.get("type")?, None).ok()?;
    let ClangTypeKind::Array { element, len } = &clang_ty.kind else {
        return None;
    };
    if !clang_type_is_const(&clang_ty)
        || len.is_none()
        || !matches!(element.kind, ClangTypeKind::Integer { .. })
    {
        return None;
    }

    let [initializer] = inner(var_decl) else {
        return None;
    };
    if string_field(initializer, "kind").as_deref() != Some("InitListExpr") {
        return None;
    }

    let array_len = (*len)?;
    let values = integer_literal_init_list_values(initializer, array_len, enum_constant_inventory)?;
    if values.len() != array_len {
        return None;
    }

    Some(lower_type(&clang_ty).map(|ty| IrGlobal {
        name,
        ty,
        init: IrGlobalInit::IntegerArray(values),
        source_span: None,
    }))
}

#[cfg(feature = "typed-ir")]
fn integer_literal_init_list_values(
    init_list: &Value,
    len: usize,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<Vec<u64>> {
    let entries = inner(init_list);
    if entries.is_empty() {
        return integer_literal_array_filler_values(init_list, len, enum_constant_inventory);
    }
    entries
        .iter()
        .map(|entry| integer_literal_init_value(entry, enum_constant_inventory))
        .collect()
}

#[cfg(feature = "typed-ir")]
fn integer_literal_array_filler_values(
    init_list: &Value,
    len: usize,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<Vec<u64>> {
    let filler_entries = array_filler(init_list)?;
    let filler = filler_entries.first()?;
    if string_field(filler, "kind").as_deref() != Some("ImplicitValueInitExpr") {
        return None;
    }
    if filler_entries.len().saturating_sub(1) > len {
        return None;
    }
    let filler_value = integer_literal_init_value(filler, enum_constant_inventory)?;
    let mut values = filler_entries[1..]
        .iter()
        .map(|entry| integer_literal_init_value(entry, enum_constant_inventory))
        .collect::<Option<Vec<_>>>()?;
    while values.len() < len {
        values.push(filler_value);
    }
    Some(values)
}

#[cfg(feature = "typed-ir")]
fn integer_literal_init_value(
    item: &Value,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<u64> {
    match string_field(item, "kind").as_deref() {
        Some("IntegerLiteral") => string_field(item, "value")?.parse::<u64>().ok(),
        Some("DeclRefExpr") => {
            enum_constant_literal_for_decl_ref_expr(item, enum_constant_inventory)
                .ok()
                .map(|literal| literal.value)
        }
        Some("ImplicitValueInitExpr") => {
            let ty = expr_type(item).ok()?;
            if matches!(ty.kind, ClangTypeKind::Integer { .. }) {
                Some(0)
            } else {
                None
            }
        }
        Some("ImplicitCastExpr" | "ParenExpr") => {
            let [operand] = inner(item) else {
                return None;
            };
            integer_literal_init_value(operand, enum_constant_inventory)
        }
        _ => None,
    }
}
