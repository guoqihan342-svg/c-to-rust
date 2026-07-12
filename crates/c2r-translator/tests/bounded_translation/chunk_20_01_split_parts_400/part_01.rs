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
fn clang_ast_rejects_conflicting_desugared_record_scalar_call_signature_without_clang() {
    let mut ast = direct_record_scalar_call_ast(
        "ConflictingAliasRecord",
        "word_value",
        "consume_conflicting_word",
        "forward_conflicting_word",
        "record_value",
    );
    let call = direct_record_scalar_call_node_mut(&mut ast);
    call["inner"][0]["type"] = serde_json::json!({
        "qualType": "uint32_t (*)(uint32_t)",
        "desugaredQualType": "uint32_t (*)(uint16_t)"
    });
    call["inner"][0]["inner"][0]["type"] = serde_json::json!({
        "qualType": "uint32_t (uint32_t)",
        "desugaredQualType": "uint32_t (uint16_t)"
    });

    let error = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "forward_conflicting_word",
    )
    .expect_err("conflicting desugared member call signature must fail closed");
    assert!(
        error.message.contains("does not match parameter type"),
        "{}",
        error.message
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
