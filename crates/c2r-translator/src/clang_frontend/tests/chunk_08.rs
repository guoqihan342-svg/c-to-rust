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

    do_while_body_insert_tail_assignment_before_current_level_continue(&mut body, &assignment);

    let [ClangStmtSkeleton::If {
        then_body,
        else_body,
        ..
    }, ClangStmtSkeleton::While {
        body: while_body, ..
    }, ClangStmtSkeleton::DoWhile {
        body: do_while_body,
        ..
    }, ClangStmtSkeleton::For { body: for_body, .. }] = body.as_slice()
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
    let mut call_suffix =
        do_while_assignment_call_with_suffix_ast("sample", "pull_sample", "remaining", "!=", "&&");
    call_suffix["inner"][1] = direct_int_call_ast("check_limit");

    let mut assignment_suffix =
        do_while_assignment_call_with_suffix_ast("sample", "pull_sample", "remaining", "!=", "&&");
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

    let logical_or =
        do_while_assignment_call_with_suffix_ast("sample", "pull_sample", "remaining", "!=", "||");
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

fn local_record_dot_path_ast(root: &str, root_ty: &str, members: &[(&str, &str)]) -> Value {
    let mut expr = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": root_ty },
        "referencedDecl": { "kind": "VarDecl", "name": root }
    });
    for (field, ty) in members {
        expr = serde_json::json!({
            "kind": "MemberExpr",
            "name": field,
            "isArrow": false,
            "type": { "qualType": ty },
            "inner": [expr]
        });
    }
    expr
}

fn local_record_tail_assignment_ast(target: Value, callee: &str, result_ty: &str) -> Value {
    serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "!=",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "ParenExpr",
                "type": { "qualType": result_ty },
                "inner": [{
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": result_ty },
                    "inner": [target, direct_int_call_ast(callee)]
                }]
            },
            { "kind": "IntegerLiteral", "value": "0", "type": { "qualType": "int" } }
        ]
    })
}

fn clang_local_member_path(expr: &ClangExprSkeleton) -> Option<(String, Vec<String>)> {
    match expr {
        ClangExprSkeleton::DeclRef { name, .. } => Some((name.clone(), Vec::new())),
        ClangExprSkeleton::Member {
            base,
            field,
            is_arrow: false,
            ..
        } => {
            let (root, mut fields) = clang_local_member_path(base)?;
            fields.push(field.clone());
            Some((root, fields))
        }
        _ => None,
    }
}

#[test]
fn do_while_local_record_dot_path_assignment_call_normalizes_without_names() {
    for (root, root_ty, middle, middle_ty, leaf, callee) in [
        (
            "packet",
            "struct packet_box",
            "state",
            "struct packet_box_state",
            "code",
            "pull_code",
        ),
        (
            "cursor",
            "struct cursor_frame",
            "window",
            "struct cursor_frame_window",
            "offset",
            "advance_offset",
        ),
    ] {
        let expected_fields = vec![middle.to_string(), leaf.to_string()];
        let target =
            local_record_dot_path_ast(root, root_ty, &[(middle, middle_ty), (leaf, "int")]);
        let condition = local_record_tail_assignment_ast(target, callee, "int");

        let normalized = do_while_tail_call_assignment_from_ast(&condition)
            .expect("normalize renamed local record dot-path assignment-call comparison");
        let AssignmentCallComparisonNormalization::Accepted {
            assignment,
            condition,
        } = normalized
        else {
            panic!("expected accepted local record normalization");
        };
        let ClangStmtSkeleton::Assign { target, value } = assignment else {
            panic!("expected normalized assignment");
        };
        assert_eq!(
            clang_local_member_path(&target),
            Some((root.to_string(), expected_fields.clone()))
        );
        assert!(
            matches!(value, ClangExprSkeleton::Call { callee: actual, .. } if actual == callee)
        );
        assert!(matches!(
            condition,
            ClangExprSkeleton::Binary { lhs, .. }
                if matches!(
                    lhs.as_ref(),
                    ClangExprSkeleton::LValueToRValue { expr, .. }
                        if clang_local_member_path(expr)
                            == Some((root.to_string(), expected_fields.clone()))
                )
        ));
    }
}

#[test]
fn do_while_local_record_dot_path_rejects_adjacent_targets() {
    let valid = local_record_dot_path_ast(
        "packet",
        "struct packet_box",
        &[("state", "struct packet_box_state"), ("code", "int")],
    );
    let mut arrow = valid.clone();
    arrow["inner"][0]["isArrow"] = Value::Bool(true);
    let mut parameter_root = valid.clone();
    parameter_root["inner"][0]["inner"][0]["referencedDecl"]["kind"] =
        Value::String("ParmVarDecl".to_string());
    let mut pointer_hop = valid.clone();
    pointer_hop["inner"][0]["type"] = serde_json::json!({ "qualType": "int *" });
    let non_integer_leaf = local_record_dot_path_ast(
        "packet",
        "struct packet_box",
        &[("state", "struct packet_box_state"), ("ratio", "float")],
    );

    for (target, result_ty, expected_reason) in [
        (arrow, "int", "arrow"),
        (parameter_root, "int", "direct local"),
        (pointer_hop, "int", "complete by-value record"),
        (non_integer_leaf, "float", "not a fixed-width integer"),
    ] {
        let normalized = do_while_tail_call_assignment_from_ast(&local_record_tail_assignment_ast(
            target,
            "pull_code",
            result_ty,
        ))
        .expect("classify adjacent local record target");
        let AssignmentCallComparisonNormalization::Rejected(reason) = normalized else {
            panic!("expected rejected local record target");
        };
        assert!(reason.contains(expected_reason), "{reason}");
    }
}

#[test]
fn if_assignment_call_comparison_rejects_renamed_local_member_target() {
    let target = local_record_dot_path_ast(
        "ledger",
        "struct ledger_frame",
        &[
            ("snapshot", "struct ledger_frame_snapshot"),
            ("status", "int"),
        ],
    );
    let condition = local_record_tail_assignment_ast(target, "refresh_status", "int");

    let normalized = if_assignment_call_comparison_from_ast(&condition)
        .expect("classify renamed if local-member assignment-call target");
    let AssignmentCallComparisonNormalization::Rejected(reason) = normalized else {
        panic!("if local-member assignment-call target must remain rejected");
    };
    assert!(
        reason.contains(
            "if condition assignment-call target must be a direct non-volatile, non-atomic fixed-width integer DeclRef"
        ),
        "{reason}"
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
