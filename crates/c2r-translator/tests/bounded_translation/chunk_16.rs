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
            "bad_do_while_tail_assign_continue",
            "current-level continue",
        ),
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
        (
            "bad_if_tail_assign_shape",
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
