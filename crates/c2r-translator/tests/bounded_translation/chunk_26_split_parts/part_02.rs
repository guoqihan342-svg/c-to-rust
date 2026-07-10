#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_second_arrow() {
    let function_name = "reject_second_arrow_offset";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    let function = nested_literal_assignment_function_mut(&mut ast, function_name);
    let target = nested_literal_assignment_target_mut(function);
    target["isArrow"] = serde_json::json!(true);
    target["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct Coordinate *");
    ast["inner"][1]["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct Coordinate *");

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("second arrow")
            || reason.contains("ownership evidence")
            || reason.contains("arrow member assignment"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_readonly_root() {
    let function_name = "reject_readonly_nested_offset";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    let function = nested_literal_assignment_function_mut(&mut ast, function_name);
    function["inner"][0]["type"]["qualType"] =
        serde_json::json!("const struct Session *");
    let target = nested_literal_assignment_target_mut(function);
    target["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("const struct Session *");
    target["inner"][0]["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("const struct Session *");

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("mutable record pointer")
            || reason.contains("ownership evidence")
            || reason.contains("readonly"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_nullable_root() {
    let function_name = "reject_nullable_nested_offset";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    let function = nested_literal_assignment_function_mut(&mut ast, function_name);
    let assignment = function["inner"][1]["inner"][0].clone();
    function["inner"][1]["inner"] =
        serde_json::json!([nested_literal_null_guard(), assignment]);

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("nullable")
            || reason.contains("comparison pointer operand")
            || reason.contains("unsupported type"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_volatile_and_atomic_leaf() {
    for (label, qual_type) in [
        ("volatile", "volatile unsigned int"),
        ("atomic", "_Atomic(unsigned int)"),
    ] {
        let function_name = format!("reject_{label}_nested_offset");
        let mut ast = nested_literal_field_assignment_fixture(&function_name);
        set_nested_literal_leaf_type(&mut ast, &function_name, qual_type);

        let reason = nested_literal_assignment_error(&ast, &function_name);
        let lower_reason = reason.to_ascii_lowercase();
        assert!(
            lower_reason.contains("volatile")
                || lower_reason.contains("atomic")
                || lower_reason.contains("unsupported"),
            "{label}: {reason}"
        );
    }
}
