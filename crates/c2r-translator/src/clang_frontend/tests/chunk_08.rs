#[test]
fn do_while_tail_assignment_rewrite_only_enters_current_level_if_branches() {
    let int_ty = ClangTypeSkeleton {
        spelled: "int".to_string(),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    };
    let condition = ClangExprSkeleton::IntegerLiteral {
        value: 1,
        spelling: "1".to_string(),
        ty: int_ty.clone(),
    };
    let assignment = ClangStmtSkeleton::Assign {
        target: ClangExprSkeleton::DeclRef {
            name: "value".to_string(),
            ty: int_ty.clone(),
        },
        value: condition.clone(),
    };
    let mut body = vec![
        ClangStmtSkeleton::If {
            condition: condition.clone(),
            then_body: vec![ClangStmtSkeleton::Continue],
            else_body: vec![ClangStmtSkeleton::Continue],
        },
        ClangStmtSkeleton::While {
            condition: condition.clone(),
            body: vec![ClangStmtSkeleton::Continue],
        },
        ClangStmtSkeleton::DoWhile {
            body: vec![ClangStmtSkeleton::Continue],
            condition: condition.clone(),
        },
        ClangStmtSkeleton::For {
            init: Vec::new(),
            condition: Some(condition),
            step: None,
            body: vec![ClangStmtSkeleton::Continue],
        },
    ];

    do_while_body_insert_tail_assignment_before_current_level_continue(
        &mut body,
        &assignment,
    );

    let [
        ClangStmtSkeleton::If {
            then_body,
            else_body,
            ..
        },
        ClangStmtSkeleton::While {
            body: while_body, ..
        },
        ClangStmtSkeleton::DoWhile {
            body: do_while_body, ..
        },
        ClangStmtSkeleton::For { body: for_body, .. },
    ] = body.as_slice()
    else {
        panic!("unexpected rewritten body: {body:?}");
    };
    assert_eq!(
        then_body.as_slice(),
        [assignment.clone(), ClangStmtSkeleton::Continue]
    );
    assert_eq!(
        else_body.as_slice(),
        [assignment, ClangStmtSkeleton::Continue]
    );
    assert_eq!(while_body.as_slice(), [ClangStmtSkeleton::Continue]);
    assert_eq!(do_while_body.as_slice(), [ClangStmtSkeleton::Continue]);
    assert_eq!(for_body.as_slice(), [ClangStmtSkeleton::Continue]);
}

#[test]
fn assignment_call_comparison_contexts_admit_only_their_declared_operators() {
    for (opcode, expected) in [
        ("==", ClangBinaryOperator::Eq),
        ("!=", ClangBinaryOperator::Neq),
        ("<", ClangBinaryOperator::Lt),
        ("<=", ClangBinaryOperator::Le),
        (">", ClangBinaryOperator::Gt),
        (">=", ClangBinaryOperator::Ge),
    ] {
        assert_eq!(
            AssignmentCallComparisonContext::IfCondition.comparison_operator(Some(opcode)),
            Some(expected)
        );
    }
    assert_eq!(
        AssignmentCallComparisonContext::DoWhileTail.comparison_operator(Some("!=")),
        Some(ClangBinaryOperator::Neq)
    );
    assert_eq!(
        AssignmentCallComparisonContext::DoWhileTail.comparison_operator(Some("==")),
        None
    );
    assert_eq!(
        AssignmentCallComparisonContext::IfCondition.comparison_operator(Some("&&")),
        None
    );
}

#[test]
fn if_assignment_call_comparison_normalizes_to_assignment_and_pure_read() {
    let condition = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": ">",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "ParenExpr",
                "type": { "qualType": "int" },
                "inner": [{
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "kind": "VarDecl", "name": "value" }
                        },
                        {
                            "kind": "CallExpr",
                            "type": { "qualType": "int" },
                            "inner": [{
                                "kind": "ImplicitCastExpr",
                                "castKind": "FunctionToPointerDecay",
                                "type": { "qualType": "int (*)(void)" },
                                "inner": [{
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int (void)" },
                                    "referencedDecl": { "kind": "FunctionDecl", "name": "next_value" }
                                }]
                            }]
                        }
                    ]
                }]
            },
            { "kind": "IntegerLiteral", "value": "0", "type": { "qualType": "int" } }
        ]
    });

    let normalized = if_assignment_call_comparison_from_ast(&condition)
        .expect("normalize strict if assignment-call comparison");
    let AssignmentCallComparisonNormalization::Accepted {
        assignment,
        condition,
    } = normalized
    else {
        panic!("expected accepted normalization");
    };
    assert!(matches!(
        assignment,
        ClangStmtSkeleton::Assign {
            target: ClangExprSkeleton::DeclRef { name, .. },
            value: ClangExprSkeleton::Call { callee, .. }
        } if name == "value" && callee == "next_value"
    ));
    assert!(matches!(
        condition,
        ClangExprSkeleton::Binary {
            op: ClangBinaryOperator::Gt,
            lhs,
            ..
        } if matches!(
            lhs.as_ref(),
            ClangExprSkeleton::LValueToRValue { expr, .. }
                if matches!(expr.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "value")
        )
    ));
}
