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

    let mut first_unsupported = None;
    let mut first_error = None;
    for candidate in candidates {
        match parse(&candidate) {
            Ok(ty) if !matches!(ty.kind, ClangTypeKind::Unsupported { .. }) => return Ok(ty),
            Ok(ty) => {
                if first_unsupported.is_none() {
                    first_unsupported = Some(ty);
                }
            }
            Err(error) => {
                if first_error.is_none() {
                    first_error = Some(error);
                }
            }
        }
    }

    if let Some(ty) = first_unsupported {
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

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_ast_type_object_with_aliases(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    validate_fixed_width_typedef_desugaring(type_object, target_abi)?;
    type_from_ast_type_object_with_parser(
        type_object,
        |qual_type| type_from_qual_type_with_aliases(qual_type, target_abi, aliases),
        "invalid_clang_type",
        "clang type object is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
pub(super) fn function_return_type_from_type_object_with_aliases(
    type_object: &Value,
    aliases: &TypeAliasInventory,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_ast_type_object_with_parser(
        type_object,
        |qual_type| function_return_type_with_aliases(qual_type, aliases, target_abi),
        "invalid_function_decl",
        "FunctionDecl is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
fn function_return_type_with_aliases(
    qual_type: &str,
    aliases: &TypeAliasInventory,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    if let Some(return_type) = function_pointer_return_qual_type(qual_type) {
        return type_from_qual_type_with_aliases(&return_type, target_abi, aliases);
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
    type_from_qual_type_with_aliases(return_type.trim(), target_abi, aliases)
}

#[cfg(feature = "typed-ir")]
fn type_from_qual_type_with_aliases(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    if let Some(alias) = type_alias_skeleton(trimmed, aliases) {
        return Ok(alias);
    }
    if let Some(function_pointer) = split_function_pointer_qual_type(trimmed) {
        let function = function_type_skeleton_with_aliases(
            function_pointer.function.trim(),
            target_abi,
            aliases,
        )?;
        let canonical = format!("{} *", function.canonical);
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(function),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(pointer) = split_pointer_qual_type(trimmed) {
        let pointee =
            type_from_qual_type_with_aliases(pointer.pointee.trim(), target_abi, aliases)?;
        let canonical = match pointer.restrict_qualifier {
            Some(qualifier) => format!("{} *{qualifier}", pointee.canonical),
            None => format!("{} *", pointee.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(pointee),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(unqualified) = trimmed.strip_prefix("const ") {
        let unqualified = type_from_qual_type_with_aliases(unqualified.trim(), target_abi, aliases)?;
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: unqualified.canonical,
            kind: unqualified.kind,
        });
    }
    if let Some((element, len)) = split_array_qual_type(trimmed)? {
        let element = type_from_qual_type_with_aliases(element, target_abi, aliases)?;
        let canonical = match len {
            Some(len) => format!("{}[{len}]", element.canonical),
            None => format!("{}[]", element.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Array {
                element: Box::new(element),
                len,
            },
        });
    }
    if split_function_qual_type(trimmed).is_some() {
        return function_type_skeleton_with_aliases(trimmed, target_abi, aliases);
    }
    type_from_qual_type_with_target_abi(trimmed, target_abi)
}

#[cfg(feature = "typed-ir")]
fn function_type_skeleton_with_aliases(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    let Some((return_type, _params)) = split_function_qual_type(trimmed) else {
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!("{trimmed} is outside the current function type skeleton"),
            },
        });
    };
    let return_type = type_from_qual_type_with_aliases(return_type, target_abi, aliases)?;
    if matches!(return_type.kind, ClangTypeKind::Unsupported { .. }) {
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!(
                    "function return type {} is outside the current type skeleton",
                    return_type.spelled
                ),
            },
        });
    }
    Ok(ClangTypeSkeleton {
        spelled: trimmed.to_string(),
        canonical: trimmed.to_string(),
        kind: ClangTypeKind::Function,
    })
}

#[cfg(feature = "typed-ir")]
fn type_alias_skeleton(
    name: &str,
    aliases: &TypeAliasInventory,
) -> Option<ClangTypeSkeleton> {
    let entry = aliases.by_name.get(name)?;
    Some(match entry {
        Ok(ty) => ClangTypeSkeleton {
            spelled: name.to_string(),
            canonical: ty.canonical.clone(),
            kind: ty.kind.clone(),
        },
        Err(reason) => ClangTypeSkeleton {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: reason.clone(),
            },
        },
    })
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Copy)]
struct FixedWidthInteger {
    signed: bool,
    width: u16,
}

#[cfg(feature = "typed-ir")]
pub(super) fn validate_fixed_width_typedef_desugaring(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<(), ClangFrontendError> {
    let Some(qual_type) = string_field(type_object, "qualType") else {
        return Ok(());
    };
    let Some(expected) = fixed_width_integer_signature(qual_type.trim()) else {
        return Ok(());
    };

    for field in ["desugaredQualType", "canonicalQualType"] {
        let Some(spelling) = string_field(type_object, field) else {
            continue;
        };
        let spelling = spelling.trim();
        if spelling == qual_type.trim() {
            continue;
        }
        let parsed = type_from_qual_type_with_target_abi(spelling, target_abi)?;
        match parsed.kind {
            ClangTypeKind::Integer { signed, width }
                if signed == expected.signed && width == expected.width => {}
            ClangTypeKind::Integer { signed, width } => {
                return Err(fixed_width_typedef_mismatch_error(
                    qual_type.trim(),
                    expected,
                    field,
                    spelling,
                    Some((signed, width)),
                    None,
                ));
            }
            ClangTypeKind::Unsupported { reason } => {
                if target_abi.is_none() && reason.contains("requires target ABI width provenance") {
                    continue;
                }
                return Err(fixed_width_typedef_mismatch_error(
                    qual_type.trim(),
                    expected,
                    field,
                    spelling,
                    None,
                    Some(reason.as_str()),
                ));
            }
            _ => {
                return Err(fixed_width_typedef_mismatch_error(
                    qual_type.trim(),
                    expected,
                    field,
                    spelling,
                    None,
                    Some("desugared type is not an integer"),
                ));
            }
        }
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn fixed_width_typedef_mismatch_error(
    qual_type: &str,
    expected: FixedWidthInteger,
    field: &str,
    spelling: &str,
    actual: Option<(bool, u16)>,
    reason: Option<&str>,
) -> ClangFrontendError {
    let actual_text = actual
        .map(|(signed, width)| format!("signed={signed}, width={width}"))
        .or_else(|| reason.map(str::to_string))
        .unwrap_or_else(|| "unresolved".to_string());
    ClangFrontendError {
        kind: "fixed_width_typedef_desugaring_mismatch".to_string(),
        message: format!(
            "{qual_type} requires {field}={spelling} to prove the same fixed-width integer contract (expected signed={}, width={}; actual {actual_text})",
            expected.signed, expected.width
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn fixed_width_integer_signature(spelling: &str) -> Option<FixedWidthInteger> {
    match spelling {
        "int8_t" => Some(FixedWidthInteger {
            signed: true,
            width: 8,
        }),
        "uint8_t" => Some(FixedWidthInteger {
            signed: false,
            width: 8,
        }),
        "int16_t" => Some(FixedWidthInteger {
            signed: true,
            width: 16,
        }),
        "uint16_t" => Some(FixedWidthInteger {
            signed: false,
            width: 16,
        }),
        "int32_t" => Some(FixedWidthInteger {
            signed: true,
            width: 32,
        }),
        "uint32_t" => Some(FixedWidthInteger {
            signed: false,
            width: 32,
        }),
        "int64_t" => Some(FixedWidthInteger {
            signed: true,
            width: 64,
        }),
        "uint64_t" => Some(FixedWidthInteger {
            signed: false,
            width: 64,
        }),
        _ => None,
    }
}

#[cfg(all(feature = "typed-ir", test))]
/// Parses clang `qualType` spelling into the frontend's narrow type skeleton.
///
/// The mapper is intentionally conservative: pointers, `const`, arrays, record
/// names, and fixed-width integer spellings are accepted; target-dependent or
/// ambiguous C spellings fail closed so the typed IR emitter never receives a
/// type whose width or layout was inferred by string guesswork.
pub(super) fn type_from_qual_type(
    qual_type: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_qual_type_with_target_abi(qual_type, None)
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_qual_type_with_target_abi(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    if let Some(function_pointer) = split_function_pointer_qual_type(trimmed) {
        let function = function_type_skeleton(function_pointer.function.trim(), target_abi)?;
        let canonical = format!("{} *", function.canonical);
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(function),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(pointer) = split_pointer_qual_type(trimmed) {
        let pointee = type_from_qual_type_with_target_abi(pointer.pointee.trim(), target_abi)?;
        let canonical = match pointer.restrict_qualifier {
            Some(qualifier) => format!("{} *{qualifier}", pointee.canonical),
            None => format!("{} *", pointee.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(pointee),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(unqualified) = trimmed.strip_prefix("const ") {
        let unqualified = type_from_qual_type_with_target_abi(unqualified.trim(), target_abi)?;
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: unqualified.canonical,
            kind: unqualified.kind,
        });
    }
    if let Some((element, len)) = split_array_qual_type(trimmed)? {
        let element = type_from_qual_type_with_target_abi(element, target_abi)?;
        let canonical = match len {
            Some(len) => format!("{}[{len}]", element.canonical),
            None => format!("{}[]", element.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Array {
                element: Box::new(element),
                len,
            },
        });
    }
    if split_function_qual_type(trimmed).is_some() {
        return function_type_skeleton(trimmed, target_abi);
    }
    if let Some(name) = trimmed.strip_prefix("struct ") {
        let name = name.trim();
        if is_simple_c_identifier(name) {
            return Ok(ClangTypeSkeleton {
                spelled: trimmed.to_string(),
                canonical: trimmed.to_string(),
                kind: ClangTypeKind::Record {
                    name: name.to_string(),
                },
            });
        }
    }

    match trimmed {
        "void" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        }),
        "bool" | "_Bool" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "_Bool".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 8,
            },
        }),
        "int" => Ok(profile_or_default_int_type(
            "int", "int", true, 32, target_abi,
        )),
        "signed char" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "signed char".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        }),
        "int8_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int8_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        }),
        "int16_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int16_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 16,
            },
        }),
        "int32_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int32_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 32,
            },
        }),
        "int64_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int64_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 64,
            },
        }),
        "uint16_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "uint16_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 16,
            },
        }),
        "unsigned int" => Ok(profile_or_default_int_type(
            "unsigned int",
            "unsigned int",
            false,
            32,
            target_abi,
        )),
        "uint32_t" => Ok(ClangTypeSkeleton {
            spelled: qual_type.trim().to_string(),
            canonical: "uint32_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 32,
            },
        }),
        "unsigned char" | "uint8_t" => Ok(ClangTypeSkeleton {
            spelled: qual_type.trim().to_string(),
            canonical: "uint8_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 8,
            },
        }),
        "uint64_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "uint64_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        }),
        "char" | "short" | "unsigned short" | "long" | "unsigned long" | "long long"
        | "unsigned long long" | "size_t" | "__size_t" => Ok(
            target_dependent_integer_type_with_profile(trimmed, target_abi),
        ),
        other => Ok(ClangTypeSkeleton {
            spelled: other.to_string(),
            canonical: other.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!("{other} is outside the current type skeleton"),
            },
        }),
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn profile_or_default_int_type(
    spelling: &str,
    canonical: &str,
    signed: bool,
    default_width: u16,
    target_abi: Option<&TargetAbiProfile>,
) -> ClangTypeSkeleton {
    let width = match target_abi {
        Some(abi) => match nonzero_width(abi.int_width) {
            Some(width) => width,
            None => {
                return ClangTypeSkeleton {
                    spelled: spelling.to_string(),
                    canonical: canonical.to_string(),
                    kind: ClangTypeKind::Unsupported {
                        reason: format!(
                            "{spelling} requires an explicit target ABI int_width before typed IR lowering"
                        ),
                    },
                };
            }
        },
        None => default_width,
    };

    ClangTypeSkeleton {
        spelled: spelling.to_string(),
        canonical: canonical.to_string(),
        kind: ClangTypeKind::Integer { signed, width },
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn target_dependent_integer_type_with_profile(
    spelling: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> ClangTypeSkeleton {
    if let Some((signed, width)) = target_dependent_integer_width(spelling, target_abi) {
        return ClangTypeSkeleton {
            spelled: spelling.to_string(),
            canonical: spelling.to_string(),
            kind: ClangTypeKind::Integer { signed, width },
        };
    }

    ClangTypeSkeleton {
        spelled: spelling.to_string(),
        canonical: spelling.to_string(),
        kind: ClangTypeKind::Unsupported {
            reason: if target_abi.is_some() {
                format!(
                    "{spelling} requires an explicit target ABI width field before typed IR lowering"
                )
            } else {
                format!("{spelling} requires target ABI width provenance before typed IR lowering")
            },
        },
    }
}
