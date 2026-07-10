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

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_scalar_call_without_readonly_noalias_proof() {
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("MutableInput", vec![("value", u32_ty.clone())]);
    let pointer_ty = ir_pointer(
        "struct MutableInput *",
        "struct MutableInput *",
        record_ty,
        false,
    );
    let ir = scalar_member_call_function(
        "read_unproven_mutable_input",
        "mutable_input",
        pointer_ty,
        "value",
        u32_ty,
        true,
    );

    let error = emit_rust_from_ir(&ir)
        .expect_err("mutable record pointer member call without readonly proof must fail");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("lacks readonly/noalias read proof")
            || error.reason.contains("pointer type") && error.reason.contains("unsupported"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_mutable_record_pointer_scalar_call_beside_write_without_noalias() {
    let error = emit_rust_from_ir(&mutable_noalias_record_scalar_call_ir())
        .expect_err("mutable input read beside record pointer write needs noalias proof");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error.reason.contains("readonly/noalias read proof")
            || error.reason.contains("requires noalias proof")
            || error.reason.contains("alias proof"),
        "{}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nullable_record_pointer_scalar_call_argument() {
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("OptionalFrame", vec![("token", u32_ty.clone())]);
    let pointer_ty = ir_pointer(
        "const struct OptionalFrame *",
        "const struct OptionalFrame *",
        ir_const(record_ty),
        false,
    );
    let member_call = scalar_member_call(
        "consume_scalar",
        direct_record_scalar_member(
            "maybe_frame",
            pointer_ty.clone(),
            "token",
            u32_ty.clone(),
            true,
        ),
        u32_ty.clone(),
    );
    let ir = IrFunction {
        name: "read_optional_frame".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "maybe_frame".to_string(),
            ty: pointer_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::If {
                condition: IrExpr::Binary {
                    op: IrBinOp::Neq,
                    lhs: Box::new(ir_var("maybe_frame", pointer_ty.clone())),
                    rhs: Box::new(ir_null_ptr(pointer_ty)),
                    ty: ir_i32(),
                    source_span: None,
                },
                then_body: vec![IrStmt::Return {
                    value: Some(member_call),
                    source_span: None,
                }],
                else_body: vec![],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("nullable record pointer scalar member call must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("nullable record pointer param"), "{}", error.reason);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_non_integer_or_unverifiable_direct_record_call_fields() {
    let u32_ty = ir_u32();
    let pointer_field_ty = ir_pointer("void *", "void *", ir_void(), false);
    let nested_ty = ir_record_with_fields("NestedValue", vec![("part", u32_ty.clone())]);
    let cases = vec![
        (
            "pointer-valued",
            ir_record_with_fields("PointerField", vec![("payload", pointer_field_ty.clone())]),
            "payload",
            pointer_field_ty,
        ),
        (
            "record-valued",
            ir_record_with_fields("RecordField", vec![("nested", nested_ty.clone())]),
            "nested",
            nested_ty,
        ),
        (
            "incomplete-record",
            ir_record("IncompleteFieldOwner"),
            "value",
            u32_ty.clone(),
        ),
        (
            "mismatched-field-type",
            ir_record_with_fields("MismatchedField", vec![("value", ir_i32())]),
            "value",
            u32_ty,
        ),
    ];

    for (case, record_ty, field, member_ty) in cases {
        let ir = scalar_member_call_function(
            &format!("reject_{case}"),
            "record_value",
            record_ty,
            field,
            member_ty,
            false,
        );
        let error = emit_rust_from_ir(&ir)
            .expect_err("non-integer or unverifiable record call field must fail closed");
        assert_eq!(error.route.route, CandidateRoute::Unsupported, "{case}");
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_nested_index_deref_and_call_record_member_bases() {
    let u32_ty = ir_u32();
    let inner_ty = ir_record_with_fields("InnerBase", vec![("value", u32_ty.clone())]);
    let outer_ty = ir_record_with_fields("OuterBase", vec![("inner", inner_ty.clone())]);
    let pointer_ty = ir_pointer(
        "const struct InnerBase *",
        "const struct InnerBase *",
        ir_const(inner_ty.clone()),
        false,
    );
    let array_ty = ir_array(inner_ty.clone(), 2);
    let bases = vec![
        (
            "nested",
            IrExpr::Member {
                base: Box::new(ir_var("root", outer_ty.clone())),
                field: "inner".to_string(),
                ty: inner_ty.clone(),
                is_arrow: false,
                source_span: None,
            },
            outer_ty,
        ),
        (
            "index",
            IrExpr::Index {
                base: Box::new(ir_var("root", array_ty.clone())),
                index: Box::new(ir_lit(0, "0", ir_i32())),
                ty: inner_ty.clone(),
                source_span: None,
            },
            array_ty,
        ),
        (
            "deref",
            IrExpr::Deref {
                ptr: Box::new(ir_var("root", pointer_ty.clone())),
                ty: inner_ty.clone(),
                source_span: None,
            },
            pointer_ty,
        ),
        (
            "call",
            IrExpr::Call {
                callee: "make_record".to_string(),
                args: vec![],
                ty: inner_ty.clone(),
                source_span: None,
            },
            inner_ty.clone(),
        ),
    ];

    for (case, base, param_ty) in bases {
        let member = IrExpr::Member {
            base: Box::new(base),
            field: "value".to_string(),
            ty: u32_ty.clone(),
            is_arrow: false,
            source_span: None,
        };
        let ir = IrFunction {
            name: format!("reject_{case}_member_base"),
            return_type: u32_ty.clone(),
            params: vec![IrParam {
                name: "root".to_string(),
                ty: param_ty,
                source_span: None,
            }],
            body: vec![IrStmt::Return {
                value: Some(scalar_member_call("consume_scalar", member, u32_ty.clone())),
                source_span: None,
            }],
            source_span: None,
        };
        let error = emit_rust_from_ir(&ir)
            .expect_err("non-direct record member call base must fail closed");
        assert_eq!(error.route.route, CandidateRoute::Unsupported, "{case}");
        assert!(
            error.reason.contains("direct DeclRef root")
                || case == "index" && error.reason.contains("array type") && error.reason.contains("unsupported"),
            "{case}: {}",
            error.reason
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_record_scalar_member_argument_with_additional_call() {
    let u32_ty = ir_u32();
    let record_ty = ir_record_with_fields("CallIsolation", vec![("value", u32_ty.clone())]);
    let ir = IrFunction {
        name: "reject_member_with_extra_call".to_string(),
        return_type: u32_ty.clone(),
        params: vec![IrParam {
            name: "record_value".to_string(),
            ty: record_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Call {
                callee: "combine".to_string(),
                args: vec![
                    direct_record_scalar_member(
                        "record_value",
                        record_ty,
                        "value",
                        u32_ty.clone(),
                        false,
                    ),
                    IrExpr::Call {
                        callee: "next_value".to_string(),
                        args: vec![],
                        ty: u32_ty.clone(),
                        source_span: None,
                    },
                ],
                ty: u32_ty,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir)
        .expect_err("record scalar member argument with another call must fail closed");
    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(error.reason.contains("additional call"), "{}", error.reason);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn direct_record_scalar_call_node_mut(ast: &mut Value) -> &mut Value {
    &mut ast["inner"][1]["inner"][1]["inner"][0]["inner"][0]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_rejects_volatile_and_atomic_record_scalar_call_fields_without_clang() {
    for (case, field_type) in [
        ("volatile", "volatile uint32_t"),
        ("atomic", "_Atomic(uint32_t)"),
    ] {
        let mut ast = direct_record_scalar_call_ast(
            "QualifiedRecord",
            "qualified_value",
            "consume_qualified",
            "forward_qualified",
            "record_value",
        );
        ast["inner"][0]["inner"][0]["type"]["qualType"] =
            Value::String(field_type.to_string());
        let member = &mut direct_record_scalar_call_node_mut(&mut ast)["inner"][1]["inner"][0]["inner"][0];
        member["type"]["qualType"] = Value::String(field_type.to_string());

        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "forward_qualified")
            .expect_err("volatile/atomic record scalar call field must fail closed");
        assert!(
            error.message.contains("fixed-width integer scalar")
                || error.message.contains("outside")
                || error.message.contains("unsupported"),
            "{case}: {}",
            error.message
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_rejects_variadic_and_mismatched_record_scalar_call_signatures_without_clang() {
    for (case, pointer_signature, function_signature, expected) in [
        (
            "variadic",
            "uint32_t (*)(uint32_t, ...)",
            "uint32_t (uint32_t, ...)",
            "variadic signature",
        ),
        (
            "mismatched",
            "uint32_t (*)(uint16_t)",
            "uint32_t (uint16_t)",
            "does not match parameter type",
        ),
        (
            "arity",
            "uint32_t (*)(uint32_t, uint32_t)",
            "uint32_t (uint32_t, uint32_t)",
            "expects 2 arguments",
        ),
    ] {
        let mut ast = direct_record_scalar_call_ast(
            "SignatureRecord",
            "scalar_value",
            "consume_signature",
            "forward_signature",
            "record_value",
        );
        let call = direct_record_scalar_call_node_mut(&mut ast);
        call["inner"][0]["type"]["qualType"] = Value::String(pointer_signature.to_string());
        call["inner"][0]["inner"][0]["type"]["qualType"] =
            Value::String(function_signature.to_string());

        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "forward_signature")
            .expect_err("variadic/mismatched member call signature must fail closed");
        assert!(error.message.contains(expected), "{case}: {}", error.message);
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_uses_desugared_fixed_width_member_call_signature_without_clang() {
    let mut ast = direct_record_scalar_call_ast(
        "AliasRecord",
        "word_value",
        "consume_alias_word",
        "forward_alias_word",
        "record_value",
    );
    let call = direct_record_scalar_call_node_mut(&mut ast);
    call["inner"][0]["type"] = serde_json::json!({
        "qualType": "word_alias_t (*)(word_alias_t)",
        "desugaredQualType": "uint32_t (*)(uint32_t)"
    });
    call["inner"][0]["inner"][0]["type"] = serde_json::json!({
        "qualType": "word_alias_t (word_alias_t)",
        "desugaredQualType": "uint32_t (uint32_t)"
    });

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "forward_alias_word")
        .expect("desugared fixed-width direct member call signature should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("desugared fixed-width direct member call signature should emit");
    assert!(
        emitted
            .rust
            .contains("return consume_alias_word(record_value.word_value);"),
        "{}",
        emitted.rust
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_rejects_indirect_record_scalar_member_call_without_clang() {
    let mut ast = direct_record_scalar_call_ast(
        "IndirectRecord",
        "word_value",
        "function_slot",
        "forward_indirect_word",
        "record_value",
    );
    let call = direct_record_scalar_call_node_mut(&mut ast);
    call["inner"][0]["castKind"] = Value::String("NoOp".to_string());
    call["inner"][0]["inner"][0]["type"]["qualType"] =
        Value::String("uint32_t (*)(uint32_t)".to_string());
    call["inner"][0]["inner"][0]["referencedDecl"]["kind"] =
        Value::String("ParmVarDecl".to_string());

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "forward_indirect_word")
        .expect_err("indirect member call must stay outside the direct-call slice");
    assert!(
        error.message.contains("must target a direct FunctionDecl"),
        "{}",
        error.message
    );
}
