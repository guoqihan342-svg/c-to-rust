#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn if_assignment_call_record_pointer_member_fixture(
    function_name: &str,
    opcode: &str,
) -> Value {
    let comparison_inner = serde_json::json!({
        "kind": "IfStmt",
        "inner": [
            {
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "ParenExpr",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            {
                                "kind": "BinaryOperator",
                                "opcode": "=",
                                "type": { "qualType": "unsigned int" },
                                "inner": [
                                    {
                                        "kind": "MemberExpr",
                                        "name": "threshold",
                                        "isArrow": true,
                                        "type": { "qualType": "unsigned int" },
                                        "inner": [
                                            {
                                                "kind": "DeclRefExpr",
                                                "type": { "qualType": "struct Context *" },
                                                "referencedDecl": { "kind": "ParmVarDecl", "name": "ctx" }
                                            }
                                        ]
                                    },
                                    {
                                        "kind": "CallExpr",
                                        "type": { "qualType": "unsigned int" },
                                        "inner": [
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "FunctionToPointerDecay",
                                                "type": { "qualType": "unsigned int (*)(struct Context *, unsigned int)" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "unsigned int (struct Context *, unsigned int)" },
                                                        "referencedDecl": { "kind": "FunctionDecl", "name": "fetch_value" }
                                                    }
                                                ]
                                            },
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "LValueToRValue",
                                                "type": { "qualType": "struct Context *" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "struct Context *" },
                                                        "referencedDecl": { "kind": "ParmVarDecl", "name": "ctx" }
                                                    }
                                                ]
                                            },
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "LValueToRValue",
                                                "type": { "qualType": "unsigned int" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "unsigned int" },
                                                        "referencedDecl": { "kind": "ParmVarDecl", "name": "seed" }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "kind": "IntegerLiteral",
                        "value": "4294967295",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            { "kind": "CompoundStmt", "inner": [] }
        ]
    });
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
    function["type"]["qualType"] = serde_json::json!("void (struct Context *, unsigned int)");
    function["inner"] = serde_json::json!([
        {
            "kind": "ParmVarDecl",
            "name": "ctx",
            "type": { "qualType": "struct Context *" }
        },
        {
            "kind": "ParmVarDecl",
            "name": "seed",
            "type": { "qualType": "unsigned int" }
        },
        {
            "kind": "CompoundStmt",
            "inner": [comparison_inner]
        }
    ]);
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_accepts_and_runs() {
    let function_name = "if_assign_call_record_ptr_member";
    let ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower record-pointer member assignment-call comparison");
    let [assignment, _conditional] = lowered.function_ir.body.as_slice() else {
        panic!("expected Assign + If, got {:?}", lowered.function_ir.body);
    };
    assert!(matches!(
        assignment,
        IrStmt::Assign { target, value, .. }
            if matches!(target, IrExpr::Member { is_arrow: true, .. })
                && matches!(value, IrExpr::Call { callee, .. } if callee == "fetch_value")
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit record-pointer member assignment-call comparison");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    let rust = &emitted.rust;
    assert!(
        rust.contains("ctx.threshold = fetch_value(ctx, seed);"),
        "missing emitted assignment: {rust}"
    );
    assert!(
        rust.contains("if (ctx.threshold == 4294967295u32)"),
        "missing pure comparison: {rust}"
    );
    assert_eq!(rust.matches("fetch_value(").count(), 1, "{rust}");

    let runtime_rust = format!(
        "use std::sync::atomic::{{AtomicUsize, Ordering}};\n\
         static CALLS: AtomicUsize = AtomicUsize::new(0);\n\
         fn fetch_value(_ctx: &mut Context, seed: u32) -> u32 {{\
             CALLS.fetch_add(1, Ordering::SeqCst); seed.wrapping_add(1)\
         }}\n\
         {rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-if-assignment-call-record-ptr-member",
        &runtime_rust,
        r#"
    CALLS.store(0, Ordering::SeqCst);
    let mut ctx = Context { threshold: 0 };
    if_assign_call_record_ptr_member(&mut ctx, 99);
    assert_eq!(ctx.threshold, 100);
    assert_eq!(CALLS.load(Ordering::SeqCst), 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_nested_dot_hop() {
    let function_name = "bad_if_assign_call_nested_dot";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let target_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    target_member["isArrow"] = serde_json::json!(false);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("nested dot hop must fail closed at frontend");
    assert!(
        error
            .message
            .contains("direct mutable record-pointer arrow integer member"),
        "expected nested dot rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_readonly_root() {
    let function_name = "bad_if_assign_call_readonly_record_ptr";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let root_ref = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0]["inner"][0];
    root_ref["type"]["qualType"] = serde_json::json!("const struct Context *");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("readonly record pointer root must fail closed");
    assert!(
        error.message.contains("non-const mutable record pointer"),
        "expected readonly root rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_second_arrow_hop() {
    let function_name = "bad_if_assign_call_second_arrow";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let target_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    let inner = target_member.clone();
    target_member["name"] = serde_json::json!("outer_wrapper");
    target_member["isArrow"] = serde_json::json!(true);
    target_member["type"] = serde_json::json!({ "qualType": "unsigned int" });
    target_member["inner"] = serde_json::json!([inner]);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("second arrow hop must fail closed");
    assert!(
        error.message.contains("must not contain a second member hop"),
        "expected second arrow rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_effectful_base() {
    let function_name = "bad_if_assign_call_effectful_base";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let arrow_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    let call_expr = arrow_member["inner"][1].clone();
    let base_ref = arrow_member["inner"][0].clone();
    arrow_member["inner"] = serde_json::json!([
        {
            "kind": "BinaryOperator",
            "opcode": ",",
            "type": { "qualType": "struct Context *" },
            "inner": [call_expr, base_ref]
        }
    ]);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("effectful base must fail closed");
    assert!(
        error.message.contains("root must be a direct non-null"),
        "expected effectful base rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_volatile_leaf() {
    let function_name = "bad_if_assign_call_volatile_leaf";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let outer_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    outer_member["type"]["qualType"] = serde_json::json!("volatile unsigned int");

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("volatile leaf must fail closed");
    assert!(
        error.message.contains("volatile"),
        "expected volatile rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_by_value_local_member() {
    let function_name = "bad_if_assign_call_local_member";
    let inner = serde_json::json!({
        "kind": "IfStmt",
        "inner": [
            {
                "kind": "BinaryOperator",
                "opcode": "==",
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "ParenExpr",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            {
                                "kind": "BinaryOperator",
                                "opcode": "=",
                                "type": { "qualType": "unsigned int" },
                                "inner": [
                                    {
                                        "kind": "MemberExpr",
                                        "name": "counter",
                                        "isArrow": false,
                                        "type": { "qualType": "unsigned int" },
                                        "inner": [
                                            {
                                                "kind": "MemberExpr",
                                                "name": "inner",
                                                "isArrow": false,
                                                "type": { "qualType": "struct Inner" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "struct Local" },
                                                        "referencedDecl": { "kind": "ParmVarDecl", "name": "obj" }
                                                    }
                                                ]
                                            }
                                        ]
                                    },
                                    {
                                        "kind": "CallExpr",
                                        "type": { "qualType": "unsigned int" },
                                        "inner": [
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "FunctionToPointerDecay",
                                                "type": { "qualType": "unsigned int (*)(struct Local)" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "unsigned int (struct Local)" },
                                                        "referencedDecl": { "kind": "FunctionDecl", "name": "fetch_count" }
                                                    }
                                                ]
                                            },
                                            {
                                                "kind": "ImplicitCastExpr",
                                                "castKind": "LValueToRValue",
                                                "type": { "qualType": "struct Local" },
                                                "inner": [
                                                    {
                                                        "kind": "DeclRefExpr",
                                                        "type": { "qualType": "struct Local" },
                                                        "referencedDecl": { "kind": "ParmVarDecl", "name": "obj" }
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "kind": "IntegerLiteral",
                        "value": "4294967295",
                        "type": { "qualType": "unsigned int" }
                    }
                ]
            },
            { "kind": "CompoundStmt", "inner": [] }
        ]
    });
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
    function["type"]["qualType"] = serde_json::json!("void (struct Local)");
    function["inner"] = serde_json::json!([
        {
            "kind": "ParmVarDecl",
            "name": "obj",
            "type": { "qualType": "struct Local" }
        },
        {
            "kind": "CompoundStmt",
            "inner": [inner]
        }
    ]);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("by-value local member must fail closed in IfCondition");
    assert!(
        error
            .message
            .contains("direct mutable record-pointer arrow integer member"),
        "expected local member rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_logical_and_in_if() {
    let function_name = "bad_if_assign_call_logical_and_record_ptr";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let assignment_comparison = function["inner"][2]["inner"][0]["inner"][0].clone();
    function["inner"][2]["inner"][0]["inner"][0] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "&&",
        "type": { "qualType": "int" },
        "inner": [
            assignment_comparison,
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
        ]
    });

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("logical and in if must fail closed");
    assert!(
        error.message.contains("opcode = is outside the current skeleton"),
        "expected logical-and rejection, got {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_member_rejects_second_call() {
    let function_name = "bad_if_assign_call_second_call_record_ptr";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let call = &mut function["inner"][2]["inner"][0]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][1];
    let second_call = call.clone();
    call["inner"]
        .as_array_mut()
        .expect("direct call operands")
        .push(second_call);

    let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect_err("second call must fail closed");
    assert!(
        error.message.contains("second call"),
        "expected second call rejection, got {error:?}"
    );
}
