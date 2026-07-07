    #[test]
    fn record_inventory_from_ast_keeps_anonymous_nested_integer_record_field() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "RecordDecl",
                    "tagUsed": "struct",
                    "name": "fdb_blob",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "kind": "FieldDecl",
                            "name": "buf",
                            "type": { "qualType": "void *" }
                        },
                        {
                            "kind": "FieldDecl",
                            "name": "size",
                            "type": { "qualType": "size_t" }
                        },
                        {
                            "kind": "RecordDecl",
                            "tagUsed": "struct",
                            "completeDefinition": true,
                            "inner": [
                                {
                                    "kind": "FieldDecl",
                                    "name": "meta_addr",
                                    "type": {
                                        "qualType": "uint32_t",
                                        "desugaredQualType": "unsigned int"
                                    }
                                },
                                {
                                    "kind": "FieldDecl",
                                    "name": "addr",
                                    "type": {
                                        "qualType": "uint32_t",
                                        "desugaredQualType": "unsigned int"
                                    }
                                },
                                {
                                    "kind": "FieldDecl",
                                    "name": "len",
                                    "type": { "qualType": "size_t" }
                                }
                            ]
                        },
                        {
                            "kind": "FieldDecl",
                            "name": "saved",
                            "type": {
                                "qualType": "struct (unnamed at sources/FlashDB/inc/fdb_def.h:319:5)"
                            }
                        }
                    ]
                }
            ]
        });

        let abi = TargetAbiProfile {
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
        let inventory = record_inventory_from_ast_with_target_abi(&ast, Some(&abi));
        let fields = inventory
            .get("fdb_blob")
            .expect("anonymous nested record field stays modeled");

        assert_eq!(fields.len(), 3);
        assert_eq!(fields[2].name, "saved");
        let IrTypeKind::Record {
            name,
            fields: Some(saved_fields),
        } = &fields[2].ty.kind
        else {
            panic!("saved field should lower to a complete nested record");
        };
        assert_eq!(name, "fdb_blob_saved");
        assert_eq!(saved_fields.len(), 3);
        assert_eq!(saved_fields[0].name, "meta_addr");
        assert_eq!(saved_fields[1].name, "addr");
        assert_eq!(saved_fields[2].name, "len");
    }
