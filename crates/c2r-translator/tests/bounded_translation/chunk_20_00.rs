#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn direct_record_scalar_call_ast(
    record: &str,
    field: &str,
    callee: &str,
    function: &str,
    parameter: &str,
) -> Value {
    let record_type = format!("struct {record}");
    let member = serde_json::json!({
        "kind": "MemberExpr",
        "name": field,
        "isArrow": false,
        "type": { "qualType": "uint32_t" },
        "inner": [
            {
                "kind": "DeclRefExpr",
                "type": { "qualType": record_type },
                "referencedDecl": {
                    "kind": "ParmVarDecl",
                    "name": parameter
                }
            }
        ]
    });
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": record,
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": field,
                        "type": { "qualType": "uint32_t" }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": function,
                "type": { "qualType": format!("uint32_t ({record_type})") },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": parameter,
                        "type": { "qualType": record_type }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "CallExpr",
                                        "type": { "qualType": "uint32_t" },
                                        "inner": [
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "FunctionToPointerDecay",
                                                "type": { "qualType": "uint32_t (*)(uint32_t)" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "uint32_t (uint32_t)" },
                                                        "referencedDecl": {
                                                            "kind": "FunctionDecl",
                                                            "name": callee
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "LValueToRValue",
                                                "type": { "qualType": "uint32_t" },
                                                "inner": [
                                                    {
                                                        "kind": "ParenExpr",
                                                        "type": { "qualType": "uint32_t" },
                                                        "inner": [member]
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
            }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_emits_fully_renamed_by_value_record_scalar_direct_call_argument_without_clang() {
    let ast = direct_record_scalar_call_ast(
        "TelemetryEnvelope",
        "sequence_code",
        "fold_sequence",
        "forward_envelope_sequence",
        "envelope_value",
    );
    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "forward_envelope_sequence",
    )
    .expect("lower fully renamed record scalar call argument without invoking clang");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit fully renamed record scalar call argument");
    let rust = format!(
        "fn fold_sequence(value: u32) -> u32 {{ value ^ 0x5a5a_1234 }}\n{}",
        emitted.rust
    );

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains("return fold_sequence(envelope_value.sequence_code);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-fully-renamed-record-scalar-call-argument",
        &rust,
        "let value = TelemetryEnvelope { sequence_code: 0x1020_3040 };\nassert_eq!(forward_envelope_sequence(value), 0x4a7a_2274);",
    );
}

#[cfg(feature = "typed-ir")]
fn direct_record_scalar_member(
    root: &str,
    root_ty: IrType,
    field: &str,
    field_ty: IrType,
    is_arrow: bool,
) -> IrExpr {
    IrExpr::Member {
        base: Box::new(ir_var(root, root_ty)),
        field: field.to_string(),
        ty: field_ty,
        is_arrow,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn scalar_member_call(callee: &str, arg: IrExpr, return_ty: IrType) -> IrExpr {
    IrExpr::Call {
        callee: callee.to_string(),
        args: vec![arg],
        ty: return_ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn scalar_member_call_function(
    name: &str,
    root: &str,
    root_ty: IrType,
    field: &str,
    field_ty: IrType,
    is_arrow: bool,
) -> IrFunction {
    let return_ty = ir_u32();
    IrFunction {
        name: name.to_string(),
        return_type: return_ty.clone(),
        params: vec![IrParam {
            name: root.to_string(),
            ty: root_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(scalar_member_call(
                "consume_scalar",
                direct_record_scalar_member(root, root_ty, field, field_ty, is_arrow),
                return_ty,
            )),
            source_span: None,
        }],
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_local_record_scalar_direct_call_argument() {
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("LocalPacket", vec![("status_word", u32_ty.clone())]);
    let ir = IrFunction {
        name: "forward_local_status".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "seed_packet".to_string(),
            ty: record_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "local_packet".to_string(),
                ty: record_ty.clone(),
                init: Some(ir_var("seed_packet", record_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(scalar_member_call(
                    "consume_scalar",
                    direct_record_scalar_member(
                        "local_packet",
                        record_ty,
                        "status_word",
                        u32_ty.clone(),
                        false,
                    ),
                    u32_ty,
                )),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit local record scalar call argument");
    let rust = format!(
        "fn consume_scalar(value: u32) -> u32 {{ value + 17 }}\n{}",
        emitted.rust
    );
    assert!(
        rust.contains("return consume_scalar(local_packet.status_word);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-local-record-scalar-call-argument",
        &rust,
        "let seed = LocalPacket { status_word: 25u32 };\nassert_eq!(forward_local_status(seed), 42u32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_readonly_record_pointer_scalar_direct_call_argument() {
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("ReadonlyFrame", vec![("epoch", u32_ty.clone())]);
    let pointer_ty = ir_pointer(
        "const struct ReadonlyFrame *",
        "const struct ReadonlyFrame *",
        ir_const(record_ty),
        false,
    );
    let ir = scalar_member_call_function(
        "forward_readonly_epoch",
        "frame_ref",
        pointer_ty,
        "epoch",
        u32_ty,
        true,
    );

    let emitted = emit_rust_from_ir(&ir).expect("emit readonly record pointer scalar call arg");
    let rust = format!(
        "fn consume_scalar(value: u32) -> u32 {{ value.rotate_left(3) }}\n{}",
        emitted.rust
    );
    assert!(rust.contains("frame_ref: &ReadonlyFrame"), "{rust}");
    assert!(
        rust.contains("return consume_scalar(frame_ref.epoch);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-readonly-record-pointer-scalar-call-argument",
        &rust,
        "let frame = ReadonlyFrame { epoch: 9u32 };\nassert_eq!(forward_readonly_epoch(&frame), 72u32);",
    );
}

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
