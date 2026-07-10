#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn distinct_record_pointer_compound_read_fixture(function_name: &str) -> Value {
    let cursor_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct WalkCursor *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "cursor" }
    });
    let ledger_ref = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": "struct StepLedger *" },
        "referencedDecl": { "kind": "ParmVarDecl", "name": "ledger" }
    });
    let target = serde_json::json!({
        "kind": "MemberExpr",
        "name": "walked",
        "isArrow": true,
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "struct WalkCursor *" },
            "inner": [cursor_ref]
        }]
    });
    let rhs_member = serde_json::json!({
        "kind": "MemberExpr",
        "name": "step_size",
        "isArrow": true,
        "type": { "qualType": "unsigned int" },
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "struct StepLedger *" },
            "inner": [ledger_ref]
        }]
    });
    let rhs = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "unsigned int" },
        "inner": [rhs_member]
    });
    let compound = serde_json::json!({
        "kind": "CompoundAssignOperator",
        "opcode": "+=",
        "type": { "qualType": "unsigned int" },
        "computeLHSType": { "qualType": "unsigned int" },
        "computeResultType": { "qualType": "unsigned int" },
        "inner": [target, rhs]
    });
    let ledger_record = serde_json::json!({
        "kind": "RecordDecl",
        "tagUsed": "struct",
        "name": "StepLedger",
        "completeDefinition": true,
        "inner": [{
            "kind": "FieldDecl",
            "name": "step_size",
            "type": { "qualType": "unsigned int" }
        }]
    });
    let cursor_record = serde_json::json!({
        "kind": "RecordDecl",
        "tagUsed": "struct",
        "name": "WalkCursor",
        "completeDefinition": true,
        "inner": [{
            "kind": "FieldDecl",
            "name": "walked",
            "type": { "qualType": "unsigned int" }
        }]
    });
    let function = serde_json::json!({
        "kind": "FunctionDecl",
        "name": function_name,
        "type": { "qualType": "void (struct StepLedger *, struct WalkCursor *)" },
        "inner": [
            {
                "kind": "ParmVarDecl",
                "name": "ledger",
                "type": { "qualType": "struct StepLedger *" }
            },
            {
                "kind": "ParmVarDecl",
                "name": "cursor",
                "type": { "qualType": "struct WalkCursor *" }
            },
            { "kind": "CompoundStmt", "inner": [compound] }
        ]
    });
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [ledger_record, cursor_record, function]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn distinct_record_pointer_compound_read_policy() -> EmitPolicy {
    EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "ledger".to_string(),
            mutable_param: "cursor".to_string(),
        }],
        ..Default::default()
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn distinct_record_pointer_compound_read_rhs_mut<'a>(
    ast: &'a mut Value,
    function_name: &str,
) -> &'a mut Value {
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed compound-read fixture function");
    &mut function["inner"][2]["inner"][0]["inner"][1]
}
