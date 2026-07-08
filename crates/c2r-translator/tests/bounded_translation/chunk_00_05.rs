#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_typedef_enum_alias_reference_with_implicit_values() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "0x3201",
                "kind": "EnumDecl",
                "inner": [
                    {
                        "id": "0x3202",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_NO_ERR",
                        "type": { "qualType": "int" }
                    },
                    {
                        "id": "0x3203",
                        "kind": "EnumConstantDecl",
                        "name": "FDB_INIT_FAILED",
                        "type": { "qualType": "int" }
                    }
                ]
            },
            {
                "id": "0x3200",
                "kind": "TypedefDecl",
                "name": "fdb_err_t",
                "isReferenced": true,
                "type": { "qualType": "enum fdb_err_t" },
                "inner": [
                    {
                        "kind": "EnumType",
                        "type": { "qualType": "enum fdb_err_t" },
                        "decl": {
                            "kind": "EnumDecl",
                            "id": "0x3201"
                        }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "id_err",
                "type": {
                    "qualType": "fdb_err_t (fdb_err_t)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "e",
                        "type": {
                            "qualType": "fdb_err_t",
                            "desugaredQualType": "enum fdb_err_t",
                            "typeAliasDeclId": "0x3200"
                        }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "LValueToRValue",
                                        "type": {
                                            "qualType": "fdb_err_t",
                                            "desugaredQualType": "enum fdb_err_t",
                                            "typeAliasDeclId": "0x3200"
                                        },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": {
                                                    "qualType": "fdb_err_t",
                                                    "desugaredQualType": "enum fdb_err_t",
                                                    "typeAliasDeclId": "0x3200"
                                                },
                                                "referencedDecl": {
                                                    "kind": "ParmVarDecl",
                                                    "name": "e"
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "id_err",
        Some(&target_abi),
    )
    .expect("lower FlashDB-style typedef enum alias reference with implicit values");

    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from FlashDB-style implicit typedef enum alias fixture");
    let rust = &emitted.rust;
    assert!(rust.contains("pub fn id_err(e: i32) -> i32"), "{rust}");
    assert!(rust.contains("return e;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-clang-ast-fixture-typedef-enum-alias-implicit-values",
        rust,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_enum_local_variable_branch_and_assignment_with_target_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "choose_mode",
        Some(&target_abi),
    )
    .expect("lower explicit i32 enum local variable fixture without invoking clang");
    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        lowered.function_ir.params.as_slice(),
        [IrParam {
            name,
            ty:
                IrType {
                    kind:
                        IrTypeKind::Integer {
                            signed: true,
                            width: 32
                        },
                    ..
                },
            ..
        }] if name == "value"
    ));
    let [IrStmt::Decl {
        name: decl_name,
        ty: decl_ty,
        init: Some(IrExpr::LitInt { value: 1, .. }),
        ..
    }, IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    }, IrStmt::Return {
        value: Some(IrExpr::Var {
            name: return_name, ..
        }),
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected enum local declaration, branch assignment, and return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(decl_name, "current");
    assert!(matches!(
        decl_ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    ));
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Eq,
            lhs,
            rhs,
            ..
        } if matches!(lhs.as_ref(), IrExpr::Var { name, .. } if name == "value")
            && matches!(rhs.as_ref(), IrExpr::LitInt { value: 2, .. })
    ));
    assert!(else_body.is_empty());
    assert!(matches!(
        then_body.as_slice(),
        [IrStmt::Assign {
            target: IrExpr::Var { name: target_name, .. },
            value: IrExpr::LitInt { value: 2, .. },
            ..
        }] if target_name == "current"
    ));
    assert_eq!(return_name, "current");

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from explicit i32 enum local variable fixture");
    let rust = &emitted.rust;
    assert!(
        rust.contains("pub fn choose_mode(value: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("let mut current: i32 = 1i32;"), "{rust}");
    assert!(rust.contains("if (value == 2i32)"), "{rust}");
    assert!(rust.contains("current = 2i32;"), "{rust}");
    assert!(rust.contains("return current;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-fixture-enum-local-variable", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_sizeof_enum_without_layout_abi() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/enum_constant_ast.json"))
            .expect("fixture JSON");
    let target_abi = TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        char_width: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        long_width: 64,
        long_long_width: 64,
        pointer_width: 64,
        ..TargetAbiProfile::default()
    };

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "sizeof_mode_bytes",
        Some(&target_abi),
    )
    .expect_err("sizeof(enum) still needs explicit enum layout/ABI proof");
    assert_eq!(error.kind, "unsupported_sizeof_type");
    assert!(
        error.message.contains("sizeof(enum mode)"),
        "{}",
        error.message
    );
    assert!(
        error
            .message
            .contains("requires explicit C layout/ABI provenance"),
        "{}",
        error.message
    );
}
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
