#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_rejects_abi_unproven_unsigned_long() {
    let function_name = "reject_abi_unproven_add";
    let mut ast = nested_record_scalar_add_fixture(function_name);
    ast["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned long");
    ast["inner"][2]["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned long");
    let function = nested_record_scalar_add_function_mut(&mut ast, function_name);
    function["inner"][2]["type"]["qualType"] = serde_json::json!("unsigned long");
    let assignment = nested_record_scalar_add_assignment_mut(function);
    assignment["type"]["qualType"] = serde_json::json!("unsigned long");
    assignment["inner"][0]["type"]["qualType"] = serde_json::json!("unsigned long");
    assignment["inner"][1]["type"]["qualType"] = serde_json::json!("unsigned long");
    assignment["inner"][1]["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned long");
    assignment["inner"][1]["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned long");
    assignment["inner"][1]["inner"][1]["type"]["qualType"] =
        serde_json::json!("unsigned long");
    assignment["inner"][1]["inner"][1]["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned long");

    let reason = nested_record_scalar_add_error(&ast, function_name);
    assert!(
        reason.contains("ABI")
            || reason.contains("abi")
            || reason.contains("unsigned long")
            || reason.contains("target"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_requires_complete_source_inventory() {
    let function_name = "reject_incomplete_source_add";
    let mut ast = nested_record_scalar_add_fixture(function_name);
    ast["inner"][2]["completeDefinition"] = serde_json::json!(false);

    let reason = nested_record_scalar_add_error(&ast, function_name);
    assert!(
        reason.contains("Input")
            || reason.contains("field inventory")
            || reason.contains("complete"),
        "{reason}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_nested_record_scalar_add_rejects_qualified_fields() {
    for (label, qual_type) in [
        ("volatile", "volatile unsigned int"),
        ("atomic", "_Atomic(unsigned int)"),
    ] {
        let function_name = format!("reject_{label}_source_add");
        let mut ast = nested_record_scalar_add_fixture(&function_name);
        ast["inner"][2]["inner"][0]["type"]["qualType"] =
            serde_json::json!(qual_type);
        let function = nested_record_scalar_add_function_mut(&mut ast, &function_name);
        let assignment = nested_record_scalar_add_assignment_mut(function);
        assignment["inner"][1]["inner"][0]["type"]["qualType"] =
            serde_json::json!(qual_type);
        assignment["inner"][1]["inner"][0]["inner"][0]["type"]["qualType"] =
            serde_json::json!(qual_type);

        let reason = nested_record_scalar_add_error(&ast, &function_name);
        let reason_lower = reason.to_ascii_lowercase();
        assert!(
            reason_lower.contains(label)
                || reason_lower.contains("field inventory")
                || reason_lower.contains("unsupported"),
            "{label}: {reason}"
        );
    }
}
