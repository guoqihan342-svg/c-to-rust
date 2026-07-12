#[cfg(feature = "typed-ir")]
fn record_memset_fixture(
    function_name: &str,
    byte: u64,
    count: u64,
    valid_layout_hashes: bool,
    include_pointer_field: bool,
) -> IrFunction {
    let nested = ir_record_with_fields("wire_word", vec![("value", ir_u32())]);
    let padding = IrType {
        spelled: "unsigned char[8]".to_string(),
        canonical: "unsigned char[8]".to_string(),
        kind: IrTypeKind::Array {
            element: Box::new(ir_u8()),
            len: Some(8),
        },
        is_const: false,
        width_bits: Some(64),
        source_span: None,
    };
    let mut fields = vec![("tag", ir_u32()), ("word", nested), ("padding", padding)];
    if include_pointer_field {
        fields.push((
            "opaque",
            ir_pointer("void *", "void *", ir_void(), false),
        ));
    }
    let record = ir_record_with_fields("wire_packet", fields);
    let pointer = ir_pointer(
        "struct wire_packet *",
        "struct wire_packet *",
        record,
        false,
    );
    IrFunction {
        name: function_name.to_string(),
        return_type: ir_void(),
        params: vec![IrParam {
            name: "packet".to_string(),
            ty: pointer.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::RecordMemset {
                destination: ir_var("packet", pointer),
                byte: u8::try_from(byte).unwrap_or(u8::MAX),
                write_len_bytes: count,
                layout: IrRecordLayoutBinding {
                    record_type: "struct wire_packet".to_string(),
                    size_bytes: 16,
                    align_bytes: 8,
                    dump_sha256: if valid_layout_hashes {
                        "a".repeat(64)
                    } else {
                        "bad".to_string()
                    },
                    diagnostics_sha256: "b".repeat(64),
                    compile_arguments_sha256: "c".repeat(64),
                    compile_database_sha256: "d".repeat(64),
                    target_abi: TargetAbiProfile {
                        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
                        int_width: 32,
                        char_width: 8,
                        long_width: 64,
                        pointer_width: 64,
                        ..TargetAbiProfile::default()
                    },
                },
                source_span: None,
            },
            IrStmt::Return {
                value: None,
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_generic_record_memset_as_safe_zero_value_assignment() {
    let ir = record_memset_fixture("reset_wire_packet", 0, 16, true, false);

    let emitted = emit_rust_from_ir(&ir).expect("emit layout-bound record memset");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("pub fn reset_wire_packet(packet: &mut WirePacket)"),
        "{rust}"
    );
    assert!(rust.contains("*packet = WirePacket"), "{rust}");
    assert!(rust.contains("word: WireWord { value: 0u32 }"), "{rust}");
    assert!(rust.contains("padding: [0u8; 8]"), "{rust}");
    assert!(rust.contains("compiler-bound C object size: 16 bytes"), "{rust}");
    assert!(!rust.contains("unsafe"), "{rust}");
    assert!(!rust.contains("memset("), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-record-memset-safe-zero-assignment",
        rust,
        r#"
    let mut packet = WirePacket {
        tag: 9,
        word: WireWord { value: 77 },
        padding: [5u8; 8],
    };
    reset_wire_packet(&mut packet);
    assert_eq!(packet.tag, 0);
    assert_eq!(packet.word.value, 0);
    assert_eq!(packet.padding, [0u8; 8]);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_record_memset_boundaries_fail_closed() {
    let cases = [
        (
            record_memset_fixture("malformed_layout", 0, 16, false, false),
            "layout provenance is incomplete",
        ),
        (
            record_memset_fixture("wrong_count", 0, 15, true, false),
            "layout provenance is incomplete",
        ),
        (
            record_memset_fixture("nonzero_fill", 1, 16, true, false),
            "supports only a zero byte value",
        ),
        (
            record_memset_fixture("pointer_field", 0, 16, true, true),
            "non-zero-safe type",
        ),
    ];

    for (ir, expected) in cases {
        let error = emit_rust_from_ir(&ir).expect_err("invalid record memset must fail closed");
        assert!(
            error.reason.contains(expected),
            "{}: {}",
            ir.name,
            error.reason
        );
    }

    let mut wrong_record = record_memset_fixture("wrong_record", 0, 16, true, false);
    let IrStmt::RecordMemset { layout, .. } = &mut wrong_record.body[0] else {
        panic!("expected record memset statement");
    };
    layout.record_type = "struct unrelated".to_string();
    let error = emit_rust_from_ir(&wrong_record).expect_err("record identity drift must fail");
    assert!(error.reason.contains("layout provenance"), "{error:?}");

    let mut ordinary_call = record_memset_fixture("ordinary_call_bypass", 0, 16, true, false);
    let IrStmt::RecordMemset { destination, .. } = ordinary_call.body.remove(0) else {
        panic!("expected record memset statement");
    };
    ordinary_call.body.insert(
        0,
        IrStmt::Expr {
            expr: IrExpr::Call {
                callee: "memset".to_string(),
                args: vec![
                    destination,
                    ir_lit(0, "0", ir_i32()),
                    ir_lit(16, "16", ir_usize()),
                ],
                ty: ir_pointer("void *", "void *", ir_void(), false),
                source_span: None,
            },
            source_span: None,
        },
    );
    let error = emit_rust_from_ir(&ordinary_call)
        .expect_err("ordinary numeric memset call must not impersonate bound record memset");
    assert!(
        error.reason.contains("mutable unsigned 8-bit integer pointer"),
        "{error:?}"
    );
}
