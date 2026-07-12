#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_single_statement_else_if_keeps_assignment_inside_else() {
    let function_name = "if_assign_call_else_if_owner";
    let mut ast = if_assignment_call_fixture(function_name, "!=");
    let function = if_assignment_call_function_mut(&mut ast, function_name);
    let nested_condition = function["inner"][1]["inner"][0]["inner"][0].clone();
    function["type"]["qualType"] = serde_json::json!("int (int, int)");
    function["inner"] = serde_json::json!([
        {
            "kind": "ParmVarDecl",
            "name": "value",
            "type": { "qualType": "int" }
        },
        {
            "kind": "ParmVarDecl",
            "name": "choose_outer",
            "type": { "qualType": "int" }
        },
        {
            "kind": "CompoundStmt",
            "inner": [
                {
                    "kind": "IfStmt",
                    "inner": [
                        clang_int_read("choose_outer"),
                        clang_int_return(10),
                        {
                            "kind": "IfStmt",
                            "inner": [
                                nested_condition,
                                clang_int_return(20),
                                clang_int_return(30)
                            ]
                        }
                    ]
                }
            ]
        }
    ]);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower single-statement else-if assignment-call comparison");
    let [IrStmt::If {
        then_body,
        else_body,
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected one outer If, got {:?}",
            lowered.function_ir.body
        );
    };
    assert!(matches!(then_body.as_slice(), [IrStmt::Return { .. }]));
    assert!(matches!(
        else_body.as_slice(),
        [
            IrStmt::Assign { target, value, .. },
            IrStmt::If {
                then_body: nested_then,
                else_body: nested_else,
                ..
            }
        ] if matches!(target, IrExpr::Var { name, .. } if name == "value")
            && matches!(value, IrExpr::Call { callee, .. } if callee == "step_value")
            && matches!(nested_then.as_slice(), [IrStmt::Return { .. }])
            && matches!(nested_else.as_slice(), [IrStmt::Return { .. }])
    ));

    let rust = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit single-statement else-if assignment-call comparison")
        .rust;
    let outer_if = rust
        .find("if choose_outer != 0i32")
        .unwrap_or_else(|| panic!("missing outer if: {rust}"));
    let assignment = rust
        .find("value = step_value(value);")
        .expect("else-owned assignment");
    let nested_if = rust[assignment..]
        .find("if (value != 0i32)")
        .map(|offset| assignment + offset)
        .expect("nested pure if");
    assert!(outer_if < assignment && assignment < nested_if, "{rust}");

    let runtime_rust = format!(
        "use std::sync::atomic::{{AtomicUsize, Ordering}};\nstatic CALLS: AtomicUsize = AtomicUsize::new(0);\nfn step_value(value: i32) -> i32 {{ CALLS.fetch_add(1, Ordering::SeqCst); value + 1 }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-if-assignment-call-else-if-owner",
        &runtime_rust,
        r#"
    CALLS.store(0, Ordering::SeqCst);
    assert_eq!(if_assign_call_else_if_owner(99, 1), 10);
    assert_eq!(CALLS.load(Ordering::SeqCst), 0);
    assert_eq!(if_assign_call_else_if_owner(-1, 0), 30);
    assert_eq!(if_assign_call_else_if_owner(0, 0), 20);
    assert_eq!(CALLS.load(Ordering::SeqCst), 2);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_boundaries_fail_closed() {
    let mut while_ast = if_assignment_call_fixture("bad_if_assign_call_while", "!=");
    let function =
        if_assignment_call_function_mut(&mut while_ast, "bad_if_assign_call_while");
    let condition = function["inner"][1]["inner"][0]["inner"][0].clone();
    function["inner"][1]["inner"][0] = serde_json::json!({
        "kind": "WhileStmt",
        "inner": [condition, { "kind": "CompoundStmt", "inner": [] }]
    });

    let mut right_assignment_ast =
        if_assignment_call_fixture("bad_if_assign_call_on_right", "!=");
    let function = if_assignment_call_function_mut(
        &mut right_assignment_ast,
        "bad_if_assign_call_on_right",
    );
    function["inner"][1]["inner"][0]["inner"][0]["inner"]
        .as_array_mut()
        .expect("comparison operands")
        .swap(0, 1);

    let mut second_call_ast =
        if_assignment_call_fixture("bad_if_assign_call_second_call", "!=");
    let function = if_assignment_call_function_mut(
        &mut second_call_ast,
        "bad_if_assign_call_second_call",
    );
    let call = &mut function["inner"][1]["inner"][0]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][1];
    let second_call = call.clone();
    call["inner"]
        .as_array_mut()
        .expect("direct call operands")
        .push(second_call);

    let mut logical_and_ast =
        if_assignment_call_fixture("bad_if_assign_call_logical_and", "!=");
    let function = if_assignment_call_function_mut(
        &mut logical_and_ast,
        "bad_if_assign_call_logical_and",
    );
    let assignment_comparison = function["inner"][1]["inner"][0]["inner"][0].clone();
    function["inner"][1]["inner"][0]["inner"][0] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "&&",
        "type": { "qualType": "int" },
        "inner": [
            assignment_comparison,
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
        ]
    });

    let mut deref_ast = if_assignment_call_fixture("bad_if_assign_call_deref", "!=");
    let function = if_assignment_call_function_mut(&mut deref_ast, "bad_if_assign_call_deref");
    function["inner"][1]["inner"][0]["inner"][0]["inner"][0]["inner"][0]
        ["inner"][0] =
        serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "*",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int *" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "slot"
                            }
                        }
                    ]
                }
            ]
        });

    let mut volatile_ast =
        if_assignment_call_fixture("bad_if_assign_call_volatile", "!=");
    let function =
        if_assignment_call_function_mut(&mut volatile_ast, "bad_if_assign_call_volatile");
    function["inner"][0]["type"]["qualType"] = serde_json::json!("volatile int");
    function["inner"][1]["inner"][0]["inner"][0]["inner"][0]["inner"][0]
        ["inner"][0]["type"]["qualType"] = serde_json::json!("volatile int");

    for (function_name, ast, expected_reason) in [
        (
            "bad_if_assign_call_while",
            while_ast,
            "opcode = is outside the current skeleton",
        ),
        (
            "bad_if_assign_call_on_right",
            right_assignment_ast,
            "opcode = is outside the current skeleton",
        ),
        (
            "bad_if_assign_call_second_call",
            second_call_ast,
            "second call",
        ),
        (
            "bad_if_assign_call_logical_and",
            logical_and_ast,
            "opcode = is outside the current skeleton",
        ),
        (
            "bad_if_assign_call_deref",
            deref_ast,
            "direct non-volatile, non-atomic fixed-width integer DeclRef",
        ),
        (
            "bad_if_assign_call_volatile",
            volatile_ast,
            "volatile",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("out-of-bound if assignment-call shape must fail closed");
        assert!(
            error.message.contains(expected_reason),
            "{function_name}: expected {expected_reason:?}, got {error:?}"
        );
    }
}
