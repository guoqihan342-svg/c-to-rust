#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_pointer_value_call_and_return_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/pointer_value_boundary_ast.json"
    ))
    .expect("fixture JSON");

    let lowered_call = lower_function_and_globals_from_clang_ast_json_value(&ast, "call_take_ptr")
        .expect("lower pointer value call fixture without invoking clang");
    let call_error =
        emit_rust_from_ir_with_globals(&lowered_call.function_ir, &lowered_call.globals)
            .expect_err("pointer value call arg must fail closed");
    assert!(
        call_error
            .reason
            .contains("call arg[0] pointer value argument"),
        "{:?}",
        call_error.reason
    );
    assert!(
        call_error.reason.contains("const int *"),
        "{:?}",
        call_error.reason
    );

    let lowered_return =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "return_pointer")
            .expect("lower pointer value return fixture without invoking clang");
    let return_error =
        emit_rust_from_ir_with_globals(&lowered_return.function_ir, &lowered_return.globals)
            .expect_err("pointer value return must fail closed");
    assert!(
        return_error.reason.contains("pointer value return"),
        "{:?}",
        return_error.reason
    );
    assert!(
        return_error.reason.contains("const int *"),
        "{:?}",
        return_error.reason
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_function_name_decay_argument_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/function_decay_boundary_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "call_with_function_value")
            .expect("function-to-pointer decay argument should stay visible in typed IR");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for bounded function name decay argument");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn call_with_function_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return apply(helper, value);"), "{rust}");
    let rust_with_helpers = format!(
        "fn helper(value: i32) -> i32 {{ value + 1 }}\nfn apply(func: fn(i32) -> i32, value: i32) -> i32 {{ func(value) }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-function-name-decay-argument",
        &rust_with_helpers,
        "assert_eq!(call_with_function_value(41i32), 42i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_function_pointer_parameter_call_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/function_pointer_call_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "call_fn")
        .expect("lower function pointer parameter call fixture without invoking clang");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for bounded function pointer parameter call");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn call_fn(fp: fn(i32) -> i32, value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return fp(value);"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-function-pointer-param-call",
        rust,
        "fn inc(value: i32) -> i32 { value + 1 }\nassert_eq!(call_fn(inc, 41i32), 42i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_function_to_pointer_decay_without_lowering_evidence() {
    let i32_ty = ir_i32();
    let function_ty = ir_function_type("int (int)");
    let function_pointer_ty =
        ir_pointer("int (*)(int)", "int (*)(int)", function_ty.clone(), false);
    let decay_expr: IrExpr = serde_json::from_value(serde_json::json!({
        "FunctionToPointerDecay": {
            "target": serde_json::to_value(&function_pointer_ty).unwrap(),
            "expr": serde_json::to_value(ir_var("helper", function_ty)).unwrap(),
            "source_span": null
        }
    }))
    .expect("deserialize explicit function-to-pointer decay IR node");
    let ir = IrFunction {
        name: "bad_function_decay_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Expr {
                expr: decay_expr,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("function-to-pointer decay must stay fail closed");
    assert!(error.reason.contains("function-to-pointer decay"));
    assert!(error.reason.contains("function pointer value"));
    assert!(error.reason.contains("explicit function-pointer lowering"));
}
