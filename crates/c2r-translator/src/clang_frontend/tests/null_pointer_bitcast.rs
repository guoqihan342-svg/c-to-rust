#[test]
fn implicit_bitcast_retargets_an_already_proven_null_pointer() {
    let expr = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "BitCast",
        "type": { "qualType": "const unsigned char *" },
        "inner": [{
            "kind": "ParenExpr",
            "type": { "qualType": "void *" },
            "inner": [{
                "kind": "CStyleCastExpr",
                "castKind": "NullToPointer",
                "type": { "qualType": "void *" },
                "inner": [{
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }]
            }]
        }]
    });

    let skeleton = expr_skeleton_from_ast(&expr).expect("lower generic null pointer bitcast");
    let ClangExprSkeleton::NullPtr { ty } = skeleton else {
        panic!("expected retargeted NullPtr skeleton");
    };
    assert_eq!(ty.spelled, "const unsigned char *");
}

#[test]
fn implicit_bitcast_of_non_null_pointer_stays_unsupported() {
    let expr = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "BitCast",
        "type": { "qualType": "const unsigned char *" },
        "inner": [{
            "kind": "DeclRefExpr",
            "type": { "qualType": "void *" },
            "referencedDecl": {
                "kind": "ParmVarDecl",
                "name": "opaque",
                "type": { "qualType": "void *" }
            }
        }]
    });

    let skeleton = expr_skeleton_from_ast(&expr).expect("record unsupported bitcast skeleton");
    let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
        panic!("non-null BitCast must remain unsupported");
    };
    assert!(reason.contains("BitCast"));
}
