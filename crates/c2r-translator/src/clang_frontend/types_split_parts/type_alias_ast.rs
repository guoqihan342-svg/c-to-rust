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
        bind_missing_type_alias_desugaring(type_object, aliases);
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
fn bind_missing_type_alias_desugaring(type_object: &mut Value, aliases: &TypeAliasInventory) {
    if string_field(type_object, "desugaredQualType").is_some()
        || string_field(type_object, "canonicalQualType").is_some()
    {
        return;
    }
    let Some(alias_name) = string_field(type_object, "qualType")
        .map(|value| value.trim().to_string())
        .filter(|value| is_simple_c_identifier(value))
    else {
        return;
    };
    if is_target_dependent_integer_spelling(&alias_name)
        || type_from_qual_type_with_target_abi(&alias_name, None)
            .is_ok_and(|ty| !matches!(ty.kind, ClangTypeKind::Unsupported { .. }))
    {
        return;
    }
    let Some(Ok(alias_ty)) = aliases.by_name.get(&alias_name) else {
        return;
    };
    let Some(object) = type_object.as_object_mut() else {
        return;
    };
    object.insert(
        "desugaredQualType".to_string(),
        Value::String(alias_ty.canonical.clone()),
    );
}
