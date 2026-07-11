
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_lowers_missing_step_for_to_none_without_clang_and_runs() {
    let function_name = "accumulate_without_step";
    let ast = renamed_missing_step_for_ast(function_name);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower for loop with a condition and an empty step slot");
    let [IrStmt::Decl { .. }, IrStmt::For { step, .. }, IrStmt::Return { .. }] =
        lowered.function_ir.body.as_slice()
    else {
        panic!(
            "unexpected missing-step function body: {:?}",
            lowered.function_ir.body
        );
    };
    assert!(step.is_none(), "missing step must stay None, got {step:?}");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit for loop through the existing no-step path");
    let rust = &emitted.rust;
    let body_increment = "i = i.checked_add(1i32).expect(\"signed addition overflow\");";
    assert_eq!(rust.matches(body_increment).count(), 1, "{rust}");
    assert!(rust.contains("continue;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-for-missing-step",
        rust,
        "assert_eq!(accumulate_without_step(0i32), 0i32);\n\
         assert_eq!(accumulate_without_step(1i32), 1i32);\n\
         assert_eq!(accumulate_without_step(4i32), 4i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_missing_step_for_keeps_adjacent_boundaries_fail_closed() {
    let function_name = "bounded_missing_step_loop";
    let base = renamed_missing_step_for_ast(function_name);
    let mut cases = Vec::new();

    let mut missing_condition = base.clone();
    missing_step_for_inner(&mut missing_condition)[2] = serde_json::json!({});
    cases.push((
        "missing condition",
        missing_condition,
        "unsupported_clang_stmt",
        "ForStmt without condition",
    ));

    let mut condition_variable = base.clone();
    missing_step_for_inner(&mut condition_variable)[1] =
        serde_json::json!({ "kind": "VarDecl", "name": "guard" });
    cases.push((
        "condition variable",
        condition_variable,
        "unsupported_clang_stmt",
        "ForStmt condition variable",
    ));

    let mut unsupported_init = base.clone();
    missing_step_for_inner(&mut unsupported_init)[0] = serde_json::json!({ "kind": "CallExpr" });
    cases.push((
        "unsupported init",
        unsupported_init,
        "unsupported_clang_stmt",
        "ForStmt init CallExpr",
    ));

    let mut unsupported_condition = base.clone();
    missing_step_for_inner(&mut unsupported_condition)[2] = serde_json::json!({
        "kind": "MysteryExpr",
        "type": { "qualType": "int" }
    });
    cases.push((
        "unsupported condition",
        unsupported_condition,
        "unsupported_clang_expr",
        "MysteryExpr",
    ));

    let mut unsupported_body = base;
    missing_step_for_inner(&mut unsupported_body)[4] = serde_json::json!({
        "kind": "CompoundStmt",
        "inner": [{ "kind": "MysteryStmt" }]
    });
    cases.push((
        "unsupported body",
        unsupported_body,
        "unsupported_clang_stmt",
        "MysteryStmt",
    ));

    for (label, ast, expected_kind, expected_message) in cases {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err(label);
        assert_eq!(error.kind, expected_kind, "{label}: {error:?}");
        assert!(
            error.message.contains(expected_message),
            "{label}: {error:?}"
        );
    }
}
