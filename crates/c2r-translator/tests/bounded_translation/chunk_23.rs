#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn if_assignment_call_distinct_record_borrows_fixture(function_name: &str) -> Value {
    let mut ast = if_assignment_call_record_pointer_nested_member_fixture(function_name);
    let declarations = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations");
    declarations.insert(
        0,
        serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "Database",
            "completeDefinition": true,
            "inner": [
                { "kind": "FieldDecl", "name": "generation", "type": { "qualType": "unsigned int" } }
            ]
        }),
    );
    declarations.insert(
        0,
        serde_json::json!({
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "name": "Sector",
            "completeDefinition": true,
            "inner": [
                { "kind": "FieldDecl", "name": "offset", "type": { "qualType": "unsigned int" } }
            ]
        }),
    );
    let function = declarations
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let ctx_param = function["inner"][0].clone();
    let seed_param = function["inner"][1].clone();
    let if_stmt = function["inner"][2]["inner"][0].clone();
    function["type"]["qualType"] = serde_json::json!(
        "void (struct Database *, struct Context *, unsigned int, struct Sector)"
    );
    function["inner"] = serde_json::json!([
        {
            "kind": "ParmVarDecl",
            "name": "database",
            "type": { "qualType": "struct Database *" }
        },
        ctx_param,
        seed_param,
        {
            "kind": "ParmVarDecl",
            "name": "sector_seed",
            "type": { "qualType": "struct Sector" }
        },
        {
            "kind": "CompoundStmt",
            "inner": [
                {
                    "kind": "DeclStmt",
                    "inner": [{
                        "kind": "VarDecl",
                        "name": "sector",
                        "init": "c",
                        "type": { "qualType": "struct Sector" },
                        "inner": [{
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct Sector" },
                            "referencedDecl": { "kind": "ParmVarDecl", "name": "sector_seed" }
                        }]
                    }]
                },
                if_stmt
            ]
        }
    ]);
    let call = &mut function["inner"][4]["inner"][1]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][1];
    let callee = call["inner"][0].clone();
    call["inner"] = serde_json::json!([
        callee,
        {
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "struct Database *" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "struct Database *" },
                "referencedDecl": { "kind": "ParmVarDecl", "name": "database" }
            }]
        },
        {
            "kind": "UnaryOperator",
            "opcode": "&",
            "type": { "qualType": "struct Sector *" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "struct Sector" },
                "referencedDecl": { "kind": "VarDecl", "name": "sector" }
            }]
        },
        {
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "struct Context *" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "struct Context *" },
                "referencedDecl": { "kind": "ParmVarDecl", "name": "ctx" }
            }]
        }
    ]);
    call["inner"][0]["type"]["qualType"] = serde_json::json!(
        "unsigned int (*)(struct Database *, struct Sector *, struct Context *)"
    );
    call["inner"][0]["inner"][0]["type"]["qualType"] = serde_json::json!(
        "unsigned int (struct Database *, struct Sector *, struct Context *)"
    );
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_accepts_distinct_record_borrow_arguments() {
    let function_name = "if_assign_call_distinct_record_borrows";
    let ast = if_assignment_call_distinct_record_borrows_fixture(function_name);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower distinct record borrow assignment-call comparison");
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "database".to_string(),
            mutable_param: "ctx".to_string(),
        }],
        ..Default::default()
    };
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        policy,
    )
    .expect("emit distinct record borrow assignment-call comparison with noalias evidence");
    let rust = &emitted.rust;
    assert!(
        rust.contains("fetch_value(database, &mut sector, ctx)"),
        "missing three-record call: {rust}"
    );
    assert!(
        rust.contains("ctx.address.threshold = fetch_value"),
        "missing nested assignment: {rust}"
    );

    let runtime_rust = format!(
        "fn fetch_value(_database: &mut Database, sector: &mut Sector, _ctx: &mut Context) -> u32 {{ sector.offset + 1 }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-if-assignment-call-distinct-record-borrows",
        &runtime_rust,
        r#"
    let mut database = Database { generation: 7 };
    let mut ctx = Context { address: Address { threshold: 0 } };
    let sector = Sector { offset: 41 };
    if_assign_call_distinct_record_borrows(&mut database, &mut ctx, 0, sector);
    assert_eq!(ctx.address.threshold, 42);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_distinct_record_borrows_require_noalias_contract() {
    let function_name = "bad_if_assign_call_missing_record_noalias";
    let ast = if_assignment_call_distinct_record_borrows_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower missing-noalias distinct record borrow candidate");

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("multiple pointer params without noalias must fail closed");
    assert!(
        error
            .reason
            .contains("requires exactly one pointer param for alias proof"),
        "expected noalias refusal, got {error:?}"
    );
}
