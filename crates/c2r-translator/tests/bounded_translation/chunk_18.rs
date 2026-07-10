#[cfg(feature = "typed-ir")]
fn mutable_byte_pointer_index_reader_ir() -> IrFunction {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let pointer_ty = ir_pointer("uint8_t *", "unsigned char *", u8_ty.clone(), false);
    IrFunction {
        name: "read_mutable_byte_at".to_string(),
        return_type: u8_ty.clone(),
        params: vec![
            IrParam {
                name: "value".to_string(),
                ty: pointer_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "index".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Index {
                base: Box::new(ir_var("value", pointer_ty)),
                index: Box::new(ir_var("index", usize_ty)),
                ty: u8_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_body_proven_readonly_mutable_pointer_index_as_shared_slice() {
    let emitted = emit_rust_from_ir(&mutable_byte_pointer_index_reader_ir())
        .expect("emit body-proven readonly mutable pointer index");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn read_mutable_byte_at(value: &[u8], index: usize) -> u8"),
        "{rust}"
    );
    assert!(rust.contains("return value[index as usize];"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-readonly-mutable-pointer-index", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_pointer_with_index_read_and_call_escape() {
    let mut ir = mutable_byte_pointer_index_reader_ir();
    let pointer_ty = ir.params[0].ty.clone();
    let void_ty = ir_void();
    ir.body.insert(
        0,
        IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "consume".to_string(),
                args: vec![ir_var("value", pointer_ty)],
                ty: void_ty,
                source_span: None,
            },
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("escaped pointer must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("pointer type"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_readonly_mutable_pointer_beside_write_without_noalias() {
    let mut ir = mutable_byte_pointer_index_reader_ir();
    let u8_ty = ir_u8();
    let out_ty = ir_pointer("uint8_t *", "unsigned char *", u8_ty.clone(), false);
    ir.params.push(IrParam {
        name: "out".to_string(),
        ty: out_ty.clone(),
        source_span: None,
    });
    ir.body.insert(
        0,
        IrStmt::Assign {
            target: IrExpr::Index {
                base: Box::new(ir_var("out", out_ty)),
                index: Box::new(ir_lit(0, "0", ir_i32())),
                ty: u8_ty.clone(),
                source_span: None,
            },
            value: ir_lit(1, "1", u8_ty),
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("missing noalias must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("requires noalias proof"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_mutable_pointer_beside_write_with_noalias() {
    let mut ir = mutable_byte_pointer_index_reader_ir();
    let u8_ty = ir_u8();
    let out_ty = ir_pointer("uint8_t *", "unsigned char *", u8_ty.clone(), false);
    ir.params.push(IrParam {
        name: "out".to_string(),
        ty: out_ty.clone(),
        source_span: None,
    });
    ir.body.insert(
        0,
        IrStmt::Assign {
            target: IrExpr::Index {
                base: Box::new(ir_var("out", out_ty)),
                index: Box::new(ir_lit(0, "0", ir_i32())),
                ty: u8_ty.clone(),
                source_span: None,
            },
            value: ir_lit(1, "1", u8_ty),
            source_span: None,
        },
    );
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "value".to_string(),
            mutable_param: "out".to_string(),
        }],
        ..EmitPolicy::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("explicit noalias permits shared input beside mutable output");
    let rust = &emitted.rust;
    assert!(rust.contains("value: &[u8]"), "{rust}");
    assert!(rust.contains("mut out: &mut [u8]"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-readonly-mutable-pointer-noalias", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_real_fdb_is_str_without_clang() {
    let ast = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/real_fdb_is_str_ast.json"
    ))
    .expect("real fdb_is_str fixture JSON");
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
        "fdb_is_str",
        Some(&target_abi),
    )
    .expect("lower real FlashDB fdb_is_str fixture without invoking clang");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit Rust from real FlashDB fdb_is_str fixture");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(lowered.globals.is_empty());
    assert!(
        rust.contains("pub fn fdb_is_str(value: &[u8], len: usize) -> bool"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-real-fdb-is-str",
        rust,
        r#"
    for (value, len, expected) in [
        (&b""[..], 0usize, true),
        (&b" all printable ~"[..], 16usize, true),
        (&[0x20u8, 0x7eu8][..], 2usize, true),
        (&[0x1fu8, 0x20u8][..], 2usize, false),
        (&[0x20u8, 0x7fu8][..], 2usize, false),
        (&[0x20u8, 0xffu8][..], 2usize, false),
        (&[0x20u8, 0x00u8, 0x7eu8][..], 3usize, false),
        (&[0x20u8, 0x00u8][..], 1usize, true),
    ] {
        assert_eq!(fdb_is_str(value, len), expected);
    }
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_real_fdb_is_str_without_target_abi() {
    let ast = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/real_fdb_is_str_ast.json"
    ))
    .expect("real fdb_is_str fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "fdb_is_str",
        None,
    )
    .expect_err("size_t fixture must require target ABI");
    assert!(
        error.message.contains("size_t") || error.message.contains("target ABI"),
        "{}",
        error.message
    );
}
