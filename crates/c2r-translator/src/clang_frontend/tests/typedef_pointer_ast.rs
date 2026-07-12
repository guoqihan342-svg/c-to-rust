#[test]
fn binds_typedef_inside_pointer_type_object_before_expression_parsing() {
    let abi = typedef_test_abi();
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "TypedefDecl",
            "name": "output_word_t",
            "type": { "qualType": "unsigned int" }
        }]
    });
    let aliases = type_alias_inventory_from_ast(&ast, Some(&abi));
    let mut expr = serde_json::json!({
        "kind": "UnaryOperator",
        "opcode": "&",
        "type": { "qualType": "output_word_t *" }
    });

    bind_type_aliases_to_ast_type_objects(&mut expr, Some(&abi), &aliases)
        .expect("bind pointer pointee typedef");
    assert_eq!(
        expr["type"]["desugaredQualType"],
        Value::String("unsigned int *".to_string())
    );
    let ty = type_from_ast_type_object(expr.get("type").unwrap(), Some(&abi))
        .expect("parse bound pointer typedef");
    assert!(matches!(
        ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if matches!(pointee.kind, ClangTypeKind::Integer { signed: false, width: 32 })
    ));
}

#[test]
fn rejects_conflicting_desugaring_for_typedef_inside_pointer() {
    let abi = typedef_test_abi();
    let ast = serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [{
            "kind": "TypedefDecl",
            "name": "output_word_t",
            "type": { "qualType": "unsigned int" }
        }]
    });
    let aliases = type_alias_inventory_from_ast(&ast, Some(&abi));
    let mut expr = serde_json::json!({
        "kind": "UnaryOperator",
        "opcode": "&",
        "type": {
            "qualType": "output_word_t *",
            "desugaredQualType": "unsigned short *"
        }
    });

    let error = bind_type_aliases_to_ast_type_objects(&mut expr, Some(&abi), &aliases)
        .expect_err("conflicting pointer typedef desugaring must fail closed");
    assert_eq!(error.kind, "typedef_desugaring_mismatch");
    assert!(error.message.contains("output_word_t *"), "{}", error.message);
}
