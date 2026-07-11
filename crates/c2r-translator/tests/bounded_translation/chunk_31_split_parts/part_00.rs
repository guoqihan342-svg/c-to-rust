#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn zero_start_assignment_call_fixture(function_name: &str) -> Value {
    let mut ast = assignment_call_reborrow_fixture(function_name);
    let function = interior_reborrow_function_mut(&mut ast, function_name);
    function["type"]["qualType"] = serde_json::json!(
        "_Bool (struct Owner *, struct Source *, struct Seed, unsigned int)"
    );
    function["inner"].as_array_mut().unwrap().insert(
        3,
        serde_json::json!({
            "kind": "ParmVarDecl",
            "name": "offset",
            "type": { "qualType": "unsigned int" }
        }),
    );

    let body = interior_reborrow_body_mut(function);
    let loop_body = body[3]["inner"][1]["inner"].as_array_mut().unwrap();
    let clear = loop_body[0].clone();
    let assignment_call_branch = loop_body[1].clone();
    let miss_return = loop_body[2].clone();
    let target =
        assignment_call_branch["inner"][0]["inner"][0]["inner"][0]["inner"][0].clone();
    let target_read = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "unsigned int" },
        "inner": [target.clone()]
    });
    let seed_field_read = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "MemberExpr",
            "name": "token",
            "isArrow": false,
            "type": { "qualType": "unsigned int" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "struct Seed" },
                "referencedDecl": { "kind": "VarDecl", "name": "seed_local" }
            }]
        }]
    });
    let offset_read = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "DeclRefExpr",
            "type": { "qualType": "unsigned int" },
            "referencedDecl": { "kind": "ParmVarDecl", "name": "offset" }
        }]
    });
    *loop_body = vec![
        clear,
        serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                {
                    "kind": "BinaryOperator",
                    "opcode": "==",
                    "type": { "qualType": "int" },
                    "inner": [
                        target_read,
                        {
                            "kind": "IntegerLiteral",
                            "value": "0",
                            "type": { "qualType": "unsigned int" }
                        }
                    ]
                },
                {
                    "kind": "CompoundStmt",
                    "inner": [{
                        "kind": "BinaryOperator",
                        "opcode": "=",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            target,
                            {
                                "kind": "BinaryOperator",
                                "opcode": "+",
                                "type": { "qualType": "unsigned int" },
                                "inner": [seed_field_read, offset_read]
                            }
                        ]
                    }]
                },
                assignment_call_branch
            ]
        }),
        miss_return,
    ];
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn zero_start_assignment_call_failure(ast: &Value, function_name: &str) -> String {
    match lower_function_and_globals_from_clang_ast_json_value(ast, function_name) {
        Ok(lowered) => emit_rust_from_ir_with_globals_and_policy(
            &lowered.function_ir,
            &lowered.globals,
            assignment_call_reborrow_policy(),
        )
        .expect_err("adjacent zero-start assignment-call drift must fail closed")
        .reason,
        Err(error) => error.message,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn zero_start_outer_if_mut<'a>(ast: &'a mut Value, function_name: &str) -> &'a mut Value {
    let function = interior_reborrow_function_mut(ast, function_name);
    let body = interior_reborrow_body_mut(function);
    &mut body[3]["inner"][1]["inner"][1]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assert_zero_start_failure(reason: &str, case: &str) {
    assert!(
        !reason.trim().is_empty()
            && (reason.contains("interior reborrow")
                || reason.contains("zero")
                || reason.contains("offset")
                || reason.contains("parameter")
                || reason.contains("assignment-call")
                || reason.contains("record scalar add")),
        "{case}: {reason}"
    );
}
