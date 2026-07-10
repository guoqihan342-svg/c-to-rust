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
