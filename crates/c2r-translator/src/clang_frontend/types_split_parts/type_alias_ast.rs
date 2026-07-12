#[cfg(feature = "typed-ir")]
pub(super) fn bind_type_aliases_to_ast_type_objects(
    node: &mut Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) -> Result<(), ClangFrontendError> {
    for field in ["type", "argType"] {
        let Some(type_object) = node.get_mut(field).filter(|value| value.is_object()) else {
            continue;
        };
        validate_type_alias_desugaring(type_object, target_abi, aliases)?;
        bind_missing_type_alias_desugaring(type_object, target_abi, aliases);
    }

    let Some(children) = node.get_mut("inner").and_then(Value::as_array_mut) else {
        return Ok(());
    };
    for child in children {
        bind_type_aliases_to_ast_type_objects(child, target_abi, aliases)?;
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn bind_missing_type_alias_desugaring(
    type_object: &mut Value,
    target_abi: Option<&TargetAbiProfile>,
    aliases: &TypeAliasInventory,
) {
    if string_field(type_object, "desugaredQualType").is_some()
        || string_field(type_object, "canonicalQualType").is_some()
    {
        return;
    }
    let Some(qual_type) = string_field(type_object, "qualType")
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    else {
        return;
    };
    if is_target_dependent_integer_spelling(&qual_type)
        || type_from_qual_type_with_target_abi(&qual_type, target_abi)
            .is_ok_and(|ty| clang_type_is_fully_supported(&ty))
    {
        return;
    }
    let Ok(alias_ty) = type_from_qual_type_with_aliases(&qual_type, target_abi, aliases) else {
        return;
    };
    if !clang_type_is_fully_supported(&alias_ty) {
        return;
    }
    let Some(object) = type_object.as_object_mut() else {
        return;
    };
    object.insert(
        "desugaredQualType".to_string(),
        Value::String(alias_ty.canonical.clone()),
    );
}
