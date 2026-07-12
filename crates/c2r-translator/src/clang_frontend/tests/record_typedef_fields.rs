fn typedef_test_abi() -> TargetAbiProfile {
    TargetAbiProfile {
        triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        int_align: 32,
        char_width: 8,
        char_align: 8,
        plain_char_signed: Some(true),
        short_width: 16,
        short_align: 16,
        long_width: 64,
        long_align: 64,
        long_long_width: 64,
        long_long_align: 64,
        pointer_width: 64,
        pointer_align: 64,
    }
}

#[test]
fn type_object_keeps_desugared_integer_for_late_abi_binding() {
    let type_object = serde_json::json!({
        "qualType": "renamed_family_t",
        "desugaredQualType": "unsigned short"
    });

    let mut ty = type_from_ast_type_object(&type_object, None)
        .expect("desugared target-dependent type should remain bindable");
    assert_eq!(ty.spelled, "unsigned short");
    assert!(matches!(ty.kind, ClangTypeKind::Unsupported { .. }));

    bind_target_abi_to_type(&mut ty, &typedef_test_abi());
    assert!(matches!(
        ty.kind,
        ClangTypeKind::Integer {
            signed: false,
            width: 16
        }
    ));
}

#[test]
fn record_inventory_uses_renamed_typedef_without_field_desugaring() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "kind": "TypedefDecl",
                "name": "renamed_family_t",
                "type": {"qualType": "unsigned short"}
            },
            {
                "kind": "RecordDecl",
                "tagUsed": "struct",
                "completeDefinition": true,
                "name": "renamed_endpoint",
                "inner": [{
                    "kind": "FieldDecl",
                    "name": "family",
                    "type": {"qualType": "renamed_family_t"}
                }]
            }
        ]
    });

    let inventory = record_inventory_from_ast_with_target_abi(&ast, Some(&typedef_test_abi()));
    let fields = inventory
        .get("renamed_endpoint")
        .expect("record field should resolve through translation-unit typedef inventory");

    assert_eq!(fields.len(), 1);
    assert_eq!(fields[0].name, "family");
    assert_eq!(fields[0].ty.spelled, "renamed_family_t");
    assert_eq!(fields[0].ty.canonical, "unsigned short");
    assert!(matches!(
        fields[0].ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 16
        }
    ));
}

#[test]
fn typedef_and_desugared_type_conflict_stays_fail_closed() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "TypedefDecl",
            "name": "renamed_family_t",
            "type": {"qualType": "unsigned short"}
        }]
    });
    let type_object = serde_json::json!({
        "qualType": "renamed_family_t",
        "desugaredQualType": "unsigned int"
    });
    let abi = typedef_test_abi();
    let aliases = type_alias_inventory_from_ast(&ast, Some(&abi));

    let error = type_from_ast_type_object_with_aliases(&type_object, Some(&abi), &aliases)
        .expect_err("typedef and desugared width drift must fail closed");

    assert_eq!(error.kind, "typedef_desugaring_mismatch");
    assert!(error.message.contains("renamed_family_t"));
    assert!(error.message.contains("unsigned short"));
    assert!(error.message.contains("unsigned int"));
}

#[test]
fn unknown_record_field_typedef_remains_incomplete() {
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "RecordDecl",
            "tagUsed": "struct",
            "completeDefinition": true,
            "name": "renamed_endpoint",
            "inner": [{
                "kind": "FieldDecl",
                "name": "family",
                "type": {"qualType": "unknown_family_t"}
            }]
        }]
    });

    let inventory = record_inventory_from_ast_with_target_abi(&ast, Some(&typedef_test_abi()));
    assert!(!inventory.contains_key("renamed_endpoint"));
}
