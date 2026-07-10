#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn if_assignment_call_record_pointer_nested_member_fixture(function_name: &str) -> Value {
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let declarations = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations");
    declarations.insert(
        0,
        serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "Context",
            "completeDefinition": true,
            "inner": [
                { "kind": "FieldDecl", "name": "address", "type": { "qualType": "struct Address" } }
            ]
        }),
    );
    declarations.insert(
        0,
        serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "Address",
            "completeDefinition": true,
            "inner": [
                { "kind": "FieldDecl", "name": "threshold", "type": { "qualType": "unsigned int" } }
            ]
        }),
    );
    let function = declarations
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let target_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    let root = target_member["inner"][0].clone();
    target_member["name"] = serde_json::json!("threshold");
    target_member["isArrow"] = serde_json::json!(false);
    target_member["inner"] = serde_json::json!([{
        "kind": "MemberExpr",
        "name": "address",
        "isArrow": true,
        "type": { "qualType": "struct Address" },
        "inner": [root]
    }]);
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_nested_member_requires_complete_record_inventory() {
    let function_name = "bad_if_assign_call_incomplete_nested_record";
    let mut ast = if_assignment_call_record_pointer_nested_member_fixture(function_name);
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .retain(|decl| decl["name"] != "Address");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("frontend keeps the typed nested member candidate");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("missing nested record inventory must fail closed");
    assert!(
        error.reason.contains("record Context field address"),
        "expected incomplete nested record rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_nested_member_rejects_duplicate_mutable_borrow_args() {
    let function_name = "bad_if_assign_call_duplicate_mutable_borrow";
    let mut ast = if_assignment_call_record_pointer_nested_member_fixture(function_name);
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let call = &mut function["inner"][2]["inner"][0]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][1];
    call["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned int (*)(struct Context *, struct Context *)");
    call["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("unsigned int (struct Context *, struct Context *)");
    call["inner"][2] = call["inner"][1].clone();

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("frontend keeps duplicate mutable pointer arguments for emitter validation");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("duplicate mutable record borrows must fail closed");
    assert!(
        error
            .reason
            .contains("cannot borrow multiple mutable record pointer parameters"),
        "expected duplicate mutable borrow rejection, got {error:?}"
    );
}
