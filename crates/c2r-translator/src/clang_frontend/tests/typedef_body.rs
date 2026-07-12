#[test]
fn function_body_uses_translation_unit_typedef_without_node_desugaring() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "TypedefDecl",
                "name": "renamed_word_t",
                "type": {"qualType": "unsigned short"}
            },
            {
                "kind": "FunctionDecl",
                "name": "echo_word",
                "type": {"qualType": "renamed_word_t (renamed_word_t)"},
                "inner": [
                    {
                        "kind": "ParmVarDecl",
                        "name": "value",
                        "type": {"qualType": "renamed_word_t"}
                    },
                    {
                        "kind": "CompoundStmt",
                        "inner": [{
                            "kind": "ReturnStmt",
                            "inner": [{
                                "kind": "ImplicitCastExpr",
                                "castKind": "LValueToRValue",
                                "type": {"qualType": "renamed_word_t"},
                                "inner": [{
                                    "kind": "DeclRefExpr",
                                    "type": {"qualType": "renamed_word_t"},
                                    "referencedDecl": {
                                        "kind": "ParmVarDecl",
                                        "name": "value"
                                    }
                                }]
                            }]
                        }]
                    }
                ]
            }
        ]
    });
    let abi = typedef_test_abi();

    let lowered = lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
        &ast,
        "echo_word",
        Some(&abi),
    )
    .expect("body alias should resolve through translation-unit typedef inventory");

    assert!(matches!(
        lowered.function_ir.return_type.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 16
        }
    ));
    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [IrStmt::Return {
            value: Some(IrExpr::LValueToRValue { target, .. }),
            ..
        }] if matches!(target.kind, IrTypeKind::Integer { signed: false, width: 16 })
    ));
}
