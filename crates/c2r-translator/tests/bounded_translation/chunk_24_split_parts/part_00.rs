#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn do_while_record_pointer_assignment_call_fixture(function_name: &str) -> Value {
    let mut ast: Value = serde_json::from_str(r#"{
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "DispatchArena",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "epoch",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "SweepCursor",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "next_slot",
                        "type": { "qualType": "unsigned int" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "distance",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "seek_next",
                "type": {
                    "qualType": "unsigned int (struct DispatchArena *, unsigned int)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "arena",
                        "type": { "qualType": "struct DispatchArena *" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "distance",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "__FUNCTION__",
                "type": {
                    "qualType": "void (struct DispatchArena *, struct SweepCursor *)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "arena",
                        "type": { "qualType": "struct DispatchArena *" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "walker",
                        "type": { "qualType": "struct SweepCursor *" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "DoStmt",
                                "inner": [
                                    { "kind": "CompoundStmt", "inner": [] },
                                    {
                                        "kind": "BinaryOperator",
                                        "opcode": "!=",
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
                                                                "name": "next_slot",
                                                                "isArrow": true,
                                                                "type": { "qualType": "unsigned int" },
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
                                                                        "type": {
                                                                            "qualType": "unsigned int (*)(struct DispatchArena *, unsigned int)"
                                                                        },
                                                                        "inner": [
                                                                            {
                                                                                "kind": "DeclRefExpr",
                                                                                "type": {
                                                                                    "qualType": "unsigned int (struct DispatchArena *, unsigned int)"
                                                                                },
                                                                                "referencedDecl": {
                                                                                    "kind": "FunctionDecl",
                                                                                    "name": "seek_next"
                                                                                }
                                                                            }
                                                                        ]
                                                                    },
                                                                    {
                                                                        "kind": "ImplicitCastExpr",
                                                                        "castKind": "LValueToRValue",
                                                                        "type": { "qualType": "struct DispatchArena *" },
                                                                        "inner": [
                                                                            {
                                                                                "kind": "DeclRefExpr",
                                                                                "type": { "qualType": "struct DispatchArena *" },
                                                                                "referencedDecl": {
                                                                                    "kind": "ParmVarDecl",
                                                                                    "name": "arena"
                                                                                }
                                                                            }
                                                                        ]
                                                                    },
                                                                    {
                                                                        "kind": "ImplicitCastExpr",
                                                                        "castKind": "LValueToRValue",
                                                                        "type": { "qualType": "unsigned int" },
                                                                        "inner": [
                                                                            {
                                                                                "kind": "MemberExpr",
                                                                                "name": "distance",
                                                                                "isArrow": true,
                                                                                "type": { "qualType": "unsigned int" },
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
                                                                                    }
                                                                                ]
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
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }"#)
    .expect("renamed do-while record-pointer assignment-call fixture JSON");
    ast["inner"][3]["name"] = serde_json::json!(function_name);
    ast
}
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn do_while_record_pointer_fixture_function_mut<'a>(
    ast: &'a mut Value,
    function_name: &str,
) -> &'a mut Value {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed do-while record-pointer fixture function")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn do_while_record_pointer_fixture_assignment_mut(function: &mut Value) -> &mut Value {
    &mut function["inner"][2]["inner"][0]["inner"][1]["inner"][0]["inner"][0]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn do_while_record_pointer_fixture_policy() -> EmitPolicy {
    EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "arena".to_string(),
            mutable_param: "walker".to_string(),
        }],
        ..Default::default()
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assert_do_while_record_pointer_fixture_rejected(
    ast: &Value,
    function_name: &str,
    expected: &str,
) {
    let error = lower_function_and_globals_from_clang_ast_json_value(ast, function_name)
        .expect_err("out-of-bound do-while record-pointer assignment-call must fail closed");
    assert!(
        error.message.contains(expected),
        "expected {expected:?}, got {error:?}"
    );
}
