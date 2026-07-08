#[cfg(feature = "typed-ir")]
fn function_skeleton_from_ast_with_aliases(
    function: &Value,
    aliases: &TypeAliasInventory,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangFunctionSkeleton, ClangFrontendError> {
    let name = string_field(function, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_function_decl".to_string(),
        message: "FunctionDecl is missing name".to_string(),
    })?;
    let function_type = function.get("type").ok_or_else(|| ClangFrontendError {
        kind: "invalid_function_decl".to_string(),
        message: format!("FunctionDecl {name} is missing qualType"),
    })?;
    let return_type =
        function_return_type_from_type_object_with_aliases(function_type, aliases, target_abi)?;
    let children = inner(function);
    let params = children
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("ParmVarDecl"))
        .map(|param| param_skeleton_from_ast_with_aliases(param, aliases, target_abi))
        .collect::<Result<Vec<_>, ClangFrontendError>>()?;
    let compound = children
        .iter()
        .find(|child| string_field(child, "kind").as_deref() == Some("CompoundStmt"))
        .ok_or_else(|| ClangFrontendError {
            kind: "unsupported_function_body".to_string(),
            message: format!("FunctionDecl {name} does not contain a CompoundStmt body"),
        })?;
    let body = compound_body_skeleton_from_ast(compound)?;

    Ok(ClangFunctionSkeleton {
        name,
        return_type,
        params,
        body,
    })
}

#[cfg(feature = "typed-ir")]
fn param_skeleton_from_ast_with_aliases(
    param: &Value,
    aliases: &TypeAliasInventory,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangParamSkeleton, ClangFrontendError> {
    let name = string_field(param, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_param_decl".to_string(),
        message: "ParmVarDecl is missing name".to_string(),
    })?;
    let ty = param
        .get("type")
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_param_decl".to_string(),
            message: format!("ParmVarDecl {name} is missing qualType"),
        })
        .and_then(|type_object| {
            type_from_ast_type_object_with_aliases(type_object, target_abi, aliases)
        })?;

    Ok(ClangParamSkeleton { name, ty })
}
