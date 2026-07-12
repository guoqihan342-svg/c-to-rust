use std::collections::BTreeMap;

use serde_json::Value;

use super::{
    inner, is_simple_c_identifier, string_field, ClangExprSkeleton, ClangFrontendError,
    ClangFunctionSkeleton, ClangStmtSkeleton, ClangTypeKind, ClangTypeSkeleton,
};
use crate::TargetAbiProfile;

#[cfg(all(feature = "typed-ir", test))]
pub(super) fn function_return_type(
    qual_type: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    if let Some(return_type) = function_pointer_return_qual_type(qual_type) {
        return type_from_qual_type(&return_type);
    }
    let Some((return_type, _)) = split_function_qual_type(qual_type) else {
        if qual_type.contains("(*") {
            return Err(ClangFrontendError {
                kind: "unsupported_function_type".to_string(),
                message: format!(
                    "function pointer return type requires explicit function-pointer return lowering evidence: {qual_type}"
                ),
            });
        }
        return Err(ClangFrontendError {
            kind: "unsupported_function_type".to_string(),
            message: format!("unsupported function qualType: {qual_type}"),
        });
    };
    type_from_qual_type(return_type.trim())
}

#[cfg(feature = "typed-ir")]
fn function_pointer_return_qual_type(qual_type: &str) -> Option<String> {
    let trimmed = qual_type.trim();
    let marker = "(*(";
    let marker_index = trimmed.find(marker)?;
    let return_type = trimmed[..marker_index].trim();
    if return_type.is_empty() || return_type.contains(['(', ')', '*']) {
        return None;
    }
    let outer_params_open = marker_index + 2;
    let outer_params_close = matching_close_paren(trimmed, outer_params_open)?;
    if trimmed.as_bytes().get(outer_params_close + 1) != Some(&b')') {
        return None;
    }
    let function_params = trimmed[outer_params_close + 2..].trim();
    if !function_params.starts_with('(') || !function_params.ends_with(')') {
        return None;
    }
    Some(format!("{return_type} (*){function_params}"))
}

#[cfg(all(feature = "typed-ir", test))]
pub(super) fn function_return_type_from_type_object(
    type_object: &Value,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_ast_type_object_with_parser(
        type_object,
        function_return_type,
        "invalid_function_decl",
        "FunctionDecl is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_ast_type_object(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    validate_fixed_width_typedef_desugaring(type_object, target_abi)?;
    type_from_ast_type_object_with_parser(
        type_object,
        |qual_type| type_from_qual_type_with_target_abi(qual_type, target_abi),
        "invalid_clang_type",
        "clang type object is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_ast_type_object_with_parser<F>(
    type_object: &Value,
    mut parse: F,
    missing_kind: &str,
    missing_message: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError>
where
    F: FnMut(&str) -> Result<ClangTypeSkeleton, ClangFrontendError>,
{
    let candidates = clang_type_candidate_spellings(type_object);
    if candidates.is_empty() {
        return Err(ClangFrontendError {
            kind: missing_kind.to_string(),
            message: missing_message.to_string(),
        });
    }

    let mut source_unsupported = None;
    let mut canonical_unsupported = None;
    let mut first_error = None;
    for candidate in candidates {
        match parse(&candidate) {
            Ok(ty) if clang_type_is_fully_supported(&ty) => return Ok(ty),
            Ok(ty) => {
                if source_unsupported.is_none() {
                    source_unsupported = Some(ty.clone());
                }
                // Clang orders these from source spelling to desugared/canonical
                // spelling. Preserve the deepest spelling so a later ABI-binding
                // pass can resolve target-dependent canonical integer types.
                canonical_unsupported = Some(ty);
            }
            Err(error) => {
                if first_error.is_none() {
                    first_error = Some(error);
                }
            }
        }
    }

    if let Some(ty) = source_unsupported
        .filter(|ty| is_target_dependent_integer_spelling(&ty.spelled))
        .or(canonical_unsupported)
    {
        Ok(ty)
    } else if let Some(error) = first_error {
        Err(error)
    } else {
        Err(ClangFrontendError {
            kind: missing_kind.to_string(),
            message: missing_message.to_string(),
        })
    }
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_fully_supported(ty: &ClangTypeSkeleton) -> bool {
    match &ty.kind {
        ClangTypeKind::Pointer { pointee, .. } => clang_type_is_fully_supported(pointee),
        ClangTypeKind::Array { element, .. } => clang_type_is_fully_supported(element),
        ClangTypeKind::Unsupported { .. } => false,
        ClangTypeKind::Void
        | ClangTypeKind::Integer { .. }
        | ClangTypeKind::Record { .. }
        | ClangTypeKind::Function => true,
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn clang_type_candidate_spellings(type_object: &Value) -> Vec<String> {
    ["qualType", "desugaredQualType", "canonicalQualType"]
        .into_iter()
        .filter_map(|field| string_field(type_object, field))
        .collect()
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub(super) struct TypeAliasInventory {
    by_name: BTreeMap<String, Result<ClangTypeSkeleton, String>>,
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_alias_inventory_from_ast(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> TypeAliasInventory {
    let mut inventory = TypeAliasInventory::default();
    collect_type_alias_inventory_from_ast(ast, target_abi, &mut inventory);
    inventory
}

#[cfg(feature = "typed-ir")]
fn collect_type_alias_inventory_from_ast(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
    inventory: &mut TypeAliasInventory,
) {
    if string_field(node, "kind").as_deref() == Some("TypedefDecl")
        && node.get("isImplicit").and_then(Value::as_bool) != Some(true)
    {
        if let Some(alias) = string_field(node, "name").filter(|name| is_simple_c_identifier(name))
        {
            let entry = node
                .get("type")
                .ok_or_else(|| "TypedefDecl is missing type.qualType".to_string())
                .and_then(|type_object| {
                    type_from_ast_type_object(type_object, target_abi)
                        .map_err(|error| error.message)
                })
                .and_then(|ty| match ty.kind {
                    ClangTypeKind::Unsupported { reason } => Err(reason),
                    _ => Ok(ty),
                });
            insert_type_alias_inventory_entry(inventory, alias, entry);
        }
    }
    for child in inner(node) {
        collect_type_alias_inventory_from_ast(child, target_abi, inventory);
    }
}

#[cfg(feature = "typed-ir")]
fn insert_type_alias_inventory_entry(
    inventory: &mut TypeAliasInventory,
    alias: String,
    entry: Result<ClangTypeSkeleton, String>,
) {
    match inventory.by_name.entry(alias) {
        std::collections::btree_map::Entry::Vacant(slot) => {
            slot.insert(entry);
        }
        std::collections::btree_map::Entry::Occupied(mut slot) => {
            if slot.get() != &entry {
                let alias = slot.key().clone();
                let _ = slot.insert(Err(format!(
                    "duplicate TypedefDecl name {alias} in clang AST; typedef lowering requires unique alias provenance"
                )));
            }
        }
    }
}
