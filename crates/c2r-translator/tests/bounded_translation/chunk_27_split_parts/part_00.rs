#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn record_scalar_add_decl_ref(name: &str, qual_type: &str) -> Value {
    serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": qual_type },
        "referencedDecl": { "kind": "ParmVarDecl", "name": name }
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn record_scalar_add_read(expr: Value, qual_type: &str) -> Value {
    serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": qual_type },
        "inner": [expr]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_record_scalar_add_fixture(function_name: &str) -> Value {
    let target_root = record_scalar_add_read(
        record_scalar_add_decl_ref("target", "struct Output *"),
        "struct Output *",
    );
    let target_nested = serde_json::json!({
        "kind": "MemberExpr",
        "name": "nested",
        "isArrow": true,
        "type": { "qualType": "struct Cell" },
        "inner": [target_root]
    });
    let target = serde_json::json!({
        "kind": "MemberExpr",
        "name": "value",
        "isArrow": false,
        "type": { "qualType": "unsigned int" },
        "inner": [target_nested]
    });
    let source_base = serde_json::json!({
        "kind": "MemberExpr",
        "name": "base",
        "isArrow": false,
        "type": { "qualType": "unsigned int" },
        "inner": [record_scalar_add_decl_ref("source", "struct Input")]
    });
    let value = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "+",
        "type": { "qualType": "unsigned int" },
        "inner": [
            record_scalar_add_read(source_base, "unsigned int"),
            record_scalar_add_read(
                record_scalar_add_decl_ref("extent", "unsigned int"),
                "unsigned int"
            )
        ]
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
                        "name": "value",
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
                "name": "Output",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "nested",
                        "type": { "qualType": "struct Cell" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "marker",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "Input",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "base",
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
                "kind": "FunctionDecl",
                "name": function_name,
                "type": {
                    "qualType": "void (struct Output *, struct Input, unsigned int)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "target",
                        "type": { "qualType": "struct Output *" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "source",
                        "type": { "qualType": "struct Input" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "extent",
                        "type": { "qualType": "unsigned int" }
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
fn nested_record_scalar_add_function_mut<'a>(
    ast: &'a mut Value,
    function_name: &str,
) -> &'a mut Value {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed record scalar add function")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_record_scalar_add_assignment_mut(function: &mut Value) -> &mut Value {
    &mut function["inner"][3]["inner"][0]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_record_scalar_add_error(ast: &Value, function_name: &str) -> String {
    match lower_function_and_globals_from_clang_ast_json_value(ast, function_name) {
        Ok(lowered) => emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect_err("out-of-bound record scalar add must fail closed")
            .reason,
        Err(error) => error.message,
    }
}
