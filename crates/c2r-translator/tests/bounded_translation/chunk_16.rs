#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_normalizes_do_while_tail_call_assignment_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "do_while_tail_assign_paths",
    )
    .expect("lower bounded do-while tail call assignment fixture");
    let [
        IrStmt::DoWhile {
            body, condition, ..
        },
        IrStmt::Return { .. },
    ] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected do-while followed by return, got {:?}",
            lowered.function_ir.body
        );
    };

    assert!(matches!(
        body.as_slice(),
        [
            IrStmt::If {
                then_body,
                else_body,
                ..
            },
            IrStmt::Assign { target, value, .. }
        ] if matches!(then_body.as_slice(), [IrStmt::Break { .. }])
            && else_body.is_empty()
            && matches!(target, IrExpr::Var { name, .. } if name == "value")
            && matches!(value, IrExpr::Call { callee, .. } if callee == "step_value")
    ));
    assert!(matches!(
        condition,
        IrExpr::Binary {
            op: IrBinOp::Neq,
            lhs,
            ..
        } if matches!(
            lhs.as_ref(),
            IrExpr::LValueToRValue { expr, .. }
                if matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value")
        )
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit bounded do-while tail call assignment candidate");
    let rust = &emitted.rust;
    assert!(lowered.globals.is_empty());
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains(
        "pub fn do_while_tail_assign_paths(mut value: i32, break_at: i32) -> i32"
    ));
    assert_eq!(rust.matches("value = step_value(value);").count(), 1, "{rust}");
    let assignment = rust.find("value = step_value(value);").expect("tail assignment");
    let sentinel = rust[assignment..]
        .find("value != 0i32")
        .map(|offset| assignment + offset)
        .expect("pure sentinel comparison after assignment");
    assert!(assignment < sentinel, "{rust}");

    let runtime_rust = format!(
        "fn step_value(value: i32) -> i32 {{ if value < 3 {{ value + 1 }} else {{ 0 }} }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-do-while-tail-call-assignment",
        &runtime_rust,
        "    assert_eq!(do_while_tail_assign_paths(1, 99), 0);\n    assert_eq!(do_while_tail_assign_paths(2, 2), 2);",
    );

    let converted = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "do_while_tail_assign_converted",
    )
    .expect("lower clang-proven integer conversion around direct call result");
    let [IrStmt::DoWhile { body, .. }, IrStmt::Return { .. }] =
        converted.function_ir.body.as_slice()
    else {
        panic!(
            "expected converted do-while followed by return, got {:?}",
            converted.function_ir.body
        );
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign {
            value: IrExpr::Cast { expr, .. },
            ..
        }] if matches!(expr.as_ref(), IrExpr::Call { callee, .. } if callee == "step_unsigned")
    ));
    let converted_rust = emit_rust_from_ir_with_globals(
        &converted.function_ir,
        &converted.globals,
    )
    .expect("emit converted do-while tail call assignment candidate")
    .rust;
    let converted_runtime_rust = format!(
        "fn step_unsigned(value: i32) -> u32 {{ if value < 2 {{ (value + 1) as u32 }} else {{ 0 }} }}\n{converted_rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-do-while-tail-call-assignment-converted",
        &converted_runtime_rust,
        "    assert_eq!(do_while_tail_assign_converted(0), 0);",
    );

    let mut continued_ast = ast.clone();
    let continued_function = continued_ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == "bad_do_while_tail_assign_continue")
        .expect("continue boundary function");
    continued_function["inner"][1]["inner"][0]["inner"][0] = serde_json::json!({
        "kind": "CompoundStmt",
        "inner": [
            {
                "kind": "IfStmt",
                "inner": [
                    { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } },
                    { "kind": "ContinueStmt" }
                ]
            }
        ]
    });
    let continued = lower_function_and_globals_from_clang_ast_json_value(
        &continued_ast,
        "bad_do_while_tail_assign_continue",
    )
    .expect("normalize current-level continue through the do-while tail assignment");
    let [IrStmt::DoWhile { body, .. }] = continued.function_ir.body.as_slice() else {
        panic!(
            "expected one do-while with rewritten continue, got {:?}",
            continued.function_ir.body
        );
    };
    assert!(matches!(
        body.as_slice(),
        [
            IrStmt::If {
                then_body,
                else_body,
                ..
            },
            IrStmt::Assign { value: normal, .. }
        ] if matches!(
            then_body.as_slice(),
            [IrStmt::Assign { value: first, .. }, IrStmt::Continue { .. }]
                if matches!(first, IrExpr::Call { callee, .. } if callee == "step_value")
        )
            && else_body.is_empty()
            && matches!(normal, IrExpr::Call { callee, .. } if callee == "step_value")
    ));
    let continued_rust = emit_rust_from_ir_with_globals(
        &continued.function_ir,
        &continued.globals,
    )
    .expect("emit current-level continue after inserting its tail assignment")
    .rust;
    assert_eq!(
        continued_rust.matches("value = step_value(value);").count(),
        2,
        "{continued_rust}"
    );
    let first_assignment = continued_rust
        .find("value = step_value(value);")
        .expect("continue path tail assignment");
    let continue_condition = continued_rust[first_assignment..]
        .find("value != 0i32")
        .map(|offset| first_assignment + offset)
        .expect("continue path pure sentinel check");
    let continue_stmt = continued_rust[continue_condition..]
        .find("continue;")
        .map(|offset| continue_condition + offset)
        .expect("rewritten continue");
    assert!(first_assignment < continue_condition && continue_condition < continue_stmt);
    let continued_runtime_rust = format!(
        "fn step_value(value: i32) -> i32 {{ if value > 0 {{ value - 1 }} else {{ 0 }} }}\n{continued_rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-do-while-tail-call-assignment-continue",
        &continued_runtime_rust,
        "    bad_do_while_tail_assign_continue(3);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn do_while_tail_assignment_rewrite_does_not_enter_nested_loops() {
    let mut ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == "bad_do_while_tail_assign_continue")
        .expect("continue boundary function");
    function["inner"][1]["inner"][0]["inner"][0] = serde_json::json!({
        "kind": "CompoundStmt",
        "inner": [
            {
                "kind": "WhileStmt",
                "inner": [
                    { "kind": "IntegerLiteral", "value": "0", "type": { "qualType": "int" } },
                    { "kind": "CompoundStmt", "inner": [{ "kind": "ContinueStmt" }] }
                ]
            }
        ]
    });

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "bad_do_while_tail_assign_continue",
    )
    .expect("nested-loop continue must not block outer tail normalization");
    let [IrStmt::DoWhile { body, .. }] = lowered.function_ir.body.as_slice() else {
        panic!("expected outer do-while, got {:?}", lowered.function_ir.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::While { body: nested, .. }, IrStmt::Assign { .. }]
            if matches!(nested.as_slice(), [IrStmt::Continue { .. }])
    ));
    let rust = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit nested-loop boundary")
        .rust;
    assert_eq!(rust.matches("value = step_value(value);").count(), 1, "{rust}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn pure_do_while_suffix_comparison_ast() -> Value {
    serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": ">",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "ImplicitCastExpr",
                "castKind": "LValueToRValue",
                "type": { "qualType": "int" },
                "inner": [{
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "kind": "ParmVarDecl", "name": "break_at" }
                }]
            },
            { "kind": "IntegerLiteral", "value": "0", "type": { "qualType": "int" } }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn renamed_do_while_assignment_fixture_with_suffix(
    logical_opcode: &str,
    suffix: Value,
) -> (Value, &'static str) {
    let mut ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");
    let function_name = "advance_while_guarded";
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == "do_while_tail_assign_paths")
        .expect("generic do-while assignment fixture");
    function["name"] = Value::String(function_name.to_string());
    let original_condition = function["inner"][2]["inner"][0]["inner"][1].take();
    function["inner"][2]["inner"][0]["inner"][1] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": logical_opcode,
        "type": { "qualType": "int" },
        "inner": [original_condition, suffix]
    });
    (ast, function_name)
}

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
    let [
        IrStmt::DoWhile {
            body, condition, ..
        },
        IrStmt::Return { .. },
    ] = lowered.function_ir.body.as_slice()
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
    assert!(assignment < left_comparison && left_comparison < short_circuit && short_circuit < suffix);

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

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_do_while_tail_call_assignment_boundaries_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason) in [
        (
            "bad_do_while_tail_assign_deref_target",
            "direct non-volatile, non-atomic fixed-width integer DeclRef",
        ),
        (
            "bad_do_while_tail_assign_second_call",
            "second call",
        ),
        (
            "bad_while_tail_assign_shape",
            "opcode = is outside the current skeleton",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("out-of-bound tail assignment shape must fail closed");
        assert!(
            error.message.contains(expected_reason),
            "{function_name}: expected {expected_reason:?}, got {error:?}"
        );
    }
}
