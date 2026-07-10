#[cfg(feature = "typed-ir")]
fn validate_interior_reborrow_typedef_provenance(
    ast: &Value,
    function: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<(), ClangFrontendError> {
    let compound = inner(function)
        .iter()
        .find(|node| string_field(node, "kind").as_deref() == Some("CompoundStmt"));
    let Some(compound) = compound else {
        return Ok(());
    };
    let candidates = inner(compound)
        .iter()
        .filter_map(|stmt| direct_reborrow_var_decl(stmt))
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Ok(());
    }
    if candidates.len() != 1 {
        return interior_reborrow_frontend_error(
            "interior reborrow requires exactly one address-of-field local alias",
        );
    }
    let (var_decl, member) = candidates[0];
    let alias = var_decl
        .get("type")
        .and_then(|ty| string_field(ty, "qualType"))
        .filter(|name| is_simple_c_identifier(name))
        .ok_or_else(|| {
            interior_reborrow_error(
                "interior reborrow local must use one direct pointer typedef name",
            )
        })?;
    let typedefs = collect_named_typedefs(ast, &alias);
    let [typedef] = typedefs.as_slice() else {
        return interior_reborrow_frontend_error(
            "interior reborrow pointer typedef provenance is missing or conflicting",
        );
    };
    let typedef_type = typedef.get("type").ok_or_else(|| {
        interior_reborrow_error("interior reborrow TypedefDecl is missing type metadata")
    })?;
    reject_raw_reborrow_qualifiers(typedef_type)?;
    let alias_ty = type_from_ast_type_object(typedef_type, target_abi)?;
    let ClangTypeKind::Pointer { pointee, .. } = &alias_ty.kind else {
        return interior_reborrow_frontend_error(
            "interior reborrow typedef must desugar to a pointer",
        );
    };
    if !matches!(pointee.kind, ClangTypeKind::Record { .. })
        || pointee.spelled.trim_start().starts_with("const ")
    {
        return interior_reborrow_frontend_error(
            "interior reborrow typedef must point to one mutable named record",
        );
    }

    let local_type = var_decl.get("type").ok_or_else(|| {
        interior_reborrow_error("interior reborrow VarDecl is missing type metadata")
    })?;
    let local_ty = type_from_ast_type_object(local_type, target_abi)?;
    if local_ty.canonical != alias_ty.canonical || local_ty.kind != alias_ty.kind {
        return interior_reborrow_frontend_error(
            "interior reborrow local type does not match its pointer typedef",
        );
    }
    let member_type = member.get("type").ok_or_else(|| {
        interior_reborrow_error("interior reborrow owner field is missing type metadata")
    })?;
    let member_ty = type_from_ast_type_object(member_type, target_abi)?;
    if pointee.canonical != member_ty.canonical || pointee.kind != member_ty.kind {
        return interior_reborrow_frontend_error(
            "interior reborrow typedef pointee does not exactly match owner field type",
        );
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn direct_reborrow_var_decl(stmt: &Value) -> Option<(&Value, &Value)> {
    if string_field(stmt, "kind").as_deref() != Some("DeclStmt") {
        return None;
    }
    let vars = inner(stmt)
        .iter()
        .filter(|node| string_field(node, "kind").as_deref() == Some("VarDecl"))
        .collect::<Vec<_>>();
    let [var_decl] = vars.as_slice() else {
        return None;
    };
    let initializer = inner(var_decl).first()?;
    let address = unwrap_reborrow_ast_expr(initializer);
    if string_field(address, "kind").as_deref() != Some("UnaryOperator")
        || string_field(address, "opcode").as_deref() != Some("&")
    {
        return None;
    }
    let member = unwrap_reborrow_ast_expr(inner(address).first()?);
    (string_field(member, "kind").as_deref() == Some("MemberExpr")
        && member.get("isArrow").and_then(Value::as_bool) == Some(true))
    .then_some((*var_decl, member))
}

#[cfg(feature = "typed-ir")]
fn unwrap_reborrow_ast_expr(mut expr: &Value) -> &Value {
    while matches!(
        string_field(expr, "kind").as_deref(),
        Some("ParenExpr") | Some("ExprWithCleanups")
    ) {
        let Some(child) = inner(expr).first() else {
            break;
        };
        expr = child;
    }
    expr
}

#[cfg(feature = "typed-ir")]
fn collect_named_typedefs<'a>(node: &'a Value, expected: &str) -> Vec<&'a Value> {
    let mut found = Vec::new();
    if string_field(node, "kind").as_deref() == Some("TypedefDecl")
        && node.get("isImplicit").and_then(Value::as_bool) != Some(true)
        && string_field(node, "name").as_deref() == Some(expected)
    {
        found.push(node);
    }
    for child in inner(node) {
        found.extend(collect_named_typedefs(child, expected));
    }
    found
}

#[cfg(feature = "typed-ir")]
fn reject_raw_reborrow_qualifiers(type_object: &Value) -> Result<(), ClangFrontendError> {
    let qualified = clang_type_candidate_spellings(type_object)
        .join(" ")
        .to_ascii_lowercase();
    if qualified.split_whitespace().any(|part| part == "volatile")
        || qualified.contains("_atomic")
        || qualified.contains("atomic(")
        || qualified.starts_with("const ")
    {
        return interior_reborrow_frontend_error(
            "interior reborrow typedef const/volatile/atomic qualification is unsupported",
        );
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn interior_reborrow_frontend_error<T>(message: &str) -> Result<T, ClangFrontendError> {
    Err(interior_reborrow_error(message))
}

#[cfg(feature = "typed-ir")]
fn interior_reborrow_error(message: &str) -> ClangFrontendError {
    ClangFrontendError {
        kind: "unsupported_interior_reborrow".to_string(),
        message: message.to_string(),
    }
}
