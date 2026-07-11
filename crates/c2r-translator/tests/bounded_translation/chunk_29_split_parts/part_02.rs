#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn const_member_reborrow_fixture(function_name: &str) -> Value {
    let mut ast = run_once_reborrow_fixture(function_name);
    let function = interior_reborrow_function_mut(&mut ast, function_name);
    let body = interior_reborrow_body_mut(function);
    body[2]["inner"][1]["inner"][2]["inner"][1]["inner"][0]["type"]["qualType"] =
        serde_json::json!("const unsigned int");
    ast
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn const_member_reborrow_source_type_mut(function: &mut IrFunction) -> &mut IrType {
    let IrStmt::While { body, .. } = &mut function.body[2] else {
        panic!("run-once carrier while");
    };
    let IrStmt::Assign { value, .. } = &mut body[2] else {
        panic!("run-once carrier owner add");
    };
    let IrExpr::Binary { rhs, .. } = value else {
        panic!("run-once carrier binary add");
    };
    let IrExpr::LValueToRValue { expr, .. } = rhs.as_mut() else {
        panic!("run-once carrier source read");
    };
    let IrExpr::Member { ty, .. } = expr.as_mut() else {
        panic!("run-once carrier source member");
    };
    ty
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_const_record_member_top_level_const_is_exactly_normalized() {
    let function_name = "apply_const_member_step_once";
    let ast = const_member_reborrow_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower const-member fixture without clang");
    let source_ty = match &lowered.function_ir.body[2] {
        IrStmt::While { body, .. } => match &body[2] {
            IrStmt::Assign {
                value: IrExpr::Binary { rhs, .. },
                ..
            } => match rhs.as_ref() {
                IrExpr::LValueToRValue { expr, .. } => match expr.as_ref() {
                    IrExpr::Member { ty, .. } => ty,
                    _ => panic!("source member"),
                },
                _ => panic!("source read"),
            },
            _ => panic!("owner add"),
        },
        _ => panic!("run-once while"),
    };
    assert!(source_ty.is_const);
    assert_eq!(source_ty.canonical, "unsigned int");
    emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        run_once_reborrow_policy(),
    )
    .expect("emit exact top-level const member projection");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_const_record_member_rejects_qualifier_and_type_drift() {
    for case in ["qualifier", "canonical", "kind", "width"] {
        let function_name = format!("reject_const_member_{case}");
        let ast = const_member_reborrow_fixture(&function_name);
        let mut lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, &function_name)
            .expect("lower const-member refusal fixture");
        let ty = const_member_reborrow_source_type_mut(&mut lowered.function_ir);
        match case {
            "qualifier" => ty.spelled = "const volatile unsigned int".to_string(),
            "canonical" => ty.canonical = "unsigned long".to_string(),
            "kind" => {
                ty.kind = IrTypeKind::Integer {
                    signed: true,
                    width: 32,
                }
            }
            "width" => ty.width_bits = Some(64),
            _ => unreachable!(),
        }
        let error = emit_rust_from_ir_with_globals_and_policy(
            &lowered.function_ir,
            &lowered.globals,
            run_once_reborrow_policy(),
        )
        .expect_err("const member drift must fail closed");
        assert!(error.reason.contains("does not match declared type"), "{case}: {error:?}");
    }
}
