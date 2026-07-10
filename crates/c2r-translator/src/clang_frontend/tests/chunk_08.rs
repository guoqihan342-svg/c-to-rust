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
    for context in [
        AssignmentCallComparisonContext::DoWhileTail,
        AssignmentCallComparisonContext::IfCondition,
    ] {
        for (opcode, expected) in [
            ("==", ClangBinaryOperator::Eq),
            ("!=", ClangBinaryOperator::Neq),
            ("<", ClangBinaryOperator::Lt),
            ("<=", ClangBinaryOperator::Le),
            (">", ClangBinaryOperator::Gt),
            (">=", ClangBinaryOperator::Ge),
        ] {
            assert_eq!(context.comparison_operator(Some(opcode)), Some(expected));
        }
    }
    assert_eq!(
        AssignmentCallComparisonContext::IfCondition.comparison_operator(Some("&&")),
        None
    );
}

fn direct_int_call_ast(callee: &str) -> Value {
    serde_json::json!({
        "kind": "CallExpr",
        "type": { "qualType": "int" },
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "FunctionToPointerDecay",
            "type": { "qualType": "int (*)(void)" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "int (void)" },
                "referencedDecl": { "kind": "FunctionDecl", "name": callee }
            }]
        }]
    })
}

fn int_decl_read_ast(name: &str) -> Value {
    serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "int" },
        "inner": [{
            "kind": "DeclRefExpr",
            "type": { "qualType": "int" },
            "referencedDecl": { "kind": "VarDecl", "name": name }
        }]
    })
}

fn do_while_assignment_call_with_suffix_ast(
    target: &str,
    callee: &str,
    suffix_scalar: &str,
    comparison_opcode: &str,
    logical_opcode: &str,
) -> Value {
    serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": logical_opcode,
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "BinaryOperator",
                "opcode": comparison_opcode,
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
                                    "referencedDecl": { "kind": "VarDecl", "name": target }
                                },
                                direct_int_call_ast(callee)
                            ]
                        }]
                    },
                    { "kind": "IntegerLiteral", "value": "7", "type": { "qualType": "int" } }
                ]
            },
            {
                "kind": "BinaryOperator",
                "opcode": ">",
                "type": { "qualType": "int" },
                "inner": [
                    int_decl_read_ast(suffix_scalar),
                    { "kind": "IntegerLiteral", "value": "2", "type": { "qualType": "int" } }
                ]
            }
        ]
    })
}

#[test]
fn do_while_assignment_call_comparison_and_pure_suffix_normalizes_without_clang() {
    for (target, callee, suffix_scalar, comparison_opcode, expected_op) in [
        (
            "sample",
            "pull_sample",
            "remaining",
            "!=",
            ClangBinaryOperator::Neq,
        ),
        (
            "cursor",
            "advance_cursor",
            "budget",
            "<=",
            ClangBinaryOperator::Le,
        ),
    ] {
        let ast = do_while_assignment_call_with_suffix_ast(
            target,
            callee,
            suffix_scalar,
            comparison_opcode,
            "&&",
        );

        let normalized = do_while_tail_call_assignment_from_ast(&ast)
            .expect("normalize renamed do-while assignment-call comparison with pure suffix");
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
                value: ClangExprSkeleton::Call { callee: actual_callee, .. }
            } if name == target && actual_callee == callee
        ));
        assert!(matches!(
            condition,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::LogAnd,
                lhs,
                rhs,
                ..
            } if matches!(
                lhs.as_ref(),
                ClangExprSkeleton::Binary { op, .. } if *op == expected_op
            ) && matches!(
                rhs.as_ref(),
                ClangExprSkeleton::Binary {
                    op: ClangBinaryOperator::Gt,
                    lhs,
                    ..
                } if matches!(
                    lhs.as_ref(),
                    ClangExprSkeleton::LValueToRValue { expr, .. }
                        if matches!(
                            expr.as_ref(),
                            ClangExprSkeleton::DeclRef { name, .. } if name == suffix_scalar
                        )
                )
            )
        ));
    }
}

#[test]
fn do_while_assignment_call_comparison_rejects_effectful_suffixes_and_logical_or() {
    let mut call_suffix = do_while_assignment_call_with_suffix_ast(
        "sample",
        "pull_sample",
        "remaining",
        "!=",
        "&&",
    );
    call_suffix["inner"][1] = direct_int_call_ast("check_limit");

    let mut assignment_suffix = do_while_assignment_call_with_suffix_ast(
        "sample",
        "pull_sample",
        "remaining",
        "!=",
        "&&",
    );
    assignment_suffix["inner"][1] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "=",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "DeclRefExpr",
                "type": { "qualType": "int" },
                "referencedDecl": { "kind": "VarDecl", "name": "remaining" }
            },
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
        ]
    });

    let logical_or = do_while_assignment_call_with_suffix_ast(
        "sample",
        "pull_sample",
        "remaining",
        "!=",
        "||",
    );
    for (ast, expected_reason) in [
        (call_suffix, "second call"),
        (assignment_suffix, "second assignment"),
        (logical_or, "only supports a pure suffix joined by &&"),
    ] {
        let normalized = do_while_tail_call_assignment_from_ast(&ast)
            .expect("classify out-of-slice do-while condition");
        let AssignmentCallComparisonNormalization::Rejected(reason) = normalized else {
            panic!("expected rejected normalization");
        };
        assert!(reason.contains(expected_reason), "{reason}");
    }
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
