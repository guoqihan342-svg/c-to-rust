#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_assert_int_direct_call_as_rust_assert_macro() {
    let i32_ty = ir_i32();
    let void_ty = ir_void();
    let ir = IrFunction {
        name: "assert_positive".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Expr {
                expr: IrExpr::Call {
                    callee: "assert".to_string(),
                    args: vec![ir_var("value", i32_ty.clone())],
                    ty: void_ty,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("value", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C assert(int)");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn assert_positive(value: i32) -> i32"));
    assert!(rust.contains("assert!(value != 0i32);"));
    assert!(rust.contains("return value;"));
    assert_rust_snippet_compiles("typed-ir-assert-int-model", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_abs_int_direct_call_with_checked_precondition() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "abs_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "value".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "abs".to_string(),
                args: vec![ir_var("value", i32_ty.clone())],
                ty: i32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C abs(int)");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn abs_value(value: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("return value.checked_abs().expect(\"C abs(int) precondition violated\");"),
        "{rust}"
    );
    assert!(!rust.contains("abs(value)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-abs-int-model", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_abs_calls_outside_minimal_model() {
    let i32_ty = ir_i32();
    let u32_ty = ir_u32();
    let cases = [
        (
            "abs_no_args",
            vec![],
            i32_ty.clone(),
            "requires exactly one i32 argument",
        ),
        (
            "abs_two_args",
            vec![
                ir_var("value", i32_ty.clone()),
                ir_lit(1, "1", i32_ty.clone()),
            ],
            i32_ty.clone(),
            "requires exactly one i32 argument",
        ),
        (
            "abs_unsigned_arg",
            vec![ir_var("value", u32_ty.clone())],
            i32_ty.clone(),
            "argument must be i32",
        ),
        (
            "abs_unsigned_result",
            vec![ir_var("value", i32_ty.clone())],
            u32_ty.clone(),
            "requires i32 result type",
        ),
    ];

    for (name, args, call_ty, expected_reason) in cases {
        let param_ty = if name == "abs_unsigned_arg" {
            u32_ty.clone()
        } else {
            i32_ty.clone()
        };
        let return_ty = if name == "abs_unsigned_result" {
            u32_ty.clone()
        } else {
            i32_ty.clone()
        };
        let ir = IrFunction {
            name: name.to_string(),
            return_type: return_ty,
            params: vec![IrParam {
                name: "value".to_string(),
                ty: param_ty,
                source_span: None,
            }],
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Call {
                    callee: "abs".to_string(),
                    args,
                    ty: call_ty,
                    source_span: None,
                }),
                source_span: None,
            }],
            source_span: None,
        };

        let error = emit_rust_from_ir(&ir).expect_err("unsupported abs shape must fail closed");
        assert!(
            error.reason.contains(expected_reason),
            "{name}: {:?}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_strlen_direct_call_with_nul_precondition() {
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer(
        "const uint8_t *",
        "const unsigned char *",
        ir_const(ir_u8()),
        true,
    );
    let ir = IrFunction {
        name: "name_len".to_string(),
        return_type: usize_ty.clone(),
        params: vec![IrParam {
            name: "name".to_string(),
            ty: const_u8_ptr_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "strlen".to_string(),
                args: vec![ir_var("name", const_u8_ptr_ty)],
                ty: usize_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit modeled C strlen");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn name_len(name: &[u8]) -> usize"),
        "{rust}"
    );
    assert!(
        rust.contains(
            "return name.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\");"
        ),
        "{rust}"
    );
    assert!(!rust.contains("strlen(name)"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-strlen-model", rust);
}
