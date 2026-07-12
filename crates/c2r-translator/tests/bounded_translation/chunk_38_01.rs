#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_rejects_unverified_mutable_void_pointer_scalar_address_calls() {
    for (case, mutate, expected) in [
        (
            "const-parameter",
            0u8,
            "requires a mutable void * parameter",
        ),
        ("variadic", 1u8, "variadic signature"),
        ("indirect", 2u8, "not a direct function identifier"),
    ] {
        let mut ast = mutable_void_pointer_scalar_address_ast(
            "ValidationEnvelope",
            "ValidationCell",
            "cell",
            "word",
            "output",
            "write_word",
            "validate_write",
        );
        let call = mutable_void_pointer_call_node_mut(&mut ast);
        match mutate {
            0 => {
                call["inner"][0]["type"]["qualType"] =
                    Value::String("int (*)(int, const void *)".to_string());
                call["inner"][0]["inner"][0]["type"]["qualType"] =
                    Value::String("int (int, const void *)".to_string());
            }
            1 => {
                call["inner"][0]["type"]["qualType"] =
                    Value::String("int (*)(int, void *, ...)".to_string());
                call["inner"][0]["inner"][0]["type"]["qualType"] =
                    Value::String("int (int, void *, ...)".to_string());
            }
            2 => {
                call["inner"][0]["inner"][0]["referencedDecl"]["kind"] =
                    Value::String("VarDecl".to_string());
            }
            _ => unreachable!(),
        }
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, "validate_write")
            .expect_err("unverified mutable void pointer scalar address must fail closed");
        assert!(error.message.contains(expected), "{case}: {}", error.message);
    }
}

#[cfg(feature = "typed-ir")]
fn mutable_void_pointer_address_function(
    root_pointer: IrType,
    arg: IrExpr,
    sibling: Option<IrExpr>,
) -> IrFunction {
    let mut args = vec![arg];
    let mut body = Vec::new();
    if let Some(sibling) = sibling {
        body.push(IrStmt::Assign {
            target: sibling.clone(),
            value: ir_lit(0, "0", ir_u32()),
            source_span: None,
        });
        args.push(sibling);
    }
    body.push(IrStmt::Return {
        value: Some(IrExpr::Call {
            callee: "write_output_word".to_string(),
            args,
            ty: ir_i32(),
            source_span: None,
        }),
        source_span: None,
    });
    IrFunction {
        name: "route_output_word".to_string(),
        return_type: ir_i32(),
        params: vec![IrParam {
            name: "output".to_string(),
            ty: root_pointer,
            source_span: None,
        }],
        body,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_accepts_equivalent_fixed_width_integer_typedef_for_mutable_void_address() {
    let typedef_u32 = IrType {
        spelled: "project_word_t".to_string(),
        canonical: "project_word_t".to_string(),
        kind: IrTypeKind::Integer {
            signed: false,
            width: 32,
        },
        is_const: false,
        width_bits: Some(32),
        source_span: None,
    };
    let field_u32 = ir_u32();
    let nested_ty = ir_record_with_fields("PayloadCell", vec![("word", field_u32.clone())]);
    let root_ty = ir_record_with_fields("PayloadEnvelope", vec![("cell", nested_ty.clone())]);
    let root_pointer = ir_pointer(
        "struct PayloadEnvelope *",
        "struct PayloadEnvelope *",
        root_ty,
        false,
    );
    let source_pointer = ir_pointer(
        "project_word_t *",
        "project_word_t *",
        typedef_u32,
        false,
    );
    let mutable_void_pointer = ir_pointer("void *", "void *", ir_void(), false);
    let arg = mutable_void_pointer_address_ir(
        "output",
        root_pointer.clone(),
        "cell",
        nested_ty,
        "word",
        field_u32,
        source_pointer,
        mutable_void_pointer,
    );

    let emitted = emit_rust_from_ir(&mutable_void_pointer_address_function(
        root_pointer,
        arg,
        None,
    ))
    .expect("equivalent fixed-width integer typedef must preserve the safe adapter candidate");
    let rust = format!(
        "fn write_output_word(output: &mut u32) -> i32 {{ *output = 0x5060_7080; 7 }}\n{}",
        emitted.rust
    );
    assert!(
        rust.contains("write_output_word(&mut output.cell.word)"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-mutable-void-address-equivalent-integer-typedef",
        &rust,
        r#"
    let mut output = PayloadEnvelope { cell: PayloadCell { word: 0 } };
    assert_eq!(route_output_word(&mut output), 7);
    assert_eq!(output.cell.word, 0x5060_7080);
"#,
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_forged_or_aliasing_mutable_void_pointer_scalar_addresses() {
    let u32_ty = ir_u32();
    let nested_ty = ir_record_with_fields("OutputCell", vec![("word", u32_ty.clone())]);
    let complete_root = ir_record_with_fields("OutputEnvelope", vec![("cell", nested_ty.clone())]);
    let complete_pointer = ir_pointer(
        "struct OutputEnvelope *",
        "struct OutputEnvelope *",
        complete_root,
        false,
    );
    let mutable_u32_pointer = ir_pointer("uint32_t *", "uint32_t *", u32_ty.clone(), false);
    let mutable_void_pointer = ir_pointer("void *", "void *", ir_void(), false);

    let base_arg = mutable_void_pointer_address_ir(
        "output",
        complete_pointer.clone(),
        "cell",
        nested_ty.clone(),
        "word",
        u32_ty.clone(),
        mutable_u32_pointer.clone(),
        mutable_void_pointer.clone(),
    );
    let sibling_read = IrExpr::Member {
        base: Box::new(IrExpr::Member {
            base: Box::new(ir_var("output", complete_pointer.clone())),
            field: "cell".to_string(),
            ty: nested_ty.clone(),
            is_arrow: true,
            source_span: None,
        }),
        field: "word".to_string(),
        ty: u32_ty.clone(),
        is_arrow: false,
        source_span: None,
    };
    let u16_ty = IrType {
        spelled: "uint16_t".to_string(),
        canonical: "unsigned short".to_string(),
        kind: IrTypeKind::Integer {
            signed: false,
            width: 16,
        },
        is_const: false,
        width_bits: Some(16),
        source_span: None,
    };
    let mismatched_source = ir_pointer("uint16_t *", "uint16_t *", u16_ty, false);
    let signed_source = ir_pointer("int32_t *", "int *", ir_i32(), false);
    let const_void_pointer = ir_pointer("const void *", "const void *", ir_const(ir_void()), false);
    let incomplete_root = ir_record("IncompleteOutputEnvelope");
    let incomplete_pointer = ir_pointer(
        "struct IncompleteOutputEnvelope *",
        "struct IncompleteOutputEnvelope *",
        incomplete_root,
        false,
    );

    let cases = vec![
        (
            "source-type-mismatch",
            complete_pointer.clone(),
            mutable_void_pointer_address_ir(
                "output",
                complete_pointer.clone(),
                "cell",
                nested_ty.clone(),
                "word",
                u32_ty.clone(),
                mismatched_source,
                mutable_void_pointer.clone(),
            ),
            None,
            "does not match field type",
        ),
        (
            "source-signedness-mismatch",
            complete_pointer.clone(),
            mutable_void_pointer_address_ir(
                "output",
                complete_pointer.clone(),
                "cell",
                nested_ty.clone(),
                "word",
                u32_ty.clone(),
                signed_source,
                mutable_void_pointer.clone(),
            ),
            None,
            "does not match field type",
        ),
        (
            "const-target",
            complete_pointer.clone(),
            mutable_void_pointer_address_ir(
                "output",
                complete_pointer.clone(),
                "cell",
                nested_ty.clone(),
                "word",
                u32_ty.clone(),
                mutable_u32_pointer.clone(),
                const_void_pointer,
            ),
            None,
            "is not mutable void *",
        ),
        (
            "incomplete-root",
            incomplete_pointer.clone(),
            mutable_void_pointer_address_ir(
                "output",
                incomplete_pointer,
                "cell",
                nested_ty,
                "word",
                u32_ty,
                mutable_u32_pointer,
                mutable_void_pointer,
            ),
            None,
            "complete field inventory",
        ),
        (
            "sibling-read",
            complete_pointer,
            base_arg,
            Some(sibling_read),
            "sibling argument that reads the same record",
        ),
    ];

    for (case, root_pointer, arg, sibling, expected) in cases {
        let error = emit_rust_from_ir(&mutable_void_pointer_address_function(
            root_pointer,
            arg,
            sibling,
        ))
        .expect_err("forged or aliasing mutable void pointer address must fail closed");
        assert_eq!(error.route.route, CandidateRoute::Unsupported, "{case}");
        assert!(error.reason.contains(expected), "{case}: {}", error.reason);
    }
}
