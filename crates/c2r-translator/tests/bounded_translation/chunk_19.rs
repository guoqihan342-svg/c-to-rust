#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn if_assignment_call_fixture(function_name: &str, opcode: &str) -> Value {
    let mut ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == "bad_if_tail_assign_shape")
        .expect("if assignment-call fixture function");
    function["name"] = serde_json::json!(function_name);
    function["inner"][1]["inner"][0]["inner"][0]["opcode"] =
        serde_json::json!(opcode);
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn if_assignment_call_function_mut<'a>(
    ast: &'a mut Value,
    function_name: &str,
) -> &'a mut Value {
    ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed if assignment-call fixture function")
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn clang_int_return(value: i32) -> Value {
    serde_json::json!({
        "kind": "ReturnStmt",
        "inner": [
            {
                "kind": "IntegerLiteral",
                "value": value.to_string(),
                "type": { "qualType": "int" }
            }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn clang_int_read(name: &str) -> Value {
    serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "DeclRefExpr",
                "type": { "qualType": "int" },
                "referencedDecl": {
                    "kind": "ParmVarDecl",
                    "name": name
                }
            }
        ]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn returning_if_assignment_call_fixture(function_name: &str, opcode: &str) -> Value {
    let mut ast = if_assignment_call_fixture(function_name, opcode);
    let function = if_assignment_call_function_mut(&mut ast, function_name);
    let condition = function["inner"][1]["inner"][0]["inner"][0].clone();
    function["type"]["qualType"] = serde_json::json!("int (int)");
    function["inner"][1]["inner"] = serde_json::json!([
        {
            "kind": "IfStmt",
            "inner": [condition, clang_int_return(111)]
        },
        clang_int_return(222)
    ]);
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn rewrite_fixture_int_types_to_u32(value: &mut Value) {
    match value {
        Value::Array(values) => {
            for value in values {
                rewrite_fixture_int_types_to_u32(value);
            }
        }
        Value::Object(fields) => {
            if let Some(Value::String(qual_type)) = fields.get_mut("qualType") {
                *qual_type = match qual_type.as_str() {
                    "int" => "unsigned int".to_string(),
                    "void (int)" => "void (unsigned int)".to_string(),
                    "int (int)" => "unsigned int (unsigned int)".to_string(),
                    "int (*)(int)" => "unsigned int (*)(unsigned int)".to_string(),
                    other => other.to_string(),
                };
            }
            for value in fields.values_mut() {
                rewrite_fixture_int_types_to_u32(value);
            }
        }
        _ => {}
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_comparisons_emit_in_order_and_run() {
    let cases = [
        ("eq", "==", "==", IrBinOp::Eq, 0, 1),
        ("neq", "!=", "!=", IrBinOp::Neq, 1, 0),
        ("lt", "<", "<", IrBinOp::Lt, -1, 0),
        ("le", "<=", "<=", IrBinOp::Le, 0, 1),
        ("gt", ">", ">", IrBinOp::Gt, 1, 0),
        ("ge", ">=", ">=", IrBinOp::Ge, 0, -1),
    ];
    let mut runtime_rust =
        String::from("fn step_value(value: i32) -> i32 { value }\n");
    let mut runtime_assertions = String::new();

    for (suffix, c_op, rust_op, expected_op, true_input, false_input) in cases {
        let function_name = format!("if_assign_call_{suffix}");
        let ast = returning_if_assignment_call_fixture(&function_name, c_op);
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, &function_name)
            .unwrap_or_else(|error| panic!("lower {c_op} assignment-call comparison: {error:?}"));
        let [assignment, conditional, trailing_return] = lowered.function_ir.body.as_slice()
        else {
            panic!(
                "{c_op}: expected Assign + If + Return, got {:?}",
                lowered.function_ir.body
            );
        };
        assert!(matches!(
            assignment,
            IrStmt::Assign { target, value, .. }
                if matches!(target, IrExpr::Var { name, .. } if name == "value")
                    && matches!(value, IrExpr::Call { callee, .. } if callee == "step_value")
        ));
        let IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } = conditional
        else {
            panic!("{c_op}: expected pure If after assignment, got {conditional:?}");
        };
        let IrExpr::Binary {
            op,
            lhs,
            rhs,
            ..
        } = condition
        else {
            panic!("{c_op}: expected binary comparison, got {condition:?}");
        };
        assert_eq!(op, &expected_op, "{c_op}");
        assert!(matches!(
            lhs.as_ref(),
            IrExpr::LValueToRValue { expr, .. }
                if matches!(expr.as_ref(), IrExpr::Var { name, .. } if name == "value")
        ));
        assert!(matches!(
            rhs.as_ref(),
            IrExpr::LitInt { value: 0, .. }
        ));
        assert!(matches!(then_body.as_slice(), [IrStmt::Return { .. }]));
        assert!(else_body.is_empty());
        assert!(matches!(trailing_return, IrStmt::Return { .. }));

        let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .unwrap_or_else(|error| panic!("emit {c_op} assignment-call comparison: {error:?}"));
        assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
        let rust = &emitted.rust;
        let assignment_offset = rust
            .find("value = step_value(value);")
            .unwrap_or_else(|| panic!("{c_op}: missing emitted assignment: {rust}"));
        let pure_if = format!("if (value {rust_op} 0i32)");
        let if_offset = rust
            .find(&pure_if)
            .unwrap_or_else(|| panic!("{c_op}: missing pure comparison {pure_if:?}: {rust}"));
        assert!(assignment_offset < if_offset, "{c_op}: {rust}");
        assert_eq!(rust.matches("step_value(").count(), 1, "{c_op}: {rust}");

        runtime_rust.push_str(rust);
        runtime_rust.push('\n');
        runtime_assertions.push_str(&format!(
            "    assert_eq!({function_name}({true_input}), 111);\n    assert_eq!({function_name}({false_input}), 222);\n"
        ));
    }

    assert_rust_snippet_runs(
        "typed-ir-clang-ast-if-assignment-call-comparisons",
        &runtime_rust,
        &runtime_assertions,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_accepts_u32_failed_address_shape() {
    let function_name = "if_assign_call_u32_failed_addr";
    let mut ast = if_assignment_call_fixture(function_name, "==");
    let function = if_assignment_call_function_mut(&mut ast, function_name);
    rewrite_fixture_int_types_to_u32(function);
    let condition = &mut function["inner"][1]["inner"][0]["inner"][0];
    condition["type"]["qualType"] = serde_json::json!("int");
    condition["inner"][1]["value"] = serde_json::json!("4294967295");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower uint32_t FAILED_ADDR assignment-call comparison");
    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [
            IrStmt::Assign {
                target: IrExpr::Var { ty, .. },
                value: IrExpr::Call { .. },
                ..
            },
            IrStmt::If {
                condition: IrExpr::Binary {
                    op: IrBinOp::Eq,
                    rhs,
                    ..
                },
                ..
            }
        ] if matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 32
            }
        ) && matches!(
            rhs.as_ref(),
            IrExpr::LitInt { value: 4_294_967_295, .. }
        )
    ));
    let rust = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit uint32_t FAILED_ADDR assignment-call comparison")
        .rust;
    assert!(rust.contains("value = step_value(value);"), "{rust}");
    assert!(rust.contains("if (value == 4294967295u32)"), "{rust}");
}

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
