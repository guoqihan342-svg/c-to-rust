#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn mutable_void_pointer_scalar_address_ast(
    outer: &str,
    inner: &str,
    nested_field: &str,
    scalar_field: &str,
    root: &str,
    callee: &str,
    function: &str,
) -> Value {
    let outer_ty = format!("struct {outer}");
    let inner_ty = format!("struct {inner}");
    let root_pointer_ty = format!("{outer_ty} *");
    let scalar_member = serde_json::json!({
        "kind": "MemberExpr",
        "name": scalar_field,
        "isArrow": false,
        "type": { "qualType": "uint32_t" },
        "inner": [{
            "kind": "MemberExpr",
            "name": nested_field,
            "isArrow": true,
            "type": { "qualType": inner_ty },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": root_pointer_ty },
                "referencedDecl": { "kind": "ParmVarDecl", "name": root }
            }]
        }]
    });
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": inner,
                "completeDefinition": true,
                "inner": [{
                    "kind": "FieldDecl",
                    "name": scalar_field,
                    "type": { "qualType": "uint32_t" }
                }]
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": outer,
                "completeDefinition": true,
                "inner": [{
                    "kind": "FieldDecl",
                    "name": nested_field,
                    "type": { "qualType": inner_ty }
                }]
            },
            {
                "kind": "FunctionDecl",
                "name": function,
                "type": { "qualType": format!("int ({root_pointer_ty})") },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": root,
                        "type": { "qualType": root_pointer_ty }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [{
                            "kind": "ReturnStmt",
                            "inner": [{
                                "kind": "CallExpr",
                                "type": { "qualType": "int" },
                                "inner": [
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "FunctionToPointerDecay",
                                        "type": { "qualType": "int (*)(int, void *)" },
                                        "inner": [{
                                            "kind": "DeclRefExpr",
                                            "type": { "qualType": "int (int, void *)" },
                                            "referencedDecl": {
                                                "kind": "FunctionDecl",
                                                "name": callee
                                            }
                                        }]
                                    },
                                    {
                                        "kind": "IntegerLiteral",
                                        "value": "9",
                                        "type": { "qualType": "int" }
                                    },
                                    {
                                        "kind": "ImplicitCastExpr",
                                        "castKind": "BitCast",
                                        "type": { "qualType": "void *" },
                                        "inner": [{
                                            "kind": "UnaryOperator",
                                            "opcode": "&",
                                            "type": { "qualType": "uint32_t *" },
                                            "inner": [scalar_member]
                                        }]
                                    }
                                ]
                            }]
                        }]
                    }
                ]
            }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn mutable_void_pointer_call_node_mut(ast: &mut Value) -> &mut Value {
    &mut ast["inner"][2]["inner"][1]["inner"][0]["inner"][0]
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_preserves_renamed_mutable_void_pointer_scalar_address_provenance() {
    for (outer, inner, nested, scalar, root, callee, function) in [
        (
            "DispatchEnvelope",
            "DispatchCell",
            "payload_cell",
            "sequence_word",
            "output_envelope",
            "store_sequence",
            "prepare_dispatch",
        ),
        (
            "CaptureFrame",
            "CaptureSlot",
            "result_slot",
            "checksum_value",
            "frame_target",
            "write_checksum",
            "prepare_capture",
        ),
    ] {
        let ast = mutable_void_pointer_scalar_address_ast(
            outer, inner, nested, scalar, root, callee, function,
        );
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function)
            .expect("lower renamed mutable void pointer scalar address");
        let IrStmt::Return {
            value: Some(IrExpr::Call { args, .. }),
            ..
        } = &lowered.function_ir.body[0]
        else {
            panic!("expected direct return call");
        };
        assert!(matches!(
            &args[1],
            IrExpr::MutableVoidPointerAddress { target, .. }
                if matches!(
                    &target.kind,
                    IrTypeKind::Pointer { pointee }
                        if !pointee.is_const && matches!(pointee.kind, IrTypeKind::Void)
                )
        ));

        let emitted =
            emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
                .expect("emit mutable void pointer scalar address");
        let rust = format!(
            "fn {callee}(code: i32, output: &mut u32) -> i32 {{ *output = 0x1020_3040; code + 3 }}\n{}",
            emitted.rust
        );
        assert!(
            rust.contains(&format!(
                "return {callee}(9i32, &mut {root}.{nested}.{scalar});"
            )),
            "{rust}"
        );
        assert_rust_snippet_runs(
            &format!("typed-ir-mutable-void-address-{function}"),
            &rust,
            &format!(
                "let mut value = {outer} {{ {nested}: {inner} {{ {scalar}: 0 }} }};\nassert_eq!({function}(&mut value), 12);\nassert_eq!(value.{nested}.{scalar}, 0x1020_3040);"
            ),
        );
    }
}

#[cfg(feature = "typed-ir")]
fn mutable_void_pointer_address_ir(
    root: &str,
    root_pointer: IrType,
    nested_field: &str,
    nested_ty: IrType,
    scalar_field: &str,
    scalar_ty: IrType,
    source_pointer: IrType,
    target: IrType,
) -> IrExpr {
    IrExpr::MutableVoidPointerAddress {
        operand: Box::new(IrExpr::Member {
            base: Box::new(IrExpr::Member {
                base: Box::new(ir_var(root, root_pointer)),
                field: nested_field.to_string(),
                ty: nested_ty,
                is_arrow: true,
                source_span: None,
            }),
            field: scalar_field.to_string(),
            ty: scalar_ty,
            is_arrow: false,
            source_span: None,
        }),
        source_pointer,
        target,
        source_span: None,
    }
}
