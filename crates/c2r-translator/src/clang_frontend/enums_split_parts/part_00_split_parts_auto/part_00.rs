use std::collections::BTreeMap;

use serde_json::Value;

use super::{
    inner, is_simple_c_identifier, nonzero_width, string_field, type_from_ast_type_object,
    ClangExprSkeleton, ClangFrontendError, ClangFunctionSkeleton, ClangStmtSkeleton, ClangTypeKind,
    ClangTypeSkeleton,
};
use crate::TargetAbiProfile;

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub(super) struct ClangEnumConstantLiteral {
    name: String,
    pub(super) value: u64,
    spelling: String,
    ty: ClangTypeSkeleton,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Default)]
pub(super) struct EnumConstantInventory {
    by_id: BTreeMap<String, Result<ClangEnumConstantLiteral, String>>,
    by_name: BTreeMap<String, Option<Result<ClangEnumConstantLiteral, String>>>,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Default)]
pub(super) struct EnumTypeInventory {
    by_name: BTreeMap<String, Result<ClangTypeSkeleton, String>>,
}

#[cfg(feature = "typed-ir")]
pub(super) fn enum_constant_inventory_from_ast(ast: &Value) -> EnumConstantInventory {
    let mut inventory = EnumConstantInventory::default();
    collect_enum_constant_inventory_from_ast(ast, &mut inventory);
    inventory
}

#[cfg(feature = "typed-ir")]
pub(super) fn enum_type_inventory_from_ast(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> EnumTypeInventory {
    let mut inventory = EnumTypeInventory::default();
    collect_enum_type_inventory_from_ast(ast, target_abi, &mut inventory);
    collect_typedef_enum_type_inventory_from_ast(ast, ast, target_abi, &mut inventory);
    inventory
}

#[cfg(feature = "typed-ir")]
fn collect_enum_type_inventory_from_ast(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
    inventory: &mut EnumTypeInventory,
) {
    if string_field(node, "kind").as_deref() == Some("EnumDecl") {
        if let Some(name) = enum_decl_name(node) {
            let entry = enum_type_from_decl(node, &name, target_abi);
            match inventory.by_name.entry(name) {
                std::collections::btree_map::Entry::Vacant(slot) => {
                    slot.insert(entry);
                }
                std::collections::btree_map::Entry::Occupied(mut slot) => {
                    let _previous = slot.insert(Err(
                        "duplicate EnumDecl name in clang AST; enum type lowering requires unique declaration provenance"
                            .to_string(),
                    ));
                }
            }
        }
    }
    for child in inner(node) {
        collect_enum_type_inventory_from_ast(child, target_abi, inventory);
    }
}

#[cfg(feature = "typed-ir")]
fn collect_typedef_enum_type_inventory_from_ast(
    node: &Value,
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
    inventory: &mut EnumTypeInventory,
) {
    if string_field(node, "kind").as_deref() == Some("TypedefDecl")
        && node.get("isImplicit").and_then(Value::as_bool) != Some(true)
    {
        if let Some((alias, enum_decl, allow_missing_complete_definition)) =
            typedef_enum_alias_decl(node, ast)
        {
            let entry = enum_type_from_decl_with_options(
                enum_decl,
                &alias,
                target_abi,
                allow_missing_complete_definition,
            );
            insert_enum_type_inventory_entry(inventory, alias, entry);
        }
    }
    for child in inner(node) {
        collect_typedef_enum_type_inventory_from_ast(child, ast, target_abi, inventory);
    }
}

#[cfg(feature = "typed-ir")]
fn insert_enum_type_inventory_entry(
    inventory: &mut EnumTypeInventory,
    name: String,
    entry: Result<ClangTypeSkeleton, String>,
) {
    match inventory.by_name.entry(name) {
        std::collections::btree_map::Entry::Vacant(slot) => {
            slot.insert(entry);
        }
        std::collections::btree_map::Entry::Occupied(mut slot) => {
            let _previous = slot.insert(Err(
                "duplicate enum type name in clang AST; enum type lowering requires unique declaration provenance"
                    .to_string(),
            ));
        }
    }
}

#[cfg(feature = "typed-ir")]
fn typedef_enum_alias_decl<'a>(
    typedef_decl: &'a Value,
    ast: &'a Value,
) -> Option<(String, &'a Value, bool)> {
    let alias = string_field(typedef_decl, "name")?;
    if !is_simple_c_identifier(&alias) {
        return None;
    }
    if let Some(enum_decl) = inner(typedef_decl)
        .iter()
        .find(|child| string_field(child, "kind").as_deref() == Some("EnumDecl"))
    {
        return Some((alias, enum_decl, true));
    }
    let enum_decl_id = nested_enum_type_decl_id(typedef_decl)?;
    find_decl_by_id(ast, &enum_decl_id)
        .filter(|decl| string_field(decl, "kind").as_deref() == Some("EnumDecl"))
        .map(|decl| {
            let allow_missing_complete_definition = enum_decl_name(decl).is_none();
            (alias, decl, allow_missing_complete_definition)
        })
}

#[cfg(feature = "typed-ir")]
fn nested_enum_type_decl_id(node: &Value) -> Option<String> {
    if string_field(node, "kind").as_deref() == Some("EnumType") {
        if let Some(enum_decl_id) = node.get("decl").and_then(|decl| {
            if string_field(decl, "kind").as_deref() == Some("EnumDecl") {
                string_field(decl, "id")
            } else {
                None
            }
        }) {
            return Some(enum_decl_id);
        }
    }
    if let Some(enum_decl_id) = node.get("ownedTagDecl").and_then(|decl| {
        if string_field(decl, "kind").as_deref() == Some("EnumDecl") {
            string_field(decl, "id")
        } else {
            None
        }
    }) {
        return Some(enum_decl_id);
    }
    inner(node)
        .iter()
        .find_map(nested_enum_type_decl_id)
}

#[cfg(feature = "typed-ir")]
fn find_decl_by_id<'a>(node: &'a Value, id: &str) -> Option<&'a Value> {
    if string_field(node, "id").as_deref() == Some(id) {
        return Some(node);
    }
    inner(node)
        .iter()
        .find_map(|child| find_decl_by_id(child, id))
}

#[cfg(feature = "typed-ir")]
fn enum_decl_name(node: &Value) -> Option<String> {
    let name = string_field(node, "name")?;
    if is_simple_c_identifier(&name) {
        Some(name)
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
fn enum_type_from_decl(
    node: &Value,
    name: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, String> {
    enum_type_from_decl_with_options(node, name, target_abi, false)
}

#[cfg(feature = "typed-ir")]
fn enum_type_from_decl_with_options(
    node: &Value,
    name: &str,
    target_abi: Option<&TargetAbiProfile>,
    allow_missing_complete_definition: bool,
) -> Result<ClangTypeSkeleton, String> {
    let Some(target_abi) = target_abi else {
        return Err(format!(
            "EnumDecl {name} requires target ABI profile evidence before enum-typed scalar lowering"
        ));
    };
    if nonzero_width(target_abi.int_width) != Some(32) {
        return Err(format!(
            "EnumDecl {name} requires target ABI int_width=32 for the current enum-typed scalar subset"
        ));
    }
    match node.get("completeDefinition").and_then(Value::as_bool) {
        Some(true) => {}
        None if allow_missing_complete_definition => {}
        _ => {
            return Err(format!(
                "EnumDecl {name} is not a complete definition; enum type lowering requires all constants"
            ));
        }
    }
    if node.get("isImplicit").and_then(Value::as_bool) == Some(true) {
        return Err(format!(
            "EnumDecl {name} is implicit; enum type lowering requires explicit source provenance"
        ));
    }

    let constants = inner(node)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("EnumConstantDecl"))
        .collect::<Vec<_>>();
    if constants.is_empty() {
        return Err(format!(
            "EnumDecl {name} has no constants; enum type lowering requires an explicit i32 value domain"
        ));
    }

    for literal in enum_constant_literals_from_ordered_decls(&constants)? {
        if !matches!(
            literal.ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ) {
            return Err(format!(
                "EnumDecl {name} constant {} has type {}; only explicit int-backed enums are currently supported",
                literal.name, literal.ty.spelled
            ));
        }
        if literal.value > i32::MAX as u64 {
            return Err(format!(
                "EnumDecl {name} constant {} value {} does not fit the current i32 enum subset",
                literal.name, literal.spelling
            ));
        }
    }

    Ok(ClangTypeSkeleton {
        spelled: format!("enum {name}"),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    })
}
