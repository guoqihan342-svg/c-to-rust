#[cfg(feature = "typed-ir")]
pub(super) fn type_from_ast_type_object_with_aliases(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    validate_fixed_width_typedef_desugaring(type_object, target_abi)?;
    validate_type_alias_desugaring(type_object, target_abi, aliases)?;
    type_from_ast_type_object_with_parser(
        type_object,
        |qual_type| type_from_qual_type_with_aliases(qual_type, target_abi, aliases),
        "invalid_clang_type",
        "clang type object is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
fn validate_type_alias_desugaring(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> Result<(), ClangFrontendError> {
    let Some(qual_type) = string_field(type_object, "qualType")
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    else {
        return Ok(());
    };
    let alias_ty = if is_simple_c_identifier(&qual_type) {
        let Some(Ok(alias_ty)) = aliases.by_name.get(&qual_type) else {
            return Ok(());
        };
        alias_ty.clone()
    } else {
        if type_from_qual_type_with_target_abi(&qual_type, target_abi)
            .is_ok_and(|ty| clang_type_is_fully_supported(&ty))
        {
            return Ok(());
        }
        let alias_ty = type_from_qual_type_with_aliases(&qual_type, target_abi, aliases)?;
        if !clang_type_is_fully_supported(&alias_ty) {
            return Ok(());
        }
        alias_ty
    };

    for field in ["desugaredQualType", "canonicalQualType"] {
        let Some(spelling) = string_field(type_object, field) else {
            continue;
        };
        let spelling = spelling.trim();
        if spelling == qual_type {
            continue;
        }
        let parsed = type_from_qual_type_with_target_abi(spelling, target_abi)?;
        if !clang_type_is_fully_supported(&parsed) {
            continue;
        }
        if parsed.kind != alias_ty.kind {
            return Err(ClangFrontendError {
                kind: "typedef_desugaring_mismatch".to_string(),
                message: format!(
                    "typedef-containing type {qual_type} resolves to {} but {field} resolves to {}",
                    alias_ty.canonical, parsed.canonical
                ),
            });
        }
    }
    Ok(())
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
