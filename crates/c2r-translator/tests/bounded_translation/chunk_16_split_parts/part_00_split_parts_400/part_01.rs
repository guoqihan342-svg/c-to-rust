#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_do_while_assignment_comparison_and_pure_suffix_runs_without_clang() {
    // Evidence shape only: sources/FlashDB/src/fdb_kvdb.c:1936.
    let (ast, function_name) = renamed_do_while_assignment_fixture_with_suffix(
        "&&",
        pure_do_while_suffix_comparison_ast(),
    );
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower renamed assignment-call comparison with pure scalar comparison suffix");
    let [IrStmt::DoWhile {
        body, condition, ..
    }, IrStmt::Return { .. }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected do-while followed by return, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(matches!(
        body.last(),
        Some(IrStmt::Assign { target, value, .. })
            if matches!(target, IrExpr::Var { name, .. } if name == "value")
                && matches!(value, IrExpr::Call { callee, .. } if callee == "step_value")
    ));
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::LogAnd,
            lhs,
            rhs,
            ..
        } if matches!(lhs.as_ref(), IrExpr::Binary { op: IrBinOp::Neq, .. })
            && matches!(rhs.as_ref(), IrExpr::Binary { op: IrBinOp::Gt, .. })
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit renamed do-while assignment and suffix candidate");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    let rust = emitted.rust;
    assert!(rust.contains("pub fn advance_while_guarded"), "{rust}");
    let assignment = rust
        .find("value = step_value(value);")
        .expect("tail assignment");
    let left_comparison = rust[assignment..]
        .find("value != 0i32")
        .map(|offset| assignment + offset)
        .expect("assignment-result comparison");
    let short_circuit = rust[left_comparison..]
        .find("&&")
        .map(|offset| left_comparison + offset)
        .expect("short-circuit conjunction");
    let suffix = rust[short_circuit..]
        .find("break_at > 0i32")
        .map(|offset| short_circuit + offset)
        .expect("pure comparison suffix");
    assert!(
        assignment < left_comparison && left_comparison < short_circuit && short_circuit < suffix
    );

    let runtime_rust = format!(
        "fn step_value(value: i32) -> i32 {{ if value < 3 {{ value + 1 }} else {{ 0 }} }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-do-while-assignment-pure-suffix",
        &runtime_rust,
        "    assert_eq!(advance_while_guarded(1, 99), 0);\n    assert_eq!(advance_while_guarded(1, -1), 2);\n    assert_eq!(advance_while_guarded(2, 2), 2);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn do_while_assignment_comparison_rejects_effectful_suffixes_and_logical_or_without_clang() {
    let call_suffix = serde_json::json!({
        "kind": "CallExpr",
        "type": { "qualType": "int" },
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "FunctionToPointerDecay",
            "type": { "qualType": "int (*)(void)" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "int (void)" },
                "referencedDecl": { "kind": "FunctionDecl", "name": "check_limit" }
            }]
        }]
    });
    let assignment_suffix = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "=",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "DeclRefExpr",
                "type": { "qualType": "int" },
                "referencedDecl": { "kind": "ParmVarDecl", "name": "break_at" }
            },
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
        ]
    });
    for (logical_opcode, suffix, expected_reason) in [
        ("&&", call_suffix, "second call"),
        ("&&", assignment_suffix, "second assignment"),
        (
            "||",
            pure_do_while_suffix_comparison_ast(),
            "only supports a pure suffix joined by &&",
        ),
    ] {
        let (ast, function_name) =
            renamed_do_while_assignment_fixture_with_suffix(logical_opcode, suffix);
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("out-of-slice do-while conjunction must fail closed");
        assert!(
            error.message.contains(expected_reason),
            "expected {expected_reason:?}, got {error:?}"
        );
    }
}
