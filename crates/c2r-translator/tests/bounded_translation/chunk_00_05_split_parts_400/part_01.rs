#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_pointer_value_call_and_return_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/pointer_value_boundary_ast.json"
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
        "../../../fixtures/clang_ast/function_decay_boundary_ast.json"
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

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "call_local_function_pointer",
    )
    .expect("local function pointer initialized from direct decay should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for local function pointer initialized from direct decay");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn call_local_function_pointer(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let fp: fn(i32) -> i32 = helper;"), "{rust}");
    assert!(rust.contains("return fp(value);"), "{rust}");
    let rust_with_helper = format!("fn helper(value: i32) -> i32 {{ value + 1 }}\n{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-local-function-pointer-direct-decay",
        &rust_with_helper,
        "assert_eq!(call_local_function_pointer(41i32), 42i32);",
    );

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "return_function_pointer")
            .expect("function pointer return initialized from direct decay should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for function pointer return initialized from direct decay");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn return_function_pointer() -> fn(i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return helper;"), "{rust}");
    let rust_with_helper = format!("fn helper(value: i32) -> i32 {{ value + 1 }}\n{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-function-pointer-return-direct-decay",
        &rust_with_helper,
        "assert_eq!(return_function_pointer()(41i32), 42i32);",
    );

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "call_assigned_function_pointer",
    )
    .expect("function pointer assigned from direct decay should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust for function pointer assigned from direct decay");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn call_assigned_function_pointer(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut fp: fn(i32) -> i32;"), "{rust}");
    assert!(rust.contains("fp = helper;"), "{rust}");
    assert!(rust.contains("return fp(value);"), "{rust}");
    let rust_with_helper = format!("fn helper(value: i32) -> i32 {{ value + 1 }}\n{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-assigned-function-pointer-direct-decay",
        &rust_with_helper,
        "assert_eq!(call_assigned_function_pointer(41i32), 42i32);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_function_pointer_parameter_call_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/function_pointer_call_ast.json"
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
fn typed_ir_emits_local_function_pointer_initialized_from_direct_function_decay() {
    let i32_ty = ir_i32();
    let function_ty = ir_function_type("int (int)");
    let function_pointer_ty =
        ir_pointer("int (*)(int)", "int (*)(int)", function_ty.clone(), false);
    let decay_expr = IrExpr::FunctionToPointerDecay {
        target: function_pointer_ty.clone(),
        expr: Box::new(ir_var("helper", function_ty)),
        source_span: None,
    };
    let ir = IrFunction {
        name: "call_local_fp".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "fp".to_string(),
                ty: function_pointer_ty.clone(),
                init: Some(decay_expr),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fp".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit local function pointer initialized by direct decay");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn call_local_fp(value: i32) -> i32"), "{rust}");
    assert!(rust.contains("let fp: fn(i32) -> i32 = helper;"), "{rust}");
    assert!(rust.contains("return fp(value);"), "{rust}");
    let rust_with_helper = format!("fn helper(value: i32) -> i32 {{ value + 1 }}\n{rust}");
    assert_rust_snippet_runs(
        "typed-ir-local-function-pointer-direct-decay",
        &rust_with_helper,
        "assert_eq!(call_local_fp(41i32), 42i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_function_pointer_return_from_direct_function_decay() {
    let function_ty = ir_function_type("int (int)");
    let function_pointer_ty =
        ir_pointer("int (*)(int)", "int (*)(int)", function_ty.clone(), false);
    let decay_expr = IrExpr::FunctionToPointerDecay {
        target: function_pointer_ty.clone(),
        expr: Box::new(ir_var("helper", function_ty)),
        source_span: None,
    };
    let ir = IrFunction {
        name: "choose_helper".to_string(),
        return_type: function_pointer_ty,
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(decay_expr),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit function pointer return from direct decay");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn choose_helper() -> fn(i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return helper;"), "{rust}");
    let rust_with_helper = format!("fn helper(value: i32) -> i32 {{ value + 1 }}\n{rust}");
    assert_rust_snippet_runs(
        "typed-ir-function-pointer-return-direct-decay",
        &rust_with_helper,
        "assert_eq!(choose_helper()(41i32), 42i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_function_pointer_assignment_from_direct_function_decay() {
    let i32_ty = ir_i32();
    let function_ty = ir_function_type("int (int)");
    let function_pointer_ty =
        ir_pointer("int (*)(int)", "int (*)(int)", function_ty.clone(), false);
    let decay_expr = IrExpr::FunctionToPointerDecay {
        target: function_pointer_ty.clone(),
        expr: Box::new(ir_var("helper", function_ty)),
        source_span: None,
    };
    let ir = IrFunction {
        name: "call_assigned_fp".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "fp".to_string(),
                ty: function_pointer_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("fp", function_pointer_ty),
                value: decay_expr,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fp".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit function pointer assignment from direct decay");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn call_assigned_fp(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut fp: fn(i32) -> i32;"), "{rust}");
    assert!(rust.contains("fp = helper;"), "{rust}");
    assert!(rust.contains("return fp(value);"), "{rust}");
    let rust_with_helper = format!("fn helper(value: i32) -> i32 {{ value + 1 }}\n{rust}");
    assert_rust_snippet_runs(
        "typed-ir-function-pointer-assignment-direct-decay",
        &rust_with_helper,
        "assert_eq!(call_assigned_fp(41i32), 42i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_unassigned_function_pointer_local_call() {
    let i32_ty = ir_i32();
    let function_ty = ir_function_type("int (int)");
    let function_pointer_ty =
        ir_pointer("int (*)(int)", "int (*)(int)", function_ty, false);
    let ir = IrFunction {
        name: "bad_unassigned_fp".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "fp".to_string(),
                ty: function_pointer_ty,
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "fp".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("function pointer local call must be assigned first");
    assert!(error.reason.contains("var fp is read before assignment"));
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
