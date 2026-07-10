#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_distinct_record_pointer_compound_read_requires_exact_noalias_pair() {
    let function_name = "advance_cursor_with_alias_gate";
    let ast = distinct_record_pointer_compound_read_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower noalias boundary fixture");

    let missing = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("missing noalias evidence must fail closed");
    assert!(
        missing.reason.contains("alias proof") || missing.reason.contains("noalias"),
        "{missing:?}"
    );

    let reversed = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "cursor".to_string(),
            mutable_param: "ledger".to_string(),
        }],
        ..Default::default()
    };
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        reversed,
    )
    .expect_err("reversed readonly/mutable noalias pair must fail closed");
    assert!(
        error.reason.contains("alias proof") || error.reason.contains("noalias"),
        "{error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_record_pointer_compound_read_nearest_boundaries_fail_closed() {
    let function_name = "reject_compound_read_boundary";

    let mut same_owner = distinct_record_pointer_compound_read_fixture(function_name);
    let rhs = distinct_record_pointer_compound_read_rhs_mut(&mut same_owner, function_name);
    rhs["inner"][0]["name"] = serde_json::json!("walked");
    rhs["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct WalkCursor *");
    rhs["inner"][0]["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct WalkCursor *");
    rhs["inner"][0]["inner"][0]["inner"][0]["referencedDecl"]["name"] =
        serde_json::json!("cursor");
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&same_owner, function_name)
        .expect("lower same-owner boundary candidate");
    let error = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        distinct_record_pointer_compound_read_policy(),
    )
    .expect_err("same-owner compound read must fail closed");
    assert!(
        error.reason.contains("readonly")
            || error.reason.contains("definite assignment")
            || error.reason.contains("read before"),
        "{error:?}"
    );

    let mut second_arrow = distinct_record_pointer_compound_read_fixture(function_name);
    let rhs = distinct_record_pointer_compound_read_rhs_mut(&mut second_arrow, function_name);
    let ledger_root = rhs["inner"][0]["inner"][0].clone();
    rhs["inner"][0]["inner"][0] = serde_json::json!({
        "kind": "MemberExpr",
        "name": "next",
        "isArrow": true,
        "type": { "qualType": "struct StepLedger *" },
        "inner": [ledger_root]
    });
    let error = lower_function_and_globals_from_clang_ast_json_value(&second_arrow, function_name)
        .expect_err("second-arrow compound read must fail closed");
    assert!(
        error.message.contains("record field compound assignment RHS")
            || error.message.contains("direct")
            || error.message.contains("member"),
        "{error:?}"
    );

    let mut call_rhs = distinct_record_pointer_compound_read_fixture(function_name);
    *distinct_record_pointer_compound_read_rhs_mut(&mut call_rhs, function_name) =
        serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "unsigned int" },
            "inner": [{
                "kind": "ImplicitCastExpr",
                "castKind": "FunctionToPointerDecay",
                "type": { "qualType": "unsigned int (*)(void)" },
                "inner": [{
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned int (void)" },
                    "referencedDecl": { "kind": "FunctionDecl", "name": "derive_step" }
                }]
            }]
        });
    let error = lower_function_and_globals_from_clang_ast_json_value(&call_rhs, function_name)
        .expect_err("effectful call RHS must remain rejected");
    assert!(
        error.message.contains("record field compound assignment RHS"),
        "{error:?}"
    );
}
