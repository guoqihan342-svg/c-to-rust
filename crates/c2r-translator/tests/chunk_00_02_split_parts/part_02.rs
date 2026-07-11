
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_translation_unit_replays_renamed_record_fixed_array_reads_without_clang() {
    fn unsigned_param_read(name: &str) -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned int" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": name
                    }
                }
            ]
        })
    }

    fn record_array_element_read(field: &str) -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "ArraySubscriptExpr",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "ArrayToPointerDecay",
                            "type": { "qualType": "unsigned int *" },
                            "inner": [
                                {
                                    "kind": "MemberExpr",
                                    "name": field,
                                    "isArrow": true,
                                    "type": { "qualType": "unsigned int[4]" },
                                    "inner": [
                                        {
                                            "kind": "ImplicitCastExpr",
                                            "castKind": "LValueToRValue",
                                            "type": {
                                                "qualType": "const struct renamed_ledger *"
                                            },
                                            "inner": [
                                                {
                                                    "kind": "DeclRefExpr",
                                                    "type": {
                                                        "qualType": "const struct renamed_ledger *"
                                                    },
                                                    "referencedDecl": {
                                                        "kind": "ParmVarDecl",
                                                        "name": "entry"
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        },
                        unsigned_param_read("position")
                    ]
                }
            ]
        })
    }

    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "name": "renamed_ledger",
                "completeDefinition": true,
                "inner": [
                    {
                        "kind": "FieldDecl",
                        "name": "tokens",
                        "type": { "qualType": "unsigned int[4]" }
                    },
                    {
                        "kind": "FieldDecl",
                        "name": "results",
                        "type": { "qualType": "unsigned int[4]" }
                    }
                ]
            },
            {
                "kind": "FunctionDecl",
                "name": "lookup_renamed_slot",
                "type": {
                    "qualType": "unsigned int (const struct renamed_ledger *, unsigned int, unsigned int)"
                },
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "entry",
                        "type": { "qualType": "const struct renamed_ledger *" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "position",
                        "type": { "qualType": "unsigned int" }
                    },
                    {
                        "kind": "ParmVarDecl",
                        "name": "needle",
                        "type": { "qualType": "unsigned int" }
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [
                            {
                                "kind": "IfStmt",
                                "inner": [
                                    {
                                        "kind": "BinaryOperator",
                                        "opcode": "==",
                                        "type": { "qualType": "int" },
                                        "inner": [
                                            record_array_element_read("tokens"),
                                            unsigned_param_read("needle")
                                        ]
                                    },
                                    {
                                        "kind": "ReturnStmt",
                                        "inner": [
                                            record_array_element_read("results")
                                        ]
                                    }
                                ]
                            },
                            {
                                "kind": "ReturnStmt",
                                "inner": [
                                    {
                                        "kind": "IntegerLiteral",
                                        "type": { "qualType": "unsigned int" },
                                        "value": "0"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    });

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "lookup_renamed_slot",
    )
    .expect("lower renamed record fixed array reads without invoking clang");

    let IrTypeKind::Pointer { pointee } = &lowered.function_ir.params[0].ty.kind else {
        panic!("entry should lower as a record pointer");
    };
    let IrTypeKind::Record {
        name,
        fields: Some(fields),
    } = &pointee.kind
    else {
        panic!("entry record pointer should receive complete inventory");
    };
    assert_eq!(name, "renamed_ledger");
    assert!(matches!(
        fields.as_slice(),
        [
            IrRecordField {
                name: tokens,
                ty: IrType {
                    kind: IrTypeKind::Array { len: Some(4), .. },
                    ..
                }
            },
            IrRecordField {
                name: results,
                ty: IrType {
                    kind: IrTypeKind::Array { len: Some(4), .. },
                    ..
                }
            }
        ] if tokens == "tokens" && results == "results"
    ));

    let [
        IrStmt::If {
            condition: IrExpr::Binary { lhs, .. },
            then_body,
            ..
        },
        IrStmt::Return { .. },
    ] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected fixed-array comparison and fallback return, got {:?}",
            lowered.function_ir.body
        );
    };
    let IrExpr::LValueToRValue { expr: token_read, .. } = lhs.as_ref() else {
        panic!("tokens comparison should preserve its integer read, got {lhs:?}");
    };
    assert!(matches!(
        token_read.as_ref(),
        IrExpr::Index { base, .. }
            if matches!(
                base.as_ref(),
                IrExpr::Member {
                    field,
                    is_arrow: true,
                    ty: IrType {
                        kind: IrTypeKind::Array { len: Some(4), .. },
                        ..
                    },
                    ..
                } if field == "tokens"
            )
    ));
    let [IrStmt::Return {
        value: Some(IrExpr::LValueToRValue { expr: result_read, .. }),
        ..
    }] = then_body.as_slice()
    else {
        panic!("matching branch should directly return the results array read");
    };
    assert!(matches!(
        result_read.as_ref(),
        IrExpr::Index { base, .. }
            if matches!(
                base.as_ref(),
                IrExpr::Member {
                    field,
                    is_arrow: true,
                    ty: IrType {
                        kind: IrTypeKind::Array { len: Some(4), .. },
                        ..
                    },
                    ..
                } if field == "results"
            )
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed record fixed array reads");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct RenamedLedger"), "{rust}");
    assert!(rust.contains("pub tokens: [u32; 4]"), "{rust}");
    assert!(rust.contains("pub results: [u32; 4]"), "{rust}");
    assert!(
        rust.contains(
            "pub fn lookup_renamed_slot(entry: &RenamedLedger, position: u32, needle: u32) -> u32"
        ),
        "{rust}"
    );
    assert!(
        rust.contains("entry.tokens[position as usize] == needle"),
        "{rust}"
    );
    assert!(
        rust.contains("return entry.results[position as usize];"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-record-fixed-array-renamed",
        rust,
        r#"
    let entry = RenamedLedger {
        tokens: [11, 22, 33, 44],
        results: [101, 202, 303, 404],
    };
    assert_eq!(lookup_renamed_slot(&entry, 2, 33), 303);
    assert_eq!(lookup_renamed_slot(&entry, 2, 34), 0);
"#,
    );
}
