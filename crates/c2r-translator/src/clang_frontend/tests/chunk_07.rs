#[test]
fn character_literal_ast_lowers_to_plain_int_literal() {
    let ast = serde_json::json!({
        "kind": "CharacterLiteral",
        "type": { "qualType": "int" },
        "value": 32
    });

    let skeleton = expr_skeleton_from_ast(&ast).expect("lower plain character literal");
    let ClangExprSkeleton::IntegerLiteral {
        value,
        spelling,
        ty,
    } = skeleton
    else {
        panic!("expected integer literal skeleton");
    };
    assert_eq!(value, 32);
    assert_eq!(spelling, "32");
    assert_eq!(ty.canonical, "int");
}

#[test]
fn character_literal_ast_rejects_missing_negative_or_out_of_range_values() {
    for (ast, expected_kind) in [
        (
            serde_json::json!({
                "kind": "CharacterLiteral",
                "type": { "qualType": "int" }
            }),
            "invalid_character_literal",
        ),
        (
            serde_json::json!({
                "kind": "CharacterLiteral",
                "type": { "qualType": "int" },
                "value": -1
            }),
            "unsupported_character_literal_value",
        ),
        (
            serde_json::json!({
                "kind": "CharacterLiteral",
                "type": { "qualType": "int" },
                "value": 2147483648_i64
            }),
            "unsupported_character_literal_value",
        ),
    ] {
        let error = expr_skeleton_from_ast(&ast).expect_err("literal must fail closed");
        assert_eq!(error.kind, expected_kind);
    }
}

#[test]
fn character_literal_ast_rejects_non_int_type() {
    let ast = serde_json::json!({
        "kind": "CharacterLiteral",
        "type": { "qualType": "wchar_t" },
        "value": 65
    });

    let error = expr_skeleton_from_ast(&ast).expect_err("wide literal must fail closed");
    assert_eq!(error.kind, "unsupported_character_literal_type");
}
