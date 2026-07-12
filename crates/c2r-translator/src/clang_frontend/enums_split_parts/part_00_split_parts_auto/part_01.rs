
#[cfg(feature = "typed-ir")]
fn collect_enum_constant_inventory_from_ast(node: &Value, inventory: &mut EnumConstantInventory) {
    if string_field(node, "kind").as_deref() == Some("EnumDecl") {
        collect_enum_constant_inventory_from_enum_decl(node, inventory);
        for child in inner(node) {
            if string_field(child, "kind").as_deref() != Some("EnumConstantDecl") {
                collect_enum_constant_inventory_from_ast(child, inventory);
            }
        }
        return;
    }
    if string_field(node, "kind").as_deref() == Some("EnumConstantDecl") {
        let entry = enum_constant_literal_from_decl(node);
        insert_enum_constant_inventory_entry(inventory, node, entry);
    }
    for child in inner(node) {
        collect_enum_constant_inventory_from_ast(child, inventory);
    }
}

#[cfg(feature = "typed-ir")]
fn collect_enum_constant_inventory_from_enum_decl(
    node: &Value,
    inventory: &mut EnumConstantInventory,
) {
    let mut next_value = Some(0u64);
    for constant in inner(node)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("EnumConstantDecl"))
    {
        let inferred_value = if enum_constant_has_constant_expr(constant) {
            None
        } else {
            next_value
        };
        let entry = enum_constant_literal_from_decl_with_inferred_value(constant, inferred_value);
        if let Ok(literal) = &entry {
            next_value = literal.value.checked_add(1);
        } else {
            next_value = None;
        }
        insert_enum_constant_inventory_entry(inventory, constant, entry);
    }
}

#[cfg(feature = "typed-ir")]
fn insert_enum_constant_inventory_entry(
    inventory: &mut EnumConstantInventory,
    node: &Value,
    entry: Result<ClangEnumConstantLiteral, String>,
) {
    if let Some(id) = string_field(node, "id") {
        match inventory.by_id.entry(id) {
            std::collections::btree_map::Entry::Vacant(slot) => {
                slot.insert(entry.clone());
            }
            std::collections::btree_map::Entry::Occupied(mut slot) => {
                let _previous = slot.insert(Err(
                    "duplicate EnumConstantDecl id in clang AST; enum constant lowering requires a unique declaration id"
                        .to_string(),
                ));
            }
        }
    }
    if let Some(name) = enum_constant_decl_name(node) {
        match inventory.by_name.entry(name) {
            std::collections::btree_map::Entry::Vacant(slot) => {
                slot.insert(Some(entry));
            }
            std::collections::btree_map::Entry::Occupied(mut slot) => {
                slot.insert(None);
            }
        }
    }
}

#[cfg(feature = "typed-ir")]
fn enum_constant_literals_from_ordered_decls(
    constants: &[&Value],
) -> Result<Vec<ClangEnumConstantLiteral>, String> {
    let mut literals = Vec::new();
    let mut next_value = Some(0u64);
    for constant in constants {
        let inferred_value = if enum_constant_has_constant_expr(constant) {
            None
        } else {
            next_value
        };
        let literal = enum_constant_literal_from_decl_with_inferred_value(constant, inferred_value)?;
        next_value = literal.value.checked_add(1);
        literals.push(literal);
    }
    Ok(literals)
}

#[cfg(feature = "typed-ir")]
fn enum_constant_literal_from_decl(node: &Value) -> Result<ClangEnumConstantLiteral, String> {
    enum_constant_literal_from_decl_with_inferred_value(node, None)
}

#[cfg(feature = "typed-ir")]
fn enum_constant_literal_from_decl_with_inferred_value(
    node: &Value,
    inferred_value: Option<u64>,
) -> Result<ClangEnumConstantLiteral, String> {
    let name = enum_constant_decl_name(node)
        .ok_or_else(|| "EnumConstantDecl is missing name".to_string())?;
    let type_object = node
        .get("type")
        .ok_or_else(|| format!("EnumConstantDecl {name} is missing type.qualType"))?;
    let ty = type_from_ast_type_object(type_object, None).map_err(|error| {
        format!(
            "EnumConstantDecl {name} has unsupported type: {}",
            error.message
        )
    })?;
    if !matches!(ty.kind, ClangTypeKind::Integer { .. }) {
        return Err(format!(
            "EnumConstantDecl {name} type {} is not an integer type; enum type lowering is outside the current skeleton",
            ty.spelled
        ));
    }

    let Some(constant_expr) = inner(node)
        .iter()
        .find(|child| string_field(child, "kind").as_deref() == Some("ConstantExpr"))
    else {
        let Some(value) = inferred_value else {
            return Err(format!(
                "EnumConstantDecl {name} is missing explicit ConstantExpr value; implicit enum values are outside the current clang lowering skeleton"
            ));
        };
        return Ok(ClangEnumConstantLiteral {
            name,
            value,
            spelling: value.to_string(),
            ty,
        });
    };
    let spelling = string_field(constant_expr, "value").ok_or_else(|| {
        format!(
            "EnumConstantDecl {name} is missing explicit ConstantExpr value; computed enum constants are outside the current clang lowering skeleton"
        )
    })?;
    let value = spelling.parse::<u64>().map_err(|error| {
        format!(
            "EnumConstantDecl {name} explicit ConstantExpr value {spelling} is not a supported non-negative u64 integer literal: {error}"
        )
    })?;
    if !enum_constant_has_matching_direct_integer_literal(constant_expr, &spelling) {
        return Err(format!(
            "EnumConstantDecl {name} requires a direct IntegerLiteral child matching explicit ConstantExpr value {spelling}; computed enum constants are outside the current clang lowering skeleton"
        ));
    }

    Ok(ClangEnumConstantLiteral {
        name,
        value,
        spelling,
        ty,
    })
}

#[cfg(feature = "typed-ir")]
fn enum_constant_has_constant_expr(node: &Value) -> bool {
    inner(node)
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("ConstantExpr"))
}

#[cfg(feature = "typed-ir")]
fn enum_constant_has_matching_direct_integer_literal(
    constant_expr: &Value,
    spelling: &str,
) -> bool {
    inner(constant_expr).iter().any(|child| {
        string_field(child, "kind").as_deref() == Some("IntegerLiteral")
            && string_field(child, "value").as_deref() == Some(spelling)
    })
}

#[cfg(feature = "typed-ir")]
fn enum_constant_decl_name(node: &Value) -> Option<String> {
    string_field(node, "name").filter(|name| !name.trim().is_empty())
}

#[cfg(feature = "typed-ir")]
pub(super) fn rewrite_enum_constant_decl_refs_to_integer_literals(
    node: &mut Value,
    inventory: &EnumConstantInventory,
) -> Result<(), ClangFrontendError> {
    if enum_constant_ref_from_decl_ref_expr(node).is_some() {
        let literal = enum_constant_literal_for_decl_ref_expr(node, inventory)?;
        *node = serde_json::json!({
            "kind": "IntegerLiteral",
            "type": {
                "qualType": literal.ty.spelled,
            },
            "value": literal.spelling,
        });
        return Ok(());
    }

    if let Some(children) = node.get_mut("inner").and_then(Value::as_array_mut) {
        for child in children {
            rewrite_enum_constant_decl_refs_to_integer_literals(child, inventory)?;
        }
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn enum_constant_ref_from_decl_ref_expr(node: &Value) -> Option<&Value> {
    if string_field(node, "kind").as_deref() != Some("DeclRefExpr") {
        return None;
    }
    let referenced_decl = node.get("referencedDecl")?;
    if string_field(referenced_decl, "kind").as_deref() == Some("EnumConstantDecl") {
        Some(referenced_decl)
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn enum_constant_literal_for_decl_ref_expr(
    node: &Value,
    inventory: &EnumConstantInventory,
) -> Result<ClangEnumConstantLiteral, ClangFrontendError> {
    let referenced_decl =
        enum_constant_ref_from_decl_ref_expr(node).ok_or_else(|| ClangFrontendError {
            kind: "invalid_decl_ref_expr".to_string(),
            message: "DeclRefExpr is not an EnumConstantDecl reference".to_string(),
        })?;
    let name = enum_constant_decl_name(referenced_decl).ok_or_else(|| ClangFrontendError {
        kind: "invalid_decl_ref_expr".to_string(),
        message: "DeclRefExpr EnumConstantDecl reference is missing name".to_string(),
    })?;
    if let Some(id) = string_field(referenced_decl, "id") {
        let entry = inventory.by_id.get(&id).ok_or_else(|| ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "EnumConstantDecl {name} with id {id} is not present in the clang enum constant inventory"
            ),
        })?;
        return enum_constant_inventory_entry_result(&name, entry);
    }

    match inventory.by_name.get(&name) {
        Some(Some(entry)) => enum_constant_inventory_entry_result(&name, entry),
        Some(None) => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "EnumConstantDecl {name} reference is ambiguous without a declaration id; enum constant lowering requires unique clang provenance"
            ),
        }),
        None => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "EnumConstantDecl {name} is not present in the clang enum constant inventory"
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn enum_constant_inventory_entry_result(
    name: &str,
    entry: &Result<ClangEnumConstantLiteral, String>,
) -> Result<ClangEnumConstantLiteral, ClangFrontendError> {
    match entry {
        Ok(literal) => Ok(literal.clone()),
        Err(reason) => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!("EnumConstantDecl {name}: {reason}"),
        }),
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn rewrite_supported_enum_types_in_function_skeleton(
    function: &mut ClangFunctionSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    rewrite_supported_enum_type(&mut function.return_type, inventory)?;
    for param in &mut function.params {
        rewrite_supported_enum_type(&mut param.ty, inventory)?;
    }
    rewrite_supported_enum_types_in_stmts(&mut function.body, inventory)
}
