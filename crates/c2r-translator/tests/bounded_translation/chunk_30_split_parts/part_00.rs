#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn rewrite_json_string(value: &mut Value, from: &str, to: &str) {
    match value {
        Value::String(text) => *text = text.replace(from, to),
        Value::Array(values) => {
            for value in values {
                rewrite_json_string(value, from, to);
            }
        }
        Value::Object(values) => {
            for value in values.values_mut() {
                rewrite_json_string(value, from, to);
            }
        }
        _ => {}
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_reborrow_fixture(function_name: &str) -> Value {
    let mut ast = run_once_reborrow_fixture(function_name);
    rewrite_json_string(&mut ast, "const struct Source *", "struct Source *");
    ast["inner"].as_array_mut().unwrap().insert(
        4,
        serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "Seed",
            "completeDefinition": true,
            "inner": [{
                "kind": "FieldDecl",
                "name": "token",
                "type": { "qualType": "unsigned int" }
            }]
        }),
    );

    let function = interior_reborrow_function_mut(&mut ast, function_name);
    function["type"]["qualType"] =
        serde_json::json!("_Bool (struct Owner *, struct Source *, struct Seed)");
    function["inner"].as_array_mut().unwrap().insert(
        2,
        serde_json::json!({
            "kind": "ParmVarDecl",
            "name": "seed",
            "type": { "qualType": "struct Seed" }
        }),
    );

    let body = interior_reborrow_body_mut(function);
    let loop_body = body[2]["inner"][1]["inner"].as_array_mut().unwrap();
    let clear = loop_body[0].clone();
    let reset = loop_body[1].clone();
    let owner_add = loop_body[2].clone();
    let continue_stmt = loop_body[3].clone();
    let miss_return = loop_body[4].clone();
    let target = reset["inner"][0].clone();
    let source_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct Source *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "source" }
    });
    let seed_local_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct Seed" },
        "referencedDecl": { "kind": "VarDecl", "name": "seed_local" }
    });
    let alias_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": {
            "qualType": "NodeRef",
            "desugaredQualType": "struct Node *"
        },
        "referencedDecl": { "kind": "VarDecl", "name": "cursor" }
    });
    let call = serde_json::json!({
        "kind": "CallExpr",
        "type": { "qualType": "unsigned int" },
        "inner": [
            {
                "kind": "ImplicitCastExpr",
                "castKind": "FunctionToPointerDecay",
                "type": {
                    "qualType": "unsigned int (*)(struct Source *, struct Seed *, struct Node *)"
                },
                "inner": [{
                    "kind": "DeclRefExpr",
                    "type": {
                        "qualType": "unsigned int (struct Source *, struct Seed *, struct Node *)"
                    },
                    "referencedDecl": { "kind": "FunctionDecl", "name": "sample_next" }
                }]
            },
            {
                "kind": "ImplicitCastExpr",
                "castKind": "LValueToRValue",
                "type": { "qualType": "struct Source *" },
                "inner": [source_ref]
            },
            {
                "kind": "UnaryOperator",
                "opcode": "&",
                "type": { "qualType": "struct Seed *" },
                "inner": [seed_local_ref]
            },
            {
                "kind": "ImplicitCastExpr",
                "castKind": "LValueToRValue",
                "type": { "qualType": "struct Node *" },
                "inner": [alias_ref]
            }
        ]
    });
    let comparison = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "==",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "ParenExpr",
                "type": { "qualType": "unsigned int" },
                "inner": [{
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": "unsigned int" },
                    "inner": [target, call]
                }]
            },
            {
                "kind": "IntegerLiteral",
                "value": "4294967295",
                "type": { "qualType": "unsigned int" }
            }
        ]
    });
    *loop_body = vec![
        clear,
        serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                comparison,
                {
                    "kind": "CompoundStmt",
                    "inner": [reset, owner_add, continue_stmt]
                }
            ]
        }),
        miss_return,
    ];
    body.insert(
        1,
        serde_json::json!({
            "kind": "DeclStmt",
            "inner": [{
                "kind": "VarDecl",
                "name": "seed_local",
                "init": "c",
                "type": { "qualType": "struct Seed" },
                "inner": [{
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "struct Seed" },
                    "inner": [{
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "struct Seed" },
                        "referencedDecl": { "kind": "ParmVarDecl", "name": "seed" }
                    }]
                }]
            }]
        }),
    );
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_reborrow_policy() -> EmitPolicy {
    EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "source".to_string(),
            mutable_param: "owner".to_string(),
        }],
        ..Default::default()
    }
}
