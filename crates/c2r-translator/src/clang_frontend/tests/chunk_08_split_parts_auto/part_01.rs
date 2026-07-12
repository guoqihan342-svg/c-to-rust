
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
            "path must contain exactly one arrow rooted at a direct mutable record-pointer DeclRef"
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

#[test]
fn clang_arguments_resolve_relative_include_paths_from_source_root() {
    let parse_spec = ClangParseSpec {
        source_root: PathBuf::from("/workspace/project"),
        source_file: PathBuf::from("src/module.c"),
        function_name: "module_size".to_string(),
        include_paths: vec!["include".to_string()],
        defines: Vec::new(),
        target_abi: None,
        compile_commands: None,
        source_file_hashes: BTreeMap::new(),
        function_source_span: None,
    };

    assert_eq!(
        parse_spec.clang_arguments(),
        vec!["-I/workspace/project/include"]
    );
}

#[test]
fn clang_arguments_preserve_absolute_include_paths() {
    let parse_spec = ClangParseSpec {
        source_root: PathBuf::from("/workspace/project"),
        source_file: PathBuf::from("src/module.c"),
        function_name: "module_size".to_string(),
        include_paths: vec!["/opt/sdk/include".to_string()],
        defines: Vec::new(),
        target_abi: None,
        compile_commands: None,
        source_file_hashes: BTreeMap::new(),
        function_source_span: None,
    };

    assert_eq!(parse_spec.clang_arguments(), vec!["-I/opt/sdk/include"]);
}
