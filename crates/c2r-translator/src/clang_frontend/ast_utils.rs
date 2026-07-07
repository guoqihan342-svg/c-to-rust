#[cfg(feature = "typed-ir")]
fn is_integral_conversion_cast_expr(expr: &Value) -> bool {
    match string_field(expr, "castKind").as_deref() {
        Some("IntegralCast" | "IntegralPromotion") => true,
        Some("NoOp") => is_integer_noop_cast_expr(expr),
        _ => false,
    }
}

#[cfg(feature = "typed-ir")]
fn is_integer_noop_cast_expr(expr: &Value) -> bool {
    let Ok(target) = expr_type(expr) else {
        return false;
    };
    if !matches!(target.kind, ClangTypeKind::Integer { .. }) {
        return false;
    }
    let Some(operand) = inner(expr).first() else {
        return false;
    };
    let Ok(operand_ty) = expr_type(operand) else {
        return false;
    };
    matches!(operand_ty.kind, ClangTypeKind::Integer { .. })
}

#[cfg(feature = "typed-ir")]
fn is_integer_lvalue_to_rvalue_cast_expr(expr: &Value) -> bool {
    if string_field(expr, "castKind").as_deref() != Some("LValueToRValue") {
        return false;
    }
    let Ok(target) = expr_type(expr) else {
        return false;
    };
    if !is_integer_or_target_dependent_integer_type(&target) {
        return false;
    }
    let Some(operand) = inner(expr).first() else {
        return false;
    };
    let Ok(operand_ty) = expr_type(operand) else {
        return false;
    };
    is_same_lvalue_to_rvalue_integer_type(&target, &operand_ty)
}

#[cfg(feature = "typed-ir")]
fn is_integer_or_target_dependent_integer_type(ty: &ClangTypeSkeleton) -> bool {
    matches!(ty.kind, ClangTypeKind::Integer { .. })
        || target_dependent_lvalue_read_spelling(ty).is_some()
}

#[cfg(feature = "typed-ir")]
fn is_same_lvalue_to_rvalue_integer_type(
    target: &ClangTypeSkeleton,
    operand_ty: &ClangTypeSkeleton,
) -> bool {
    if matches!(target.kind, ClangTypeKind::Integer { .. })
        && matches!(operand_ty.kind, ClangTypeKind::Integer { .. })
    {
        return operand_ty.kind == target.kind;
    }
    let Some(target_spelling) = target_dependent_lvalue_read_spelling(target) else {
        return false;
    };
    let Some(operand_spelling) = target_dependent_lvalue_read_spelling(operand_ty) else {
        return false;
    };
    target_spelling == operand_spelling && target.canonical == operand_ty.canonical
}

#[cfg(feature = "typed-ir")]
fn target_dependent_lvalue_read_spelling(ty: &ClangTypeSkeleton) -> Option<&str> {
    let spelling = unqualified_lvalue_read_spelling(&ty.spelled);
    (is_target_dependent_integer_spelling(spelling) && ty.canonical == spelling).then_some(spelling)
}

#[cfg(feature = "typed-ir")]
fn unqualified_lvalue_read_spelling(spelling: &str) -> &str {
    let spelling = spelling.trim();
    spelling.strip_prefix("const ").unwrap_or(spelling).trim()
}

#[cfg(feature = "typed-ir")]
fn preserves_integral_operand_casts(op: &ClangBinaryOperator) -> bool {
    matches!(
        op,
        ClangBinaryOperator::Add
            | ClangBinaryOperator::Sub
            | ClangBinaryOperator::Mul
            | ClangBinaryOperator::Div
            | ClangBinaryOperator::Mod
            | ClangBinaryOperator::BitAnd
            | ClangBinaryOperator::BitOr
            | ClangBinaryOperator::BitXor
            | ClangBinaryOperator::Shl
            | ClangBinaryOperator::Shr
            | ClangBinaryOperator::LogAnd
            | ClangBinaryOperator::LogOr
            | ClangBinaryOperator::Eq
            | ClangBinaryOperator::Neq
            | ClangBinaryOperator::Lt
            | ClangBinaryOperator::Le
            | ClangBinaryOperator::Gt
            | ClangBinaryOperator::Ge
    )
}

#[cfg(feature = "typed-ir")]
fn expr_type(expr: &Value) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    expr.get("type")
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "clang expression node is missing qualType".to_string(),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))
}

#[cfg(feature = "typed-ir")]
fn find_function_decl<'a>(node: &'a Value, function_name: &str) -> Option<&'a Value> {
    find_function_decl_with_body(node, function_name)
        .or_else(|| find_function_decl_any(node, function_name))
}

#[cfg(feature = "typed-ir")]
fn find_function_decl_with_body<'a>(node: &'a Value, function_name: &str) -> Option<&'a Value> {
    if is_named_function_decl(node, function_name)
        && inner(node)
            .iter()
            .any(|child| string_field(child, "kind").as_deref() == Some("CompoundStmt"))
    {
        return Some(node);
    }

    inner(node)
        .iter()
        .find_map(|child| find_function_decl_with_body(child, function_name))
}

#[cfg(feature = "typed-ir")]
fn find_function_decl_any<'a>(node: &'a Value, function_name: &str) -> Option<&'a Value> {
    if is_named_function_decl(node, function_name) {
        return Some(node);
    }

    inner(node)
        .iter()
        .find_map(|child| find_function_decl_any(child, function_name))
}

#[cfg(feature = "typed-ir")]
fn is_named_function_decl(node: &Value, function_name: &str) -> bool {
    string_field(node, "kind").as_deref() == Some("FunctionDecl")
        && string_field(node, "name").as_deref() == Some(function_name)
}

#[cfg(feature = "typed-ir")]
fn is_simple_c_identifier(text: &str) -> bool {
    let mut chars = text.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|character| character == '_' || character.is_ascii_alphanumeric())
}

#[cfg(feature = "typed-ir")]
fn inner(node: &Value) -> &[Value] {
    node.get("inner")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

#[cfg(feature = "typed-ir")]
fn array_filler(node: &Value) -> Option<&[Value]> {
    node.get("array_filler")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
}

#[cfg(feature = "typed-ir")]
fn string_field(node: &Value, field: &str) -> Option<String> {
    node.get(field)
        .and_then(Value::as_str)
        .map(ToString::to_string)
}

#[cfg(feature = "typed-ir")]
fn integer_field(node: &Value, field: &str) -> Option<i64> {
    node.get(field).and_then(Value::as_i64)
}

#[cfg(feature = "typed-ir")]
fn normalized_report_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn normalized_path(path: &Path) -> String {
    normalized_metadata_path(&path.to_string_lossy())
}

fn normalized_metadata_path(path: &str) -> String {
    path.trim().replace('\\', "/")
}

fn required_path(value: Option<&str>, field: &str) -> Result<PathBuf, ClangFrontendError> {
    let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Err(ClangFrontendError {
            kind: format!("missing_{field}"),
            message: format!("clang frontend dry-run requires {field}"),
        });
    };
    Ok(PathBuf::from(value))
}
