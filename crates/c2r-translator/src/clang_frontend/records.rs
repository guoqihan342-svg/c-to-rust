use std::collections::{BTreeMap, VecDeque};

use serde_json::Value;

use super::{
    clang_type_candidate_spellings, inner, is_simple_c_identifier, lower_type, string_field,
    type_from_ast_type_object,
};
use crate::typed_ir::{IrExpr, IrFunction, IrRecordField, IrStmt, IrType, IrTypeKind};
use crate::TargetAbiProfile;

#[cfg(feature = "typed-ir")]
pub(super) fn record_inventory_from_ast_with_target_abi(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> BTreeMap<String, Vec<IrRecordField>> {
    let mut records = BTreeMap::new();
    collect_record_inventory_from_ast(ast, target_abi, &mut records);
    let mut resolved = BTreeMap::new();
    for name in records.keys() {
        let mut stack = Vec::new();
        if let Some(fields) = resolve_complete_record_fields(name, &records, &mut stack) {
            resolved.insert(name.clone(), fields);
        }
    }
    resolved
}

#[cfg(feature = "typed-ir")]
fn resolve_complete_record_fields(
    name: &str,
    records: &BTreeMap<String, Option<Vec<IrRecordField>>>,
    stack: &mut Vec<String>,
) -> Option<Vec<IrRecordField>> {
    if stack.iter().any(|ancestor| ancestor == name) {
        return None;
    }
    let mut fields = records.get(name)?.as_ref()?.clone();
    stack.push(name.to_string());
    for field in &mut fields {
        if !resolve_complete_record_type(&mut field.ty, records, stack) {
            stack.pop();
            return None;
        }
    }
    stack.pop();
    Some(fields)
}

#[cfg(feature = "typed-ir")]
fn resolve_complete_record_type(
    ty: &mut IrType,
    records: &BTreeMap<String, Option<Vec<IrRecordField>>>,
    stack: &mut Vec<String>,
) -> bool {
    let IrTypeKind::Record { name, fields } = &mut ty.kind else {
        return true;
    };
    if fields.is_none() {
        let Some(resolved) = resolve_complete_record_fields(name, records, stack) else {
            return false;
        };
        *fields = Some(resolved);
    }
    let Some(fields) = fields else {
        return false;
    };
    fields
        .iter_mut()
        .all(|field| resolve_complete_record_type(&mut field.ty, records, stack))
}

#[cfg(feature = "typed-ir")]
fn collect_record_inventory_from_ast(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
    records: &mut BTreeMap<String, Option<Vec<IrRecordField>>>,
) {
    if let Some((name, fields)) = record_inventory_entry_from_record_decl(node, target_abi) {
        match records.entry(name) {
            std::collections::btree_map::Entry::Vacant(entry) => {
                entry.insert(fields);
            }
            std::collections::btree_map::Entry::Occupied(mut entry) => {
                match (entry.get(), &fields) {
                    (Some(existing), Some(new_fields)) if existing == new_fields => {}
                    _ => {
                        entry.insert(None);
                    }
                }
            }
        }
    }
    for child in inner(node) {
        collect_record_inventory_from_ast(child, target_abi, records);
    }
}

#[cfg(feature = "typed-ir")]
fn record_inventory_entry_from_record_decl(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<(String, Option<Vec<IrRecordField>>)> {
    if string_field(node, "kind").as_deref() != Some("RecordDecl")
        || string_field(node, "tagUsed").as_deref() != Some("struct")
        || node.get("completeDefinition").and_then(Value::as_bool) != Some(true)
        || node.get("isImplicit").and_then(Value::as_bool) == Some(true)
    {
        return None;
    }
    let name = string_field(node, "name")?;
    if !is_simple_c_identifier(&name) {
        return None;
    }
    if inner(node)
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("PackedAttr"))
    {
        return Some((name, None));
    }

    let mut fields = Vec::new();
    let mut anonymous_records = VecDeque::new();
    for child in inner(node) {
        match string_field(child, "kind").as_deref() {
            Some("FieldDecl") => {
                if let Some(field) = record_field_from_field_decl(child, target_abi) {
                    fields.push(field);
                    continue;
                };
                let Some(nested_fields) = anonymous_records.pop_front() else {
                    return Some((name, None));
                };
                let Some(field) =
                    record_field_from_anonymous_record_field_decl(&name, child, nested_fields)
                else {
                    return Some((name, None));
                };
                fields.push(field);
            }
            Some("RecordDecl") => {
                let Some(fields) = anonymous_record_fields_from_record_decl(child, target_abi)
                else {
                    return Some((name, None));
                };
                anonymous_records.push_back(fields);
            }
            _ => {}
        }
    }
    if fields.is_empty() || !anonymous_records.is_empty() {
        return Some((name, None));
    }
    Some((name, Some(fields)))
}

#[cfg(feature = "typed-ir")]
fn anonymous_record_fields_from_record_decl(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<Vec<IrRecordField>> {
    if string_field(node, "kind").as_deref() != Some("RecordDecl")
        || string_field(node, "tagUsed").as_deref() != Some("struct")
        || node.get("completeDefinition").and_then(Value::as_bool) != Some(true)
        || node.get("isImplicit").and_then(Value::as_bool) == Some(true)
        || string_field(node, "name").is_some()
    {
        return None;
    }
    if inner(node)
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("PackedAttr"))
    {
        return None;
    }

    let mut fields = Vec::new();
    for child in inner(node) {
        match string_field(child, "kind").as_deref() {
            Some("FieldDecl") => {
                let field = record_field_from_field_decl(child, target_abi)?;
                fields.push(field);
            }
            Some("RecordDecl") => return None,
            _ => {}
        }
    }
    (!fields.is_empty()).then_some(fields)
}

#[cfg(feature = "typed-ir")]
fn record_field_from_anonymous_record_field_decl(
    parent_name: &str,
    field: &Value,
    fields: Vec<IrRecordField>,
) -> Option<IrRecordField> {
    let field_name = string_field(field, "name")?;
    if !is_simple_c_identifier(&field_name) || fields.is_empty() {
        return None;
    }
    let type_object = field.get("type")?;
    let spelled = clang_type_candidate_spellings(type_object)
        .into_iter()
        .find(|candidate| candidate.trim_start().starts_with("struct (unnamed "))?;
    let nested_name = format!("{parent_name}_{field_name}");
    if !is_simple_c_identifier(&nested_name) {
        return None;
    }
    Some(IrRecordField {
        name: field_name,
        ty: IrType {
            spelled,
            canonical: format!("struct {nested_name}"),
            kind: IrTypeKind::Record {
                name: nested_name,
                fields: Some(fields),
            },
            is_const: false,
            width_bits: None,
            source_span: None,
        },
    })
}

#[cfg(feature = "typed-ir")]
fn record_field_from_field_decl(
    field: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<IrRecordField> {
    if field.get("isBitfield").and_then(Value::as_bool) == Some(true) {
        return None;
    }
    if inner(field)
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("PackedAttr"))
    {
        return None;
    }
    let name = string_field(field, "name")?;
    if !is_simple_c_identifier(&name) {
        return None;
    }
    let type_object = field.get("type")?;
    let spellings = clang_type_candidate_spellings(type_object);
    if spellings
        .iter()
        .any(|qual_type| qual_type.split_whitespace().any(|part| part == "volatile"))
    {
        return None;
    }
    let clang_ty = type_from_ast_type_object(type_object, target_abi).ok()?;
    let ty = lower_type(&clang_ty).ok()?;
    if !matches!(ty.kind, IrTypeKind::Integer { .. })
        && !is_opaque_void_pointer_ir_type(&ty)
        && !is_complete_fixed_integer_array_ir_type(&ty)
        && !is_named_record_ir_type(&ty, &spellings)
    {
        return None;
    }
    Some(IrRecordField { name, ty })
}

#[cfg(feature = "typed-ir")]
fn is_named_record_ir_type(ty: &IrType, spellings: &[String]) -> bool {
    let IrTypeKind::Record { name, .. } = &ty.kind else {
        return false;
    };
    if spellings
        .iter()
        .any(|spelling| spelling.contains("(unnamed "))
    {
        return false;
    }
    is_simple_c_identifier(name)
        && spellings.iter().any(|spelling| {
            let spelling = spelling.trim();
            let spelling = spelling.strip_prefix("const ").unwrap_or(spelling);
            spelling
                .strip_prefix("struct ")
                .is_some_and(|record_name| record_name.trim() == name)
        })
}

#[cfg(feature = "typed-ir")]
fn is_complete_fixed_integer_array_ir_type(ty: &IrType) -> bool {
    matches!(
        &ty.kind,
        IrTypeKind::Array {
            element,
            len: Some(_)
        } if matches!(element.kind, IrTypeKind::Integer { .. })
    )
}

#[cfg(feature = "typed-ir")]
fn is_opaque_void_pointer_ir_type(ty: &IrType) -> bool {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return false;
    };
    matches!(pointee.kind, IrTypeKind::Void)
}

#[cfg(feature = "typed-ir")]
pub(super) fn attach_record_inventory_to_function(
    function: &mut IrFunction,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    attach_record_inventory_to_type(&mut function.return_type, inventory);
    for param in &mut function.params {
        attach_record_inventory_to_type(&mut param.ty, inventory);
    }
    for stmt in &mut function.body {
        attach_record_inventory_to_stmt(stmt, inventory);
    }
}

#[cfg(feature = "typed-ir")]
/// Recursively attaches discovered record fields to statement-local IR types.
///
/// Clang skeleton lowering may initially carry only a record name; this pass
/// enriches matching types from the translation-unit inventory before emission.
/// It does not infer missing layouts, so absent inventory remains a later
/// fail-closed type or member-access error.
fn attach_record_inventory_to_stmt(
    stmt: &mut IrStmt,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match stmt {
        IrStmt::Decl { ty, init, .. } => {
            attach_record_inventory_to_type(ty, inventory);
            if let Some(init) = init {
                attach_record_inventory_to_expr(init, inventory);
            }
        }
        IrStmt::Assign { target, value, .. } => {
            attach_record_inventory_to_expr(target, inventory);
            attach_record_inventory_to_expr(value, inventory);
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            for stmt in then_body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
            for stmt in else_body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::While {
            condition, body, ..
        }
        | IrStmt::DoWhile {
            condition, body, ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            for stmt in body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            for stmt in init {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
            if let Some(condition) = condition {
                attach_record_inventory_to_expr(condition, inventory);
            }
            if let Some(step) = step {
                attach_record_inventory_to_stmt(step, inventory);
            }
            for stmt in body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                attach_record_inventory_to_expr(value, inventory);
            }
        }
        IrStmt::Expr { expr, .. } => attach_record_inventory_to_expr(expr, inventory),
        IrStmt::RecordMemset { destination, .. } => {
            attach_record_inventory_to_expr(destination, inventory)
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_expr(
    expr: &mut IrExpr,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
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
        | IrExpr::AddrOf { ty, .. } => attach_record_inventory_to_type(ty, inventory),
        IrExpr::Cast { target, .. }
        | IrExpr::LValueToRValue { target, .. }
        | IrExpr::ArrayToPointerDecay { target, .. }
        | IrExpr::FunctionToPointerDecay { target, .. } => {
            attach_record_inventory_to_type(target, inventory)
        }
        IrExpr::Unsupported { .. } => {}
    }

    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            attach_record_inventory_to_expr(lhs, inventory);
            attach_record_inventory_to_expr(rhs, inventory);
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => attach_record_inventory_to_expr(operand, inventory),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            attach_record_inventory_to_expr(then_expr, inventory);
            attach_record_inventory_to_expr(else_expr, inventory);
        }
        IrExpr::Index { base, index, .. } => {
            attach_record_inventory_to_expr(base, inventory);
            attach_record_inventory_to_expr(index, inventory);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                attach_record_inventory_to_expr(element, inventory);
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                attach_record_inventory_to_expr(arg, inventory);
            }
        }
        IrExpr::Member { base, .. } => attach_record_inventory_to_expr(base, inventory),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_type(
    ty: &mut IrType,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match &mut ty.kind {
        IrTypeKind::Pointer { pointee } => attach_record_inventory_to_type(pointee, inventory),
        IrTypeKind::Array { element, .. } => attach_record_inventory_to_type(element, inventory),
        IrTypeKind::Record { name, fields } => {
            if fields.is_none() {
                if let Some(record_fields) = inventory.get(name) {
                    *fields = Some(record_fields.clone());
                }
            }
        }
        IrTypeKind::Void
        | IrTypeKind::Integer { .. }
        | IrTypeKind::Function
        | IrTypeKind::Unsupported { .. } => {}
    }
}
