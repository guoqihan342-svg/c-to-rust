#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_rejects_nullable_arithmetic_cast_and_stored_alias() {
    for case in ["nullable", "arithmetic", "cast", "stored_alias"] {
        let function_name = format!("reject_{case}_projection");
        let mut ast = interior_reborrow_fixture(&function_name);
        let function = interior_reborrow_function_mut(&mut ast, &function_name);
        let body = interior_reborrow_body_mut(function);
        match case {
            "nullable" => body.insert(
                0,
                serde_json::json!({
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
                                    "type": { "qualType": "struct Owner *" },
                                    "inner": [{
                                        "kind": "DeclRefExpr",
                                        "type": { "qualType": "struct Owner *" },
                                        "referencedDecl": {
                                            "kind": "ParmVarDecl",
                                            "name": "owner"
                                        }
                                    }]
                                },
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "NullToPointer",
                                    "type": { "qualType": "struct Owner *" },
                                    "inner": [{
                                        "kind": "IntegerLiteral",
                                        "value": "0",
                                        "type": { "qualType": "int" }
                                    }]
                                }
                            ]
                        },
                        { "kind": "CompoundStmt", "inner": [] }
                    ]
                }),
            ),
            "arithmetic" => {
                let address = body[0]["inner"][0]["inner"][0].clone();
                body[0]["inner"][0]["inner"][0] = serde_json::json!({
                    "kind": "BinaryOperator",
                    "opcode": "+",
                    "type": { "qualType": "struct Node *" },
                    "inner": [
                        address,
                        {
                            "kind": "IntegerLiteral",
                            "value": "0",
                            "type": { "qualType": "int" }
                        }
                    ]
                });
            }
            "cast" => {
                let address = body[0]["inner"][0]["inner"][0].clone();
                body[0]["inner"][0]["inner"][0] = serde_json::json!({
                    "kind": "CStyleCastExpr",
                    "castKind": "BitCast",
                    "type": { "qualType": "struct Node *" },
                    "inner": [address]
                });
            }
            "stored_alias" => body.insert(
                1,
                serde_json::json!({
                    "kind": "DeclStmt",
                    "inner": [{
                        "kind": "VarDecl",
                        "name": "saved",
                        "init": "c",
                        "type": {
                            "qualType": "NodeRef",
                            "desugaredQualType": "struct Node *"
                        },
                        "inner": [{
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "struct Node *" },
                            "inner": [{
                                "kind": "DeclRefExpr",
                                "type": {
                                    "qualType": "NodeRef",
                                    "desugaredQualType": "struct Node *"
                                },
                                "referencedDecl": { "kind": "VarDecl", "name": "cursor" }
                            }]
                        }]
                    }]
                }),
            ),
            _ => unreachable!(),
        }
        let reason = interior_reborrow_failure(&ast, &function_name);
        assert!(!reason.is_empty(), "{case} must fail closed");
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_rejects_nonconstant_or_effectful_write() {
    for case in ["variable", "call"] {
        let function_name = format!("reject_{case}_projection_write");
        let mut ast = interior_reborrow_fixture(&function_name);
        let function = interior_reborrow_function_mut(&mut ast, &function_name);
        let body = interior_reborrow_body_mut(function);
        body[1]["inner"][1] = match case {
            "variable" => serde_json::json!({
                "kind": "DeclRefExpr",
                "type": { "qualType": "unsigned int" },
                "referencedDecl": { "kind": "VarDecl", "name": "runtime_value" }
            }),
            "call" => serde_json::json!({
                "kind": "CallExpr",
                "type": { "qualType": "unsigned int" },
                "inner": [{
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned int (void)" },
                    "referencedDecl": { "kind": "FunctionDecl", "name": "next_value" }
                }]
            }),
            _ => unreachable!(),
        };
        let reason = interior_reborrow_failure(&ast, &function_name);
        assert!(reason.contains("constant") || reason.contains("call"), "{case}: {reason}");
    }
}
