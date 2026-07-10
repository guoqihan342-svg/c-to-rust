#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_rejects_second_arrow() {
    let function_name = "reject_second_arrow_add";
    let mut ast = nested_record_scalar_add_fixture(function_name);
    ast["inner"][1]["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct Cell *");
    let function = nested_record_scalar_add_function_mut(&mut ast, function_name);
    let target = &mut nested_record_scalar_add_assignment_mut(function)["inner"][0];
    target["isArrow"] = serde_json::json!(true);
    target["inner"][0]["type"]["qualType"] = serde_json::json!("struct Cell *");

    let reason = nested_record_scalar_add_error(&ast, function_name);
    assert!(
        reason.contains("second arrow")
            || reason.contains("ownership evidence")
            || reason.contains("arrow member assignment"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_rejects_pointer_source() {
    let function_name = "reject_pointer_source_add";
    let mut ast = nested_record_scalar_add_fixture(function_name);
    let function = nested_record_scalar_add_function_mut(&mut ast, function_name);
    function["inner"][1]["type"]["qualType"] =
        serde_json::json!("const struct Input *");
    let assignment = nested_record_scalar_add_assignment_mut(function);
    let source_member = &mut assignment["inner"][1]["inner"][0]["inner"][0];
    source_member["isArrow"] = serde_json::json!(true);
    source_member["inner"] = serde_json::json!([record_scalar_add_read(
        record_scalar_add_decl_ref("source", "const struct Input *"),
        "const struct Input *",
    )]);

    let reason = nested_record_scalar_add_error(&ast, function_name);
    assert!(
        reason.contains("alias proof")
            || reason.contains("noalias")
            || reason.contains("pointer")
            || reason.contains("by-value record")
            || reason.contains("ownership evidence"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_rejects_effectful_rhs() {
    let function_name = "reject_effectful_extent_add";
    let mut ast = nested_record_scalar_add_fixture(function_name);
    let function = nested_record_scalar_add_function_mut(&mut ast, function_name);
    let assignment = nested_record_scalar_add_assignment_mut(function);
    assignment["inner"][1]["inner"][1] = serde_json::json!({
        "kind": "UnaryOperator",
        "opcode": "++",
        "isPostfix": true,
        "type": { "qualType": "unsigned int" },
        "inner": [record_scalar_add_decl_ref("extent", "unsigned int")]
    });

    let reason = nested_record_scalar_add_error(&ast, function_name);
    assert!(
        reason.contains("side effect")
            || reason.contains("side-effect")
            || reason.contains("effectful")
            || reason.contains("increment/decrement"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_rejects_integer_type_drift() {
    let function_name = "reject_signed_extent_add";
    let mut ast = nested_record_scalar_add_fixture(function_name);
    let function = nested_record_scalar_add_function_mut(&mut ast, function_name);
    function["inner"][2]["type"]["qualType"] = serde_json::json!("int");
    let assignment = nested_record_scalar_add_assignment_mut(function);
    assignment["inner"][1]["inner"][1]["type"]["qualType"] =
        serde_json::json!("int");
    assignment["inner"][1]["inner"][1]["inner"][0]["type"]["qualType"] =
        serde_json::json!("int");

    let reason = nested_record_scalar_add_error(&ast, function_name);
    assert!(
        reason.contains("types must match")
            || reason.contains("does not match")
            || reason.contains("type drifted")
            || reason.contains("type mismatch"),
        "{reason}"
    );
}
