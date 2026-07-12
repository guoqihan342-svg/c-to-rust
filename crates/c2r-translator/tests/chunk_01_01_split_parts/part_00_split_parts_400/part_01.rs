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
