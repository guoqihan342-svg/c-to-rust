#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_effectful_base() {
    let function_name = "bad_if_assign_call_effectful_base";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let arrow_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    let call_expr = arrow_member["inner"][1].clone();
    let base_ref = arrow_member["inner"][0].clone();
    arrow_member["inner"] = serde_json::json!([
        {
            "kind": "BinaryOperator",
            "opcode": ",",
            "type": { "qualType": "struct Context *" },
            "inner": [call_expr, base_ref]
        }
    ]);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("effectful base must fail closed");
    assert!(
        error.message.contains("root must be a direct non-null"),
        "expected effectful base rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_pointer_bitcast_root() {
    let function_name = "bad_if_assign_call_pointer_bitcast";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let arrow_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    let base_ref = arrow_member["inner"][0].clone();
    let base_type = base_ref["type"].clone();
    arrow_member["inner"][0] = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "BitCast",
        "type": base_type,
        "inner": [base_ref]
    });

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("pointer bitcast root must fail closed");

    assert!(
        error.message.contains("root must be a direct non-null"),
        "expected pointer bitcast rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_volatile_leaf() {
    let function_name = "bad_if_assign_call_volatile_leaf";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let outer_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    outer_member["type"]["qualType"] = serde_json::json!("volatile unsigned int");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("volatile leaf must fail closed");
    assert!(
        error.message.contains("volatile"),
        "expected volatile rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_by_value_local_member() {
    let function_name = "bad_if_assign_call_local_member";
    let inner = serde_json::json!({
        "kind": "IfStmt",
        "inner": [
            {
                "kind": "BinaryOperator",
                "opcode": "==",
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "ParenExpr",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            {
                                "kind": "BinaryOperator",
                                "opcode": "=",
                                "type": { "qualType": "unsigned int" },
                                "inner": [
                                    {
                                        "kind": "MemberExpr",
                                        "name": "counter",
                                        "isArrow": false,
                                        "type": { "qualType": "unsigned int" },
                                        "inner": [
                                            {
                                                "kind": "MemberExpr",
                                                "name": "inner",
                                                "isArrow": false,
                                                "type": { "qualType": "struct Inner" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "struct Local" },
                                                        "referencedDecl": { "kind": "ParmVarDecl", "name": "obj" }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "kind": "CallExpr",
                                        "type": { "qualType": "unsigned int" },
                                        "inner": [
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "FunctionToPointerDecay",
                                                "type": { "qualType": "unsigned int (*)(struct Local)" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "unsigned int (struct Local)" },
                                                        "referencedDecl": { "kind": "FunctionDecl", "name": "fetch_count" }
                                                    }
                                                ]
                                            },
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "LValueToRValue",
                                                "type": { "qualType": "struct Local" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "struct Local" },
                                                        "referencedDecl": { "kind": "ParmVarDecl", "name": "obj" }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "kind": "IntegerLiteral",
                        "value": "4294967295",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            { "kind": "CompoundStmt", "inner": [] }
        ]
    });
    let mut ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == "bad_if_tail_assign_shape")
        .expect("if assignment-call fixture function");
    function["name"] = serde_json::json!(function_name);
    function["type"]["qualType"] = serde_json::json!("void (struct Local)");
    function["inner"] = serde_json::json!([
        {
            "kind": "ParmVarDecl",
            "name": "obj",
            "type": { "qualType": "struct Local" }
        },
        {
            "kind": "CompoundStmt",
            "inner": [inner]
        }
    ]);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("by-value local member must fail closed in IfCondition");
    assert!(
        error
            .message
            .contains("exactly one arrow rooted at a direct mutable record-pointer DeclRef"),
        "expected local member rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_logical_and_in_if() {
    let function_name = "bad_if_assign_call_logical_and_record_ptr";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let assignment_comparison = function["inner"][2]["inner"][0]["inner"][0].clone();
    function["inner"][2]["inner"][0]["inner"][0] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "&&",
        "type": { "qualType": "int" },
        "inner": [
            assignment_comparison,
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
        ]
    });

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("logical and in if must fail closed");
    assert!(
        error.message.contains("opcode = is outside the current skeleton"),
        "expected logical-and rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_second_call() {
    let function_name = "bad_if_assign_call_second_call_record_ptr";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let call = &mut function["inner"][2]["inner"][0]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][1];
    let second_call = call.clone();
    call["inner"]
        .as_array_mut()
        .expect("direct call operands")
        .push(second_call);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("second call must fail closed");
    assert!(
        error.message.contains("second call"),
        "expected second call rejection, got {error:?}"
    );
}
