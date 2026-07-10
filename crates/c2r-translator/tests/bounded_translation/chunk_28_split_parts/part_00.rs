#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_fixture(function_name: &str) -> Value {
    let owner_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct Owner *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "owner" }
    });
    let cursor_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": {
            "qualType": "NodeRef",
            "desugaredQualType": "struct Node *"
        },
        "referencedDecl": { "kind": "VarDecl", "name": "cursor" }
    });
    let projection = serde_json::json!({
        "kind": "MemberExpr",
        "name": "current",
        "isArrow": true,
        "type": { "qualType": "struct Node" },
        "inner": [owner_ref]
    });
    let write_target = serde_json::json!({
        "kind": "MemberExpr",
        "name": "leaf",
        "isArrow": false,
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "MemberExpr",
            "name": "nested",
            "isArrow": true,
            "type": { "qualType": "struct Cell" },
            "inner": [cursor_ref]
        }]
    });
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "Cell",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "leaf",
                        "type": { "qualType": "unsigned int" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "guard",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "Node",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "nested",
                        "type": { "qualType": "struct Cell" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "tag",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "Owner",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "current",
                        "type": { "qualType": "struct Node" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "marker",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "TypedefDecl",
                "name": "NodeRef",
                "type": { "qualType": "struct Node *" }
            },
            {
                "kind": "FunctionDecl",
                "name": function_name,
                "type": { "qualType": "_Bool (struct Owner *)" },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "owner",
                        "type": { "qualType": "struct Owner *" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "DeclStmt",
                                "inner": [{
                                    "kind": "VarDecl",
                                    "name": "cursor",
                                    "init": "c",
                                    "type": {
                                        "qualType": "NodeRef",
                                        "desugaredQualType": "struct Node *"
                                    },
                                    "inner": [{
                                        "kind": "UnaryOperator",
                                        "opcode": "&",
                                        "type": { "qualType": "struct Node *" },
                                        "inner": [projection]
                                    }]
                                }]
                            },
                            {
                                "kind": "BinaryOperator",
                                "opcode": "=",
                                "type": { "qualType": "unsigned int" },
                                "inner": [
                                    write_target,
                                    {
                                        "kind": "IntegerLiteral",
                                        "value": "37",
                                        "type": { "qualType": "unsigned int" }
                                    }
                                ]
                            },
                            {
                                "kind": "ReturnStmt",
                                "inner": [{
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "IntegralToBoolean",
                                    "type": { "qualType": "_Bool" },
                                    "inner": [{
                                        "kind": "IntegerLiteral",
                                        "value": "1",
                                        "type": { "qualType": "int" }
                                    }]
                                }]
                            }
                        ]
                    }
                ]
            }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_function_mut<'a>(ast: &'a mut Value, name: &str) -> &'a mut Value {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == name)
        .expect("renamed interior reborrow function")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_body_mut(function: &mut Value) -> &mut Vec<Value> {
    function["inner"]
        .as_array_mut()
        .expect("function children")
        .iter_mut()
        .find(|node| node["kind"] == "CompoundStmt")
        .and_then(|node| node["inner"].as_array_mut())
        .expect("interior reborrow body")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_failure(ast: &Value, name: &str) -> String {
    match lower_function_and_globals_from_clang_ast_json_value(ast, name) {
        Ok(lowered) => emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect_err("out-of-bound interior reborrow must fail closed")
            .reason,
        Err(error) => error.message,
    }
}
