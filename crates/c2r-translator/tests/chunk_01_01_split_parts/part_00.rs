#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_fail_closed_refusal_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/scalar_runtime_preconditions_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "literal_divide_by_zero")
            .expect("lower committed clang AST scalar refusal fixture");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("literal division by zero from fixture must fail closed");

    assert!(error.reason.contains("division by zero literal"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_ub_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/scalar_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason) in [
        ("literal_modulo_by_zero", "modulo by zero literal"),
        ("shift_count_out_of_range", "shift count literal 32"),
        ("signed_right_shift_without_contract", "signed right shift"),
    ] {
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .unwrap_or_else(|error| {
                panic!("lower committed clang AST fixture {function_name}: {error}")
            });
        let error = match emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals) {
            Ok(emitted) => panic!(
                "fixture {function_name} must fail closed, emitted {}",
                emitted.rust
            ),
            Err(error) => error,
        };

        assert!(
            error.reason.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.reason
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_deref_of_local_fixed_array_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/array_decay_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "first_local_table")
        .expect("array decay through unary deref of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay through unary deref of local fixed array should emit");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_local_table() -> i32"), "{rust}");
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[0i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-array-decay-deref-local-fixed-array",
        rust,
        r#"
    assert_eq!(first_local_table(), 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_allows_array_decay_inside_subscript_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/array_decay_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table")
        .expect("array decay in array subscript base should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array subscript base decay should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_local_table(i: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[i as usize];"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-array-decay-subscript", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_pointer_add_deref_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/array_decay_pointer_add_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table_add")
            .expect("array decay through pointer-add deref of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay through pointer-add deref should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_local_table_add(i: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[i as usize];"), "{rust}");
    assert!(
        !rust.contains("return table[0i32 as usize];"),
        "pointer-add deref must not collapse to *table: {rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-array-decay-pointer-add-deref",
        rust,
        r#"
    assert_eq!(lookup_local_table_add(2), 3);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_direct_call_argument_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/array_decay_call_arg_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "observe_local_table")
            .expect("array decay direct-call argument of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay direct-call argument should emit");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn observe_local_table()"), "{rust}");
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("observe(&table);"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-array-decay-direct-call-arg",
        &format!("fn observe(_: &[i32]) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_fixed_array_decay_as_readonly_direct_call_argument() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let const_i32_ty = ir_const(i32_ty.clone());
    let array_ty = ir_array(const_i32_ty.clone(), 3);
    let pointer_ty = ir_pointer("const int *", "const int *", const_i32_ty, true);
    let ir = IrFunction {
        name: "observe_local_table".to_string(),
        return_type: void_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1", i32_ty.clone()),
                        ir_lit(2, "2", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                    ],
                    ty: array_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "observe".to_string(),
                    args: vec![IrExpr::ArrayToPointerDecay {
                        target: pointer_ty,
                        expr: Box::new(ir_var("table", array_ty)),
                        source_span: None,
                    }],
                    ty: void_ty,
                    source_span: None,
                },
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit local fixed array decay as readonly direct-call argument");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn observe_local_table()"), "{rust}");
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("observe(&table);"), "{rust}");
    assert!(!rust.contains("array-to-pointer decay"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-local-fixed-array-decay-call-arg",
        &format!("fn observe(_: &[i32]) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_global_fixed_array_decay_as_direct_call_argument() {
    let u32_ty = ir_u32();
    let void_ty = ir_void();
    let const_u32_ty = ir_const(u32_ty);
    let global = ir_u32_global_array("global_table", 3, vec![1, 2, 3]);
    let array_ty = global.ty.clone();
    let pointer_ty = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        const_u32_ty,
        true,
    );
    let ir = IrFunction {
        name: "observe_global_table".to_string(),
        return_type: void_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::ArrayToPointerDecay {
                    target: pointer_ty,
                    expr: Box::new(ir_var("global_table", array_ty)),
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };
    let emitted = emit_rust_from_ir_with_globals(&ir, &[global])
        .expect("emit readonly global fixed array decay as direct-call argument");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("const GLOBAL_TABLE: [u32; 3] = [1u32, 2u32, 3u32];"),
        "{rust}"
    );
    assert!(rust.contains("pub fn observe_global_table()"), "{rust}");
    assert!(rust.contains("observe(&GLOBAL_TABLE);"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-global-fixed-array-decay-call-arg",
        &format!("fn observe(_: &[u32]) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_byte_string_literal_decay_as_direct_call_argument() {
    let u8_ty = ir_u8();
    let i8_ty = ir_integer("char", "char", true, 8);
    let void_ty = ir_void();
    let array_ty = ir_array(u8_ty.clone(), 4);
    let pointer_ty = ir_pointer("char *", "char *", i8_ty, false);
    let ir = IrFunction {
        name: "observe_string_literal".to_string(),
        return_type: void_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::ArrayToPointerDecay {
                    target: pointer_ty,
                    expr: Box::new(IrExpr::ArrayLiteral {
                        elements: vec![
                            ir_lit(107, "107", u8_ty.clone()),
                            ir_lit(118, "118", u8_ty.clone()),
                            ir_lit(10, "10", u8_ty.clone()),
                            ir_lit(0, "0", u8_ty.clone()),
                        ],
                        ty: array_ty,
                        source_span: None,
                    }),
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit byte string literal decay call argument");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn observe_string_literal()"), "{rust}");
    assert!(
        rust.contains("observe(b\"kv\\n\\0\".as_ptr().cast::<i8>());"),
        "{rust}"
    );
    assert_rust_snippet_compiles(
        "typed-ir-byte-string-literal-decay-call-arg",
        &format!("fn observe(_: *const i8) {{}}\n{rust}"),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_unbound_global_array_decay_direct_call_argument() {
    let u32_ty = ir_u32();
    let void_ty = ir_void();
    let const_u32_ty = ir_const(u32_ty);
    let array_ty = ir_u32_global_array("global_table", 3, vec![1, 2, 3]).ty;
    let pointer_ty = ir_pointer(
        "const uint32_t *",
        "const unsigned int *",
        const_u32_ty,
        true,
    );
    let ir = IrFunction {
        name: "observe_missing_global_table".to_string(),
        return_type: void_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![IrExpr::ArrayToPointerDecay {
                    target: pointer_ty,
                    expr: Box::new(ir_var("global_table", array_ty)),
                    source_span: None,
                }],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("unbound global array decay direct-call argument must fail closed");

    assert!(
        error
            .reason
            .contains("array-to-pointer decay call argument global_table is not a local fixed array binding"),
        "unexpected error: {error:?}"
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_array_decay_direct_call_argument_target() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let array_ty = ir_array(i32_ty.clone(), 3);
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let ir = IrFunction {
        name: "observe_local_table_mut".to_string(),
        return_type: void_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1", i32_ty.clone()),
                        ir_lit(2, "2", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                    ],
                    ty: array_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "observe_mut".to_string(),
                    args: vec![IrExpr::ArrayToPointerDecay {
                        target: pointer_ty,
                        expr: Box::new(ir_var("table", array_ty)),
                        source_span: None,
                    }],
                    ty: void_ty,
                    source_span: None,
                },
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable array decay direct-call argument target must fail closed");
    assert!(
        error
            .reason
            .contains("must be a readonly integer pointer"),
        "unexpected error: {error:?}"
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_array_to_pointer_decay_without_lowering_evidence() {
    let i32_ty = ir_i32();
    let array_ty = ir_array(i32_ty.clone(), 4);
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let decay_expr: IrExpr = serde_json::from_value(serde_json::json!({
        "ArrayToPointerDecay": {
            "target": serde_json::to_value(&pointer_ty).unwrap(),
            "expr": serde_json::to_value(ir_var("table", array_ty.clone())).unwrap(),
            "source_span": null
        }
    }))
    .expect("deserialize explicit array-to-pointer decay IR node");
    let ir = IrFunction {
        name: "bad_array_decay_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1", i32_ty.clone()),
                        ir_lit(2, "2", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                        ir_lit(4, "4", i32_ty.clone()),
                    ],
                    ty: array_ty,
                    source_span: None,
                }),
                source_span: None,
            },
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

    let error = emit_rust_from_ir(&ir).expect_err("array-to-pointer decay must stay fail closed");
    assert!(error.reason.contains("array-to-pointer decay"));
    assert!(error.reason.contains("explicit lowering evidence"));
}
