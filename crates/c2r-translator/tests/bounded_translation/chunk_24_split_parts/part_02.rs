#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_rejects_nullable_do_while_assignment_call_record_pointer_root() {
    let function_name = "reject_nullable_sweep_cursor";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let do_stmt = function["inner"][2]["inner"][0].clone();
    function["inner"][2]["inner"] = serde_json::json!([
        {
            "kind": "IfStmt",
            "inner": [
                {
                    "kind": "BinaryOperator",
                    "opcode": "==",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "struct SweepCursor *" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "struct SweepCursor *" },
                                    "referencedDecl": {
                                        "kind": "ParmVarDecl",
                                        "name": "walker"
                                    }
                                }
                            ]
                        },
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "NullToPointer",
                            "type": { "qualType": "struct SweepCursor *" },
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "value": "0",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        }
                    ]
                },
                { "kind": "CompoundStmt", "inner": [] }
            ]
        },
        do_stmt
    ]);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower nullable record-pointer boundary fixture");
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        do_while_record_pointer_fixture_policy(),
    )
    .expect_err("nullable record-pointer assignment-call target must fail closed");
    assert!(error.reason.contains("nullable"), "{error:?}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_rejects_assignment_call_sibling_read_when_owner_is_mutably_borrowed() {
    let function_name = "reject_borrowed_sweep_cursor_sibling";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    ast["inner"][2]["type"]["qualType"] = serde_json::json!(
        "unsigned int (struct DispatchArena *, struct SweepCursor *, unsigned int)"
    );
    ast["inner"][2]["inner"].as_array_mut().expect("callee params").insert(
        1,
        serde_json::json!({
            "kind": "ParmVarDecl",
            "name": "walker",
            "type": { "qualType": "struct SweepCursor *" }
        }),
    );
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let assignment = do_while_record_pointer_fixture_assignment_mut(function);
    let call = &mut assignment["inner"][1];
    call["inner"][0]["type"]["qualType"] = serde_json::json!(
        "unsigned int (*)(struct DispatchArena *, struct SweepCursor *, unsigned int)"
    );
    call["inner"][0]["inner"][0]["type"]["qualType"] = serde_json::json!(
        "unsigned int (struct DispatchArena *, struct SweepCursor *, unsigned int)"
    );
    call["inner"].as_array_mut().expect("direct call operands").insert(
        2,
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "struct SweepCursor *" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "struct SweepCursor *" },
                    "referencedDecl": { "kind": "ParmVarDecl", "name": "walker" }
                }
            ]
        }),
    );
    let do_stmt = function["inner"][2]["inner"][0].clone();
    function["inner"][2]["inner"] = serde_json::json!([
        {
            "kind": "BinaryOperator",
            "opcode": "=",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "distance",
                    "isArrow": true,
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct SweepCursor *" },
                            "referencedDecl": { "kind": "ParmVarDecl", "name": "walker" }
                        }
                    ]
                },
                { "kind": "IntegerLiteral", "value": "27", "type": { "qualType": "unsigned int" } }
            ]
        },
        do_stmt
    ]);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower same-owner mutable borrow boundary fixture");
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        do_while_record_pointer_fixture_policy(),
    )
    .expect_err("same owner mutable borrow plus sibling read must fail closed");
    assert!(
        error
            .reason
            .contains("cannot have a sibling argument that reads the same record"),
        "{error:?}"
    );
}
