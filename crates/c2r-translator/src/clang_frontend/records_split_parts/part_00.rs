use std::collections::{BTreeMap, VecDeque};

use serde_json::Value;

#[cfg(test)]
use super::type_alias_inventory_from_ast;
use super::{
    clang_type_candidate_spellings, inner, is_simple_c_identifier, lower_type, string_field,
    type_from_ast_type_object, type_from_ast_type_object_with_aliases, ClangTypeKind,
    TypeAliasInventory,
};
use crate::typed_ir::{IrExpr, IrFunction, IrRecordField, IrStmt, IrType, IrTypeKind};
use crate::TargetAbiProfile;

#[cfg(all(feature = "typed-ir", test))]
pub(super) fn record_inventory_from_ast_with_target_abi(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> BTreeMap<String, Vec<IrRecordField>> {
    let aliases = type_alias_inventory_from_ast(ast, target_abi);
    record_inventory_from_ast_with_aliases(ast, target_abi, &aliases)
}

#[cfg(feature = "typed-ir")]
pub(super) fn record_inventory_from_ast_with_aliases(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> BTreeMap<String, Vec<IrRecordField>> {
    let mut records = BTreeMap::new();
    collect_record_inventory_from_ast(ast, target_abi, aliases, &mut records);
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
    aliases: &TypeAliasInventory,
    records: &mut BTreeMap<String, Option<Vec<IrRecordField>>>,
) {
    if let Some((name, fields)) = record_inventory_entry_from_record_decl(node, target_abi, aliases)
    {
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
        collect_record_inventory_from_ast(child, target_abi, aliases, records);
    }
}

#[cfg(feature = "typed-ir")]
fn record_inventory_entry_from_record_decl(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
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
                if let Some(field) = record_field_from_field_decl(child, target_abi, aliases) {
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
                let Some(fields) =
                    anonymous_record_fields_from_record_decl(child, target_abi, aliases)
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
    aliases: &TypeAliasInventory,
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
                let field = record_field_from_field_decl(child, target_abi, aliases)?;
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
    aliases: &TypeAliasInventory,
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
    let direct = type_from_ast_type_object(type_object, target_abi).ok();
    let clang_ty = match direct {
        Some(ty) if !matches!(ty.kind, ClangTypeKind::Unsupported { .. }) => ty,
        _ => type_from_ast_type_object_with_aliases(type_object, target_abi, aliases).ok()?,
    };
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
