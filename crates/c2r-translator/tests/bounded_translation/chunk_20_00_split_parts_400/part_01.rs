#[cfg(feature = "typed-ir")]
fn mutable_noalias_record_scalar_call_ir() -> IrFunction {
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("SharedLedger", vec![("revision", u32_ty.clone())]);
    let pointer_ty = ir_pointer(
        "struct SharedLedger *",
        "struct SharedLedger *",
        record_ty,
        false,
    );
    IrFunction {
        name: "copy_ledger_revision".to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "read_ledger".to_string(),
                ty: pointer_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "write_ledger".to_string(),
                ty: pointer_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: direct_record_scalar_member(
                    "write_ledger",
                    pointer_ty.clone(),
                    "revision",
                    u32_ty.clone(),
                    true,
                ),
                value: ir_lit(1, "1", u32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(scalar_member_call(
                    "consume_scalar",
                    direct_record_scalar_member(
                        "read_ledger",
                        pointer_ty,
                        "revision",
                        u32_ty.clone(),
                        true,
                    ),
                    u32_ty,
                )),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_scalar_call_with_noalias_read_proof() {
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "read_ledger".to_string(),
            mutable_param: "write_ledger".to_string(),
        }],
        ..EmitPolicy::default()
    };
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &mutable_noalias_record_scalar_call_ir(),
        &[],
        policy,
    )
    .expect("emit noalias-proven mutable record pointer scalar call arg");
    let rust = format!(
        "fn consume_scalar(value: u32) -> u32 {{ value + 2 }}\n{}",
        emitted.rust
    );
    assert!(rust.contains("read_ledger: &SharedLedger"), "{rust}");
    assert!(rust.contains("write_ledger: &mut SharedLedger"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-noalias-record-pointer-scalar-call-argument",
        &rust,
        "let read = SharedLedger { revision: 40u32 };\nlet mut write = SharedLedger { revision: 8u32 };\nassert_eq!(copy_ledger_revision(&read, &mut write), 42u32);\nassert_eq!(write.revision, 1u32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_explicit_integer_cast_around_record_scalar_call_argument() {
    let u8_ty = ir_u8();
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("NarrowSample", vec![("code", u8_ty.clone())]);
    let member = direct_record_scalar_member(
        "sample",
        record_ty.clone(),
        "code",
        u8_ty,
        false,
    );
    let cast = IrExpr::Cast {
        target: u32_ty.clone(),
        expr: Box::new(member),
        implicit: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "widen_sample_code".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "sample".to_string(),
            ty: record_ty,
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(scalar_member_call("consume_scalar", cast, u32_ty)),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit integer cast around record member call arg");
    let rust = format!(
        "fn consume_scalar(value: u32) -> u32 {{ value + 1 }}\n{}",
        emitted.rust
    );
    assert!(
        rust.contains("consume_scalar((sample.code as u32))"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-cast-record-scalar-call-argument",
        &rust,
        "let sample = NarrowSample { code: 41u8 };\nassert_eq!(widen_sample_code(sample), 42u32);",
    );
}
