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
        "../../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
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
fn clang_ast_if_assignment_call_record_pointer_member_accepts_direct_lvalue_read_root() {
    let function_name = "if_assign_call_record_ptr_member_lvalue_read";
    let mut ast = if_assignment_call_record_pointer_member_fixture(function_name, "==");
    let function = ast["inner"]
        .as_array_mut()
        .expect("translation unit declarations")
        .iter_mut()
        .find(|decl| decl["name"] == function_name)
        .expect("renamed fixture function");
    let arrow_member = &mut function["inner"][2]["inner"][0]["inner"][0]
        ["inner"][0]["inner"][0]["inner"][0];
    let base_ref = arrow_member["inner"][0].clone();
    let base_type = base_ref["type"].clone();
    arrow_member["inner"][0] = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "LValueToRValue",
        "type": base_type,
        "inner": [base_ref]
    });

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower direct record-pointer lvalue read root");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit direct record-pointer lvalue read root");

    assert!(
        emitted
            .rust
            .contains("ctx.threshold = fetch_value(ctx, seed);"),
        "{}",
        emitted.rust
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_if_assignment_call_record_pointer_nested_dot_member_accepts_and_runs() {
    let function_name = "if_assign_call_record_ptr_nested_member";
    let ast = if_assignment_call_record_pointer_nested_member_fixture(function_name);

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower arrow-rooted nested dot assignment-call comparison");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit arrow-rooted nested dot assignment-call comparison");
    let rust = &emitted.rust;
    assert!(
        rust.contains("ctx.address.threshold = fetch_value(ctx, seed);"),
        "missing emitted nested assignment: {rust}"
    );
    assert!(
        rust.contains("if (ctx.address.threshold == 4294967295u32)"),
        "missing emitted nested comparison: {rust}"
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
        "typed-ir-clang-ast-if-assignment-call-record-ptr-nested-member",
        &runtime_rust,
        r#"
    CALLS.store(0, Ordering::SeqCst);
    let mut ctx = Context { address: Address { threshold: 0 } };
    if_assign_call_record_ptr_nested_member(&mut ctx, 99);
    assert_eq!(ctx.address.threshold, 100);
    assert_eq!(CALLS.load(Ordering::SeqCst), 1);
"#,
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
        error
            .message
            .contains("must not contain a second arrow or pointer member hop"),
        "expected second arrow rejection, got {error:?}"
    );
}
