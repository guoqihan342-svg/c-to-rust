#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_emits_renamed_compare_and_direct_return() {
    let emitted = emit_rust_from_ir(&renamed_record_array_lookup_ir())
        .expect("emit renamed record pointer fixed array reads");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub codes: [u32; 5]"), "{rust}");
    assert!(rust.contains("pub payloads: [u32; 5]"), "{rust}");
    assert!(
        rust.contains(
            "pub fn lookup_renamed_cell(entry: &RenamedBucket, position: usize, needle: u32) -> u32"
        ),
        "{rust}"
    );
    assert!(rust.contains("entry.codes[position as usize]"), "{rust}");
    assert!(
        rust.contains("return entry.payloads[position as usize];"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-record-pointer-fixed-array-renamed",
        rust,
        r#"
    let entry = RenamedBucket {
        codes: [3, 5, 8, 13, 21],
        payloads: [30, 50, 80, 130, 210],
    };
    assert_eq!(lookup_renamed_cell(&entry, 2, 8), 80);
    assert_eq!(lookup_renamed_cell(&entry, 2, 7), 0);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_unknown_length() {
    let u32_ty = ir_u32();
    let unknown_array_ty = IrType {
        spelled: "uint32_t[]".to_string(),
        canonical: "unsigned int[]".to_string(),
        kind: IrTypeKind::Array {
            element: Box::new(u32_ty.clone()),
            len: None,
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    };
    let error = emit_rust_from_ir(&single_record_array_reader_ir(unknown_array_ty, u32_ty))
        .expect_err("unknown record array length must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("unknown length"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_element_write() {
    let mut ir = renamed_record_array_lookup_ir();
    let pointer_ty = ir.params[0].ty.clone();
    let array_ty = ir_array(ir_u32(), 5);
    ir.body.insert(
        0,
        IrStmt::Assign {
            target: direct_record_array_index(
                "entry",
                pointer_ty,
                "payloads",
                array_ty,
                ir_lit(0, "0", ir_i32()),
                ir_u32(),
            ),
            value: ir_lit(99, "99", ir_u32()),
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("record array write must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("readonly index"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_address_escape() {
    let mut ir = renamed_record_array_lookup_ir();
    let pointer_ty = ir.params[0].ty.clone();
    let array_ty = ir_array(ir_u32(), 5);
    let address_ty = ir_pointer(
        "uint32_t (*)[5]",
        "unsigned int (*)[5]",
        array_ty.clone(),
        false,
    );
    ir.body.insert(
        0,
        IrStmt::Expr {
            expr: IrExpr::AddrOf {
                operand: Box::new(direct_record_array_member(
                    "entry", pointer_ty, "codes", array_ty,
                )),
                ty: address_ty,
                source_span: None,
            },
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("record array address escape must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("escape"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_call_escape() {
    let mut ir = renamed_record_array_lookup_ir();
    let pointer_ty = ir.params[0].ty.clone();
    ir.body.insert(
        0,
        IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "observe".to_string(),
                args: vec![ir_var("entry", pointer_ty)],
                ty: ir_void(),
                source_span: None,
            },
            source_span: None,
        },
    );

    let error = emit_rust_from_ir(&ir).expect_err("record pointer call escape must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("escape"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_side_effect_index() {
    let u32_ty = ir_u32();
    let array_ty = ir_array(u32_ty.clone(), 7);
    let mut ir = single_record_array_reader_ir(array_ty.clone(), u32_ty.clone());
    let pointer_ty = ir.params[0].ty.clone();
    let usize_ty = ir.params[1].ty.clone();
    ir.body = vec![IrStmt::Return {
        value: Some(direct_record_array_index(
            "catalog",
            pointer_ty,
            "cells",
            array_ty,
            IrExpr::IncDec {
                target: Box::new(ir_var("offset", usize_ty.clone())),
                op: IrIncDecOp::Inc,
                prefix: false,
                ty: usize_ty,
                source_span: None,
            },
            u32_ty,
        )),
        source_span: None,
    }];

    let error = emit_rust_from_ir(&ir).expect_err("side-effect index must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("side-effect-free integer"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_pointer_elements() {
    let u32_pointer_ty = ir_pointer("uint32_t *", "unsigned int *", ir_u32(), false);
    let array_ty = ir_array(u32_pointer_ty.clone(), 4);
    let mut ir = single_record_array_reader_ir(array_ty, u32_pointer_ty);
    let IrStmt::Return {
        value: Some(index_read),
        ..
    } = ir.body.remove(0)
    else {
        panic!("single record array reader must return its index read");
    };
    ir.return_type = ir_i32();
    ir.body = vec![
        IrStmt::Expr {
            expr: index_read,
            source_span: None,
        },
        IrStmt::Return {
            value: Some(ir_lit(0, "0", ir_i32())),
            source_span: None,
        },
    ];
    let error = emit_rust_from_ir(&ir).expect_err("nested pointer array elements must fail closed");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("scalar element"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
fn record_array_reader_with_output_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let mut ir = single_record_array_reader_ir(ir_array(u32_ty.clone(), 6), u32_ty.clone());
    let output_ty = ir_pointer("uint32_t *", "unsigned int *", u32_ty.clone(), false);
    ir.params.push(IrParam {
        name: "output".to_string(),
        ty: output_ty.clone(),
        source_span: None,
    });
    ir.body.insert(
        0,
        IrStmt::Assign {
            target: IrExpr::Index {
                base: Box::new(ir_var("output", output_ty)),
                index: Box::new(ir_lit(0, "0", ir_i32())),
                ty: u32_ty.clone(),
                source_span: None,
            },
            value: ir_lit(1, "1", u32_ty),
            source_span: None,
        },
    );
    ir
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_rejects_writer_without_noalias() {
    let error = emit_rust_from_ir(&record_array_reader_with_output_ir())
        .expect_err("record array reader beside writer must require noalias");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("requires noalias proof"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_pointer_fixed_array_emits_writer_with_noalias() {
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "catalog".to_string(),
            mutable_param: "output".to_string(),
        }],
        ..EmitPolicy::default()
    };
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &record_array_reader_with_output_ir(),
        &[],
        policy,
    )
    .expect("record array reader beside proven noalias writer");
    let rust = &emitted.rust;

    assert!(rust.contains("catalog: &GenericCatalog"), "{rust}");
    assert!(rust.contains("mut output: &mut [u32]"), "{rust}");
    assert!(
        rust.contains("return catalog.cells[offset as usize];"),
        "{rust}"
    );
    assert_rust_snippet_compiles("typed-ir-record-array-noalias-writer", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_real_fdb_is_str_without_clang() {
    let ast = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/real_fdb_is_str_ast.json"
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
        "../../../fixtures/clang_ast/real_fdb_is_str_ast.json"
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
