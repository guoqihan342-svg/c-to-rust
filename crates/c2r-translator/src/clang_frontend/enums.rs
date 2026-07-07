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
    let enum_decl_id = inner(typedef_decl)
        .iter()
        .find(|child| string_field(child, "kind").as_deref() == Some("EnumType"))
        .and_then(|enum_type| enum_type.get("decl"))
        .and_then(|decl| {
            if string_field(decl, "kind").as_deref() == Some("EnumDecl") {
                string_field(decl, "id")
            } else {
                None
            }
        })?;
    find_decl_by_id(ast, &enum_decl_id)
        .filter(|decl| string_field(decl, "kind").as_deref() == Some("EnumDecl"))
        .map(|decl| {
            let allow_missing_complete_definition = enum_decl_name(decl).is_none();
            (alias, decl, allow_missing_complete_definition)
        })
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

    let infer_sequential_values = allow_missing_complete_definition
        && constants
            .iter()
            .all(|constant| !enum_constant_has_constant_expr(constant));

    for (index, constant) in constants.iter().enumerate() {
        let literal = enum_constant_literal_from_decl_with_inferred_value(
            constant,
            infer_sequential_values.then_some(index as u64),
        )?;
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

#[cfg(feature = "typed-ir")]
fn collect_enum_constant_inventory_from_ast(node: &Value, inventory: &mut EnumConstantInventory) {
    if string_field(node, "kind").as_deref() == Some("EnumConstantDecl") {
        let entry = enum_constant_literal_from_decl(node);
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
    for child in inner(node) {
        collect_enum_constant_inventory_from_ast(child, inventory);
    }
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

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_stmts(
    statements: &mut [ClangStmtSkeleton],
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    for statement in statements {
        rewrite_supported_enum_types_in_stmt(statement, inventory)?;
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_stmt(
    statement: &mut ClangStmtSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    match statement {
        ClangStmtSkeleton::Decl { ty, init, .. } => {
            rewrite_supported_enum_type(ty, inventory)?;
            if let Some(init) = init {
                rewrite_supported_enum_types_in_expr(init, inventory)?;
            }
        }
        ClangStmtSkeleton::Assign { target, value } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_types_in_expr(value, inventory)?;
        }
        ClangStmtSkeleton::CompoundAssign {
            target,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            ..
        } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_types_in_expr(value, inventory)?;
            rewrite_supported_enum_type(result_ty, inventory)?;
            rewrite_supported_enum_type(compute_lhs_ty, inventory)?;
            rewrite_supported_enum_type(compute_result_ty, inventory)?;
        }
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_stmts(then_body, inventory)?;
            rewrite_supported_enum_types_in_stmts(else_body, inventory)?;
        }
        ClangStmtSkeleton::While { condition, body } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
        }
        ClangStmtSkeleton::DoWhile { body, condition } => {
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
        }
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => {
            rewrite_supported_enum_types_in_stmts(init, inventory)?;
            if let Some(condition) = condition {
                rewrite_supported_enum_types_in_expr(condition, inventory)?;
            }
            if let Some(step) = step {
                rewrite_supported_enum_types_in_stmt(step, inventory)?;
            }
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
        }
        ClangStmtSkeleton::Return { value } => {
            if let Some(value) = value {
                rewrite_supported_enum_types_in_expr(value, inventory)?;
            }
        }
        ClangStmtSkeleton::Expr { expr } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
        }
        ClangStmtSkeleton::Break
        | ClangStmtSkeleton::Continue
        | ClangStmtSkeleton::Unsupported { .. } => {}
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_expr(
    expr: &mut ClangExprSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::NullPtr { ty } => {
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::SizeOfType { ty, .. } | ClangExprSkeleton::AlignOfType { ty, .. } => {
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Binary { lhs, rhs, ty, .. } => {
            rewrite_supported_enum_types_in_expr(lhs, inventory)?;
            rewrite_supported_enum_types_in_expr(rhs, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Unary { operand, ty, .. } => {
            rewrite_supported_enum_types_in_expr(operand, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_expr(then_expr, inventory)?;
            rewrite_supported_enum_types_in_expr(else_expr, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Cast { expr, target, .. }
        | ClangExprSkeleton::LValueToRValue { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::Call { args, ty, .. } => {
            for arg in args {
                rewrite_supported_enum_types_in_expr(arg, inventory)?;
            }
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::IncDec { target, ty, .. } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Deref { ptr, ty } => {
            rewrite_supported_enum_types_in_expr(ptr, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::AddrOf { operand, ty } => {
            rewrite_supported_enum_types_in_expr(operand, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::ArrayToPointerDecay { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::FunctionToPointerDecay { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::Index { base, index, ty } => {
            rewrite_supported_enum_types_in_expr(base, inventory)?;
            rewrite_supported_enum_types_in_expr(index, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::ArrayLiteral { elements, ty } => {
            for element in elements {
                rewrite_supported_enum_types_in_expr(element, inventory)?;
            }
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Member { base, ty, .. } => {
            rewrite_supported_enum_types_in_expr(base, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Unsupported { .. } => {}
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_type(
    ty: &mut ClangTypeSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    let candidates = enum_type_inventory_candidates(ty);
    if candidates.is_empty() {
        return Ok(());
    }

    for name in &candidates {
        if let Some(entry) = inventory.by_name.get(name) {
            match entry {
                Ok(mapped) => {
                    *ty = mapped.clone();
                    return Ok(());
                }
                Err(reason) => {
                    return Err(ClangFrontendError {
                        kind: "unsupported_clang_type".to_string(),
                        message: format!("enum {name}: {reason}"),
                    });
                }
            }
        }
    }

    let Some(name) = direct_enum_type_name(ty) else {
        return Ok(());
    };
    Err(ClangFrontendError {
        kind: "unsupported_clang_type".to_string(),
        message: format!(
            "enum {name} is not present in the clang enum type inventory; enum type lowering requires a complete EnumDecl"
        ),
    })
}

#[cfg(feature = "typed-ir")]
fn enum_type_inventory_candidates(ty: &ClangTypeSkeleton) -> Vec<String> {
    let mut candidates = Vec::new();
    push_enum_type_inventory_candidate(&mut candidates, &ty.spelled);
    push_enum_type_inventory_candidate(&mut candidates, &ty.canonical);
    candidates
}

#[cfg(feature = "typed-ir")]
fn push_enum_type_inventory_candidate(candidates: &mut Vec<String>, spelling: &str) {
    if let Some(name) = direct_enum_name_from_spelling(spelling)
        .or_else(|| direct_typedef_enum_alias_from_spelling(spelling))
    {
        if !candidates.contains(&name) {
            candidates.push(name);
        }
    }
}

#[cfg(feature = "typed-ir")]
fn direct_enum_type_name(ty: &ClangTypeSkeleton) -> Option<String> {
    direct_enum_name_from_spelling(&ty.spelled)
        .or_else(|| direct_enum_name_from_spelling(&ty.canonical))
}

#[cfg(feature = "typed-ir")]
fn direct_enum_name_from_spelling(spelling: &str) -> Option<String> {
    let name = spelling.trim().strip_prefix("enum ")?.trim();
    if is_simple_c_identifier(name) {
        Some(name.to_string())
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
fn direct_typedef_enum_alias_from_spelling(spelling: &str) -> Option<String> {
    let alias = spelling.trim();
    if is_simple_c_identifier(alias) {
        Some(alias.to_string())
    } else {
        None
    }
}
