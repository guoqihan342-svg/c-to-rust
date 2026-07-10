#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_literal_field_assignment_fixture(function_name: &str) -> Value {
    let root = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct Session *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "ctx" }
    });
    let target = serde_json::json!({
        "kind": "MemberExpr",
        "name": "offset",
        "isArrow": false,
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "MemberExpr",
            "name": "position",
            "isArrow": true,
            "type": { "qualType": "struct Coordinate" },
            "inner": [{
                "kind": "ImplicitCastExpr",
                "castKind": "LValueToRValue",
                "type": { "qualType": "struct Session *" },
                "inner": [root]
            }]
        }]
    });
    let value = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "IntegralCast",
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "IntegerLiteral",
            "value": "0",
            "type": { "qualType": "int" }
        }]
    });
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "Coordinate",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "offset",
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
                "name": "Session",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "position",
                        "type": { "qualType": "struct Coordinate" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "marker",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": function_name,
                "type": { "qualType": "void (struct Session *)" },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "ctx",
                        "type": { "qualType": "struct Session *" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [{
                            "kind": "BinaryOperator",
                            "opcode": "=",
                            "type": { "qualType": "unsigned int" },
                            "inner": [target, value]
                        }]
                    }
                ]
            }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_literal_assignment_function_mut<'a>(
    ast: &'a mut Value,
    function_name: &str,
) -> &'a mut Value {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed nested literal assignment function")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_literal_assignment_target_mut(function: &mut Value) -> &mut Value {
    &mut function["inner"][1]["inner"][0]["inner"][0]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_literal_assignment_value_mut(function: &mut Value) -> &mut Value {
    &mut function["inner"][1]["inner"][0]["inner"][1]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_literal_assignment_error(ast: &Value, function_name: &str) -> String {
    match lower_function_and_globals_from_clang_ast_json_value(ast, function_name) {
        Ok(lowered) => emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect_err("boundary fixture must fail closed")
            .reason,
        Err(error) => error.message,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn set_nested_literal_leaf_type(ast: &mut Value, function_name: &str, qual_type: &str) {
    ast["inner"][0]["inner"][0]["type"]["qualType"] = serde_json::json!(qual_type);
    let function = nested_literal_assignment_function_mut(ast, function_name);
    nested_literal_assignment_target_mut(function)["type"]["qualType"] =
        serde_json::json!(qual_type);
    nested_literal_assignment_value_mut(function)["type"]["qualType"] =
        serde_json::json!(qual_type);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_literal_null_guard() -> Value {
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
                        "type": { "qualType": "struct Session *" },
                        "inner": [{
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct Session *" },
                            "referencedDecl": { "kind": "ParmVarDecl", "name": "ctx" }
                        }]
                    },
                    {
                        "kind": "ImplicitCastExpr",
                        "castKind": "NullToPointer",
                        "type": { "qualType": "struct Session *" },
                        "inner": [{
                            "kind": "IntegerLiteral",
                            "value": "0",
                            "type": { "qualType": "int" }
                        }]
                    }
                ]
            },
            { "kind": "ReturnStmt" }
        ]
    })
}
