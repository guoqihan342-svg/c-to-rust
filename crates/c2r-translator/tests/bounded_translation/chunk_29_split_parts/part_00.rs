#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn run_once_reborrow_bool(value: u64) -> Value {
    serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "IntegralToBoolean",
        "type": { "qualType": "_Bool" },
        "inner": [{
            "kind": "IntegerLiteral",
            "value": value.to_string(),
            "type": { "qualType": "int" }
        }]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn run_once_reborrow_fixture(function_name: &str) -> Value {
    let mut ast = interior_reborrow_fixture(function_name);
    ast["inner"].as_array_mut().unwrap().insert(
        3,
        serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "Source",
            "completeDefinition": true,
            "inner": [{
                "kind": "FieldDecl",
                "name": "delta",
                "type": { "qualType": "unsigned int" }
            }]
        }),
    );
    let function = interior_reborrow_function_mut(&mut ast, function_name);
    function["type"]["qualType"] =
        serde_json::json!("_Bool (struct Owner *, const struct Source *)");
    function["inner"].as_array_mut().unwrap().insert(
        1,
        serde_json::json!({
            "kind": "ParmVarDecl",
            "name": "source",
            "type": { "qualType": "const struct Source *" }
        }),
    );
    let body = interior_reborrow_body_mut(function);
    let alias_decl = body[0].clone();
    let mut alias_write = body[1].clone();
    alias_write["inner"][1] = serde_json::json!({
        "kind": "IntegerLiteral",
        "value": "0",
        "type": { "qualType": "unsigned int" }
    });
    let final_return = body[2].clone();
    let sentinel_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "_Bool" },
        "referencedDecl": { "kind": "VarDecl", "name": "once" }
    });
    let owner_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct Owner *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "owner" }
    });
    let source_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "const struct Source *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "source" }
    });
    let owner_target = serde_json::json!({
        "kind": "MemberExpr",
        "name": "marker",
        "isArrow": true,
        "type": { "qualType": "unsigned int" },
        "inner": [owner_ref]
    });
    let source_read = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "MemberExpr",
            "name": "delta",
            "isArrow": true,
            "type": { "qualType": "unsigned int" },
            "inner": [source_ref]
        }]
    });
    *body = vec![
        alias_decl,
        serde_json::json!({
            "kind": "DeclStmt",
            "inner": [{
                "kind": "VarDecl",
                "name": "once",
                "init": "c",
                "type": { "qualType": "_Bool" },
                "inner": [run_once_reborrow_bool(1)]
            }]
        }),
        serde_json::json!({
            "kind": "WhileStmt",
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "_Bool" },
                    "inner": [sentinel_ref.clone()]
                },
                {
                    "kind": "CompoundStmt",
                    "inner": [
                        {
                            "kind": "BinaryOperator",
                            "opcode": "=",
                            "type": { "qualType": "_Bool" },
                            "inner": [sentinel_ref, run_once_reborrow_bool(0)]
                        },
                        alias_write,
                        {
                            "kind": "CompoundAssignOperator",
                            "opcode": "+=",
                            "type": { "qualType": "unsigned int" },
                            "computeLHSType": { "qualType": "unsigned int" },
                            "computeResultType": { "qualType": "unsigned int" },
                            "inner": [owner_target, source_read]
                        },
                        { "kind": "ContinueStmt" },
                        { "kind": "ReturnStmt", "inner": [run_once_reborrow_bool(0)] }
                    ]
                }
            ]
        }),
        final_return,
    ];
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn run_once_reborrow_policy() -> EmitPolicy {
    EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "source".to_string(),
            mutable_param: "owner".to_string(),
        }],
        ..Default::default()
    }
}
