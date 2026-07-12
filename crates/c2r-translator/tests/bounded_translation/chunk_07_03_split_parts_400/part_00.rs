#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_accepts_final_if_when_both_branches_return_values() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "return_from_if_else".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "flag".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::If {
            condition: ir_var("flag", i32_ty.clone()),
            then_body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "helper".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            }],
            else_body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "other".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: i32_ty.clone(),
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("final if with returning branches should satisfy return gate");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn return_from_if_else(flag: i32, value: i32) -> i32"));
    assert!(rust.contains("if flag != 0i32 {"));
    assert!(rust.contains("return helper(value);"));
    assert!(rust.contains("} else {"));
    assert!(rust.contains("return other(value);"));
    assert_rust_snippet_compiles(
        "typed-ir-final-if-both-branches-return",
        &format!(
            "fn helper(value: i32) -> i32 {{ value + 1 }}\nfn other(value: i32) -> i32 {{ value - 1 }}\n{rust}"
        ),
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_uninitialized_local_decl_assigned_before_read() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "assign_after_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: ir_var("tmp", u32_ty.clone()),
                value: ir_lit(7, "7", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit assigned uninitialized local declaration");
    let rust = &emitted.rust;

    assert!(rust.contains("let mut tmp: u32;"), "{rust}");
    assert!(rust.contains("tmp = 7u32;"), "{rust}");
    assert!(rust.contains("return tmp;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-uninitialized-local-assigned-before-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_uninitialized_local_decl_read_before_assignment() {
    let u32_ty = ir_u32();
    let ir = IrFunction {
        name: "bad_uninit_decl".to_string(),
        return_type: u32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "tmp".to_string(),
                ty: u32_ty.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("tmp", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("uninitialized local read before assignment must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("tmp"), "{:?}", error);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_rust_keyword_identifier_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "type".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("rust keyword function name must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("function identifier \"type\" is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_underscore_identifier_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "_".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(1, "1", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("underscore function name must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("function identifier \"_\" is unsupported"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_undeclared_var_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_var".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_var("x", i32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("undeclared var must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("var x is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_assign_to_undeclared_var_in_generic_emitter() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "bad_assign_target".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Assign {
                target: ir_var("x", i32_ty.clone()),
                value: ir_lit(1, "1", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(1, "1", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("undeclared assign target must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error.reason.contains("assign target x is not declared"));
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_out_of_range_integer_literal_in_generic_emitter() {
    let u8_ty = ir_u8();
    let ir = IrFunction {
        name: "bad_literal".to_string(),
        return_type: u8_ty.clone(),
        params: vec![],
        body: vec![IrStmt::Return {
            value: Some(ir_lit(256, "256", u8_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("out-of-range literal must fail closed");

    assert!(error
        .reason
        .contains("outside the current typed IR emitter subset"));
    assert!(error
        .reason
        .contains("literal value 256 does not fit type u8"));
}
