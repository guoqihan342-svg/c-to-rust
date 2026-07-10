#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_do_while_scalar_incdec_candidate_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_scalar_incdec_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "do_while_postinc_paths")
            .expect("lower do-while scalar incdec fixture without invoking clang");
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
        body.as_slice(),
        [
            IrStmt::If { then_body: continue_body, .. },
            IrStmt::If { then_body: break_body, .. }
        ] if matches!(continue_body.as_slice(), [IrStmt::Continue { .. }])
            && matches!(break_body.as_slice(), [IrStmt::Break { .. }])
    ));
    let IrExpr::Binary {
        op: IrBinOp::Lt,
        lhs,
        ..
    } = condition
    else {
        panic!("expected less-than do-while condition, got {condition:?}");
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if matches!(target.as_ref(), IrExpr::Var { name, .. } if name == "value")
    ));

    let emitted =
        emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect("emit frontend/emitter candidate from do-while scalar incdec fixture");
    let rust = &emitted.rust;

    assert!(lowered.globals.is_empty());
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn do_while_postinc_paths(mut value: i32, limit: i32) -> i32"));
    assert_eq!(rust.matches("let post_inc_value: i32 = value;").count(), 2, "{rust}");
    assert_eq!(
        rust.matches("value = value.checked_add(1i32).expect(\"signed addition overflow\");")
            .count(),
        2,
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-do-while-scalar-incdec-candidate",
        rust,
        "    assert_eq!(do_while_postinc_paths(2, 1), 3);\n    assert_eq!(do_while_postinc_paths(1, 0), 2);\n    assert_eq!(do_while_postinc_paths(3, 6), 3);",
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_do_while_scalar_incdec_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_scalar_incdec_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason) in [
        (
            "bad_do_while_same_variable_sibling",
            "binary rhs reads variable value modified by lhs side-effect expression",
        ),
        (
            "bad_do_while_two_incdec",
            "comparison cannot lower two direct increment/decrement operands",
        ),
    ] {
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .unwrap_or_else(|error| panic!("lower fixture {function_name}: {error}"));
        let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect_err("out-of-bound do-while incdec comparison must fail closed");

        assert!(
            error.reason.contains("stmt[0].do while condition"),
            "{function_name}: {error:?}"
        );
        assert!(
            error.reason.contains(expected_reason),
            "{function_name}: {error:?}"
        );
    }
}
