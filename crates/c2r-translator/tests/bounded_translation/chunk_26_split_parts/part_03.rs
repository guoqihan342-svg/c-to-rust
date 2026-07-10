#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_requires_nested_record_inventory() {
    let function_name = "reject_missing_coordinate_inventory";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .retain(|decl| decl["name"] != "Coordinate");

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("record Session field position")
            || reason.contains("Coordinate")
            || reason.contains("field inventory"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_undeclared_leaf() {
    let function_name = "reject_undeclared_nested_leaf";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    let function = nested_literal_assignment_function_mut(&mut ast, function_name);
    nested_literal_assignment_target_mut(function)["name"] =
        serde_json::json!("unknown_offset");

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("unknown_offset")
            && (reason.contains("field") || reason.contains("record")),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_value_type_mismatch() {
    let function_name = "reject_nested_literal_type_mismatch";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    let function = nested_literal_assignment_function_mut(&mut ast, function_name);
    *nested_literal_assignment_value_mut(function) = serde_json::json!({
        "kind": "IntegerLiteral",
        "value": "0",
        "type": { "qualType": "int" }
    });

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("does not match expected type")
            || reason.contains("type i32")
            || reason.contains("type mismatch"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_literal_field_assignment_rejects_out_of_range_literal() {
    let function_name = "reject_nested_literal_overflow";
    let mut ast = nested_literal_field_assignment_fixture(function_name);
    set_nested_literal_leaf_type(&mut ast, function_name, "unsigned char");
    let function = nested_literal_assignment_function_mut(&mut ast, function_name);
    *nested_literal_assignment_value_mut(function) = serde_json::json!({
        "kind": "IntegerLiteral",
        "value": "256",
        "type": { "qualType": "unsigned char" }
    });

    let reason = nested_literal_assignment_error(&ast, function_name);
    assert!(
        reason.contains("literal value 256 does not fit type u8"),
        "{reason}"
    );
}
