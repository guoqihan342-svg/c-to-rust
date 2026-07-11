#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_reborrow_ir(function_name: &str) -> IrFunction {
    let ast = assignment_call_reborrow_fixture(function_name);
    lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower assignment-call refusal fixture")
        .function_ir
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_reborrow_emit_failure(function: &IrFunction, policy: EmitPolicy) -> String {
    emit_rust_from_ir_with_globals_and_policy(function, &[], policy)
        .expect_err("adjacent assignment-call reborrow drift must fail closed")
        .reason
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_loop_body_mut(function: &mut IrFunction) -> &mut Vec<IrStmt> {
    let IrStmt::While { body, .. } = &mut function.body[3] else {
        panic!("assignment-call run-once while");
    };
    body
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_args_mut(function: &mut IrFunction) -> &mut Vec<IrExpr> {
    let body = assignment_call_loop_body_mut(function);
    let IrStmt::Assign {
        value: IrExpr::Call { args, .. },
        ..
    } = &mut body[1]
    else {
        panic!("normalized assignment call");
    };
    args
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn assignment_call_branch_mut(function: &mut IrFunction) -> (&mut IrExpr, &mut Vec<IrStmt>, &mut Vec<IrStmt>) {
    let body = assignment_call_loop_body_mut(function);
    let IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    } = &mut body[2]
    else {
        panic!("normalized pure branch");
    };
    (condition, then_body, else_body)
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn assignment_call_reborrow_requires_exact_forward_noalias() {
    let function = assignment_call_reborrow_ir("reject_assignment_call_noalias");
    let missing = assignment_call_reborrow_emit_failure(&function, EmitPolicy::default());
    assert!(missing.contains("noalias"), "{missing}");

    let reversed = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "owner".to_string(),
            mutable_param: "source".to_string(),
        }],
        ..Default::default()
    };
    let reversed = assignment_call_reborrow_emit_failure(&function, reversed);
    assert!(reversed.contains("forward") && reversed.contains("noalias"), "{reversed}");
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn assignment_call_reborrow_rejects_alias_and_call_drift() {
    for case in [
        "alias_escape",
        "missing_alias_arg",
        "duplicate_alias_arg",
        "call_order",
        "call_return_type",
        "second_call",
        "duplicate_setup",
    ] {
        let mut function = assignment_call_reborrow_ir(&format!("reject_{case}"));
        match case {
            "alias_escape" => {
                let alias = assignment_call_args_mut(&mut function)[2].clone();
                function.body.insert(
                    4,
                    IrStmt::Expr {
                        expr: alias,
                        source_span: None,
                    },
                );
            }
            "missing_alias_arg" => {
                let args = assignment_call_args_mut(&mut function);
                args[2] = args[0].clone();
            }
            "duplicate_alias_arg" => {
                let args = assignment_call_args_mut(&mut function);
                args[1] = args[2].clone();
            }
            "call_order" => assignment_call_args_mut(&mut function).swap(0, 1),
            "call_return_type" => {
                let body = assignment_call_loop_body_mut(&mut function);
                let IrStmt::Assign {
                    value: IrExpr::Call { ty, .. },
                    ..
                } = &mut body[1]
                else {
                    unreachable!()
                };
                ty.kind = IrTypeKind::Integer {
                    signed: true,
                    width: 32,
                };
            }
            "second_call" => {
                let body = assignment_call_loop_body_mut(&mut function);
                body.insert(2, body[1].clone());
            }
            "duplicate_setup" => function.body.insert(2, function.body[1].clone()),
            _ => unreachable!(),
        }
        let reason = assignment_call_reborrow_emit_failure(
            &function,
            assignment_call_reborrow_policy(),
        );
        assert!(
            reason.contains("interior reborrow") || reason.contains("call"),
            "{case}: {reason}"
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn assignment_call_reborrow_rejects_branch_and_state_order_drift() {
    for case in [
        "comparison_path",
        "comparison_operator",
        "sentinel_type",
        "if_else",
        "extra_hit_stmt",
        "nested_continue",
        "continue_position",
        "hit_order",
        "miss_order",
    ] {
        let mut function = assignment_call_reborrow_ir(&format!("reject_{case}"));
        match case {
            "comparison_path" => {
                let (condition, _, _) = assignment_call_branch_mut(&mut function);
                let IrExpr::Binary { lhs, .. } = condition else {
                    unreachable!()
                };
                let lhs = match lhs.as_mut() {
                    IrExpr::LValueToRValue { expr, .. } => expr.as_mut(),
                    direct => direct,
                };
                let IrExpr::Member { field, .. } = lhs else {
                    unreachable!()
                };
                *field = "guard".to_string();
            }
            "comparison_operator" => {
                let (condition, _, _) = assignment_call_branch_mut(&mut function);
                let IrExpr::Binary { op, .. } = condition else {
                    unreachable!()
                };
                *op = IrBinOp::Neq;
            }
            "sentinel_type" => {
                let (condition, _, _) = assignment_call_branch_mut(&mut function);
                let IrExpr::Binary { rhs, .. } = condition else {
                    unreachable!()
                };
                let IrExpr::LitInt { ty, .. } = rhs.as_mut() else {
                    unreachable!()
                };
                ty.kind = IrTypeKind::Integer {
                    signed: true,
                    width: 32,
                };
            }
            "if_else" => {
                let miss = assignment_call_loop_body_mut(&mut function)[3].clone();
                assignment_call_branch_mut(&mut function).2.push(miss);
            }
            "extra_hit_stmt" => {
                let miss = assignment_call_loop_body_mut(&mut function)[3].clone();
                assignment_call_branch_mut(&mut function).1.push(miss);
            }
            "nested_continue" => {
                let condition = match &function.body[3] {
                    IrStmt::While { condition, .. } => condition.clone(),
                    _ => unreachable!(),
                };
                let (_, then_body, _) = assignment_call_branch_mut(&mut function);
                let continue_stmt = then_body[2].clone();
                then_body[2] = IrStmt::While {
                    condition,
                    body: vec![continue_stmt],
                    source_span: None,
                };
            }
            "continue_position" => assignment_call_branch_mut(&mut function).1.swap(1, 2),
            "hit_order" => assignment_call_branch_mut(&mut function).1.swap(0, 1),
            "miss_order" => assignment_call_loop_body_mut(&mut function).swap(2, 3),
            _ => unreachable!(),
        }
        let reason = assignment_call_reborrow_emit_failure(
            &function,
            assignment_call_reborrow_policy(),
        );
        assert!(reason.contains("interior reborrow"), "{case}: {reason}");
    }
}
