#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_do_while_tail_fixture(function_name: &str) -> Value {
    let mut ast = assignment_call_reborrow_fixture(function_name);
    let function = interior_reborrow_function_mut(&mut ast, function_name);
    let body = interior_reborrow_body_mut(function);
    let loop_body = body[3]["inner"][1]["inner"]
        .as_array_mut()
        .expect("run-once loop body");
    let clear = loop_body[0].clone();
    let mut comparison = loop_body[1]["inner"][0].clone();
    comparison["opcode"] = serde_json::json!("!=");
    let miss_return = loop_body[2].clone();
    *loop_body = vec![
        clear,
        serde_json::json!({
            "kind": "DoStmt",
            "inner": [
                { "kind": "CompoundStmt", "inner": [] },
                comparison
            ]
        }),
        miss_return,
    ];
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_do_while_tail_mut<'a>(
    ast: &'a mut Value,
    function_name: &str,
) -> &'a mut Value {
    let function = interior_reborrow_function_mut(ast, function_name);
    let body = interior_reborrow_body_mut(function);
    &mut body[3]["inner"][1]["inner"][1]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn interior_reborrow_do_while_tail_failure(ast: &Value, function_name: &str) -> String {
    match lower_function_and_globals_from_clang_ast_json_value(ast, function_name) {
        Ok(lowered) => emit_rust_from_ir_with_globals_and_policy(
            &lowered.function_ir,
            &lowered.globals,
            assignment_call_reborrow_policy(),
        )
        .expect_err("out-of-slice interior reborrow do-while tail must fail closed")
        .reason,
        Err(error) => error.message,
    }
}
