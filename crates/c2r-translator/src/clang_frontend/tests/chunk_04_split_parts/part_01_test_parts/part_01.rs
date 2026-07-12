
    #[test]
    fn readonly_globals_from_ast_maps_static_const_all_zero_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].name, "table");
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![0, 0, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_rejects_malformed_static_const_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_sentinel",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_length",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "3"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "4"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_side_effect",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "CallExpr",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert!(
            globals.is_empty(),
            "malformed array_filler globals must stay fail-closed: {globals:?}"
        );
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_integer_array_enum_constant_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "EnumDecl",
                    "name": "status",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "id": "0x1001",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_OK",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ConstantExpr",
                                    "type": { "qualType": "int" },
                                    "value": "7",
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "7"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[2]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[2]" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "id": "0x1001",
                                        "kind": "EnumConstantDecl",
                                        "name": "STATUS_OK"
                                    }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].name, "table");
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![7, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_maps_implicit_enum_constant_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "EnumDecl",
                    "name": "status",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "id": "0x1001",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_PENDING",
                            "type": { "qualType": "int" }
                        },
                        {
                            "id": "0x1002",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_ACTIVE",
                            "type": { "qualType": "int" },
                            "inner": [{
                                "kind": "ConstantExpr",
                                "type": { "qualType": "int" },
                                "value": "7",
                                "inner": [{
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "7"
                                }]
                            }]
                        },
                        {
                            "id": "0x1003",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_READY",
                            "type": { "qualType": "int" }
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[1]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[1]" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "id": "0x1003",
                                        "kind": "EnumConstantDecl",
                                        "name": "STATUS_READY"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![8]));
    }
