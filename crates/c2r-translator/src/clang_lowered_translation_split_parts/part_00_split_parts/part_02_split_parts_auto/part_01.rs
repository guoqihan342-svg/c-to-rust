
/// Mirrors an already-emitted typed IR function into translator evidence.
///
/// Rust code has already been produced by `typed_ir` before this runs. The job
/// here is to describe the semantic route that was accepted: type mappings,
/// call expressions, coarse CFG shape, pointer boundaries, and rule ids.
fn record_clang_lowered_ir_evidence(
    spec: &SliceSpec,
    function: &typed_ir::IrFunction,
    result: &mut TranslationResult,
) {
    record_ir_type_mapping("return", &function.return_type, &spec.build_profile, result);
    for param in &function.params {
        let rust_type_override = ir_param_type_map_rust_override(function, param);
        record_ir_type_mapping_with_rust_type_override(
            &param.name,
            &param.ty,
            &spec.build_profile,
            rust_type_override,
            result,
        );
    }
    record_ir_decl_type_mappings(&function.body, &spec.build_profile, result);
    record_ir_call_expression_evidence(&function.body, result);
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks: vec![CfgBlock {
            id: "entry".to_string(),
            statements: function.body.iter().map(ir_statement_label).collect(),
            statement_kinds: ir_statement_kind_labels(&function.body),
            lvalue_kinds: Vec::new(),
            terminator: if function
                .body
                .iter()
                .any(|stmt| matches!(stmt, typed_ir::IrStmt::Return { .. }))
            {
                "return".to_string()
            } else {
                "fallthrough".to_string()
            },
            edges: ir_cfg_edges(&function.body),
        }],
        unsupported_control_flow: Vec::new(),
        structured_control_flow: None,
    });
    emit_ir_pointer_graph(function, result);
    push_rule_once(
        &mut result.plan.translation_rule_ids,
        "clang-lowered-typed-ir",
    );
    if ir_has_byte_cursor_read(function, "buf") {
        for rule in [
            "const-void-byte-slice",
            "byte-cursor-post-increment-read",
            "byte-cursor-loop",
            "structured-while",
            "structured-return-expression",
        ] {
            push_rule_once(&mut result.plan.translation_rule_ids, rule);
        }
    }
}

fn record_ir_decl_type_mappings(
    statements: &[typed_ir::IrStmt],
    profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl { name, ty, .. } => {
                record_ir_type_mapping(name, ty, profile, result);
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                record_ir_decl_type_mappings(then_body, profile, result);
                record_ir_decl_type_mappings(else_body, profile, result);
            }
            typed_ir::IrStmt::While { body, .. } => {
                record_ir_decl_type_mappings(body, profile, result);
            }
            typed_ir::IrStmt::DoWhile { body, .. } => {
                record_ir_decl_type_mappings(body, profile, result);
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                record_ir_decl_type_mappings(init, profile, result);
                record_ir_decl_type_mappings(body, profile, result);
                if let Some(step) = step.as_deref() {
                    record_ir_decl_type_mappings(std::slice::from_ref(step), profile, result);
                }
            }
            _ => {}
        }
    }
}

/// Records direct-call evidence across all statement positions in typed IR.
///
/// The traversal keeps statement context labels because the validation reports
/// need to distinguish calls in initializers, assignments, loop conditions, and
/// returns. It recurses through nested control flow without changing the IR.
fn record_ir_call_expression_evidence(
    statements: &[typed_ir::IrStmt],
    result: &mut TranslationResult,
) {
    for statement in statements {
        match statement {
            typed_ir::IrStmt::Decl {
                init: Some(init), ..
            } => {
                record_ir_call_expression_evidence_for_expr(init, "declaration_initializer", result)
            }
            typed_ir::IrStmt::Decl { init: None, .. } => {}
            typed_ir::IrStmt::Assign { value, .. } => {
                record_ir_call_expression_evidence_for_expr(value, "assignment", result);
            }
            typed_ir::IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                record_ir_call_expression_evidence(then_body, result);
                record_ir_call_expression_evidence(else_body, result);
            }
            typed_ir::IrStmt::While { body, .. } => {
                record_ir_call_expression_evidence(body, result);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                record_ir_call_expression_evidence(body, result);
                record_ir_call_expression_evidence_for_expr(
                    condition,
                    "do_while_condition",
                    result,
                );
            }
            typed_ir::IrStmt::For {
                init, step, body, ..
            } => {
                record_ir_call_expression_evidence(init, result);
                record_ir_call_expression_evidence(body, result);
                if let Some(step) = step.as_deref() {
                    record_ir_call_expression_evidence(std::slice::from_ref(step), result);
                }
            }
            typed_ir::IrStmt::Return {
                value: Some(value), ..
            } => record_ir_call_expression_evidence_for_expr(value, "return", result),
            typed_ir::IrStmt::Return { value: None, .. } => {}
            typed_ir::IrStmt::Break { .. } | typed_ir::IrStmt::Continue { .. } => {}
            typed_ir::IrStmt::Expr { expr, .. } => {
                record_ir_call_expression_evidence_for_expr(expr, "expression", result);
            }
            typed_ir::IrStmt::RecordMemset { .. } => {}
            typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

fn record_ir_call_expression_evidence_for_expr(
    expr: &typed_ir::IrExpr,
    statement_context: &str,
    result: &mut TranslationResult,
) {
    match expr {
        typed_ir::IrExpr::Call { callee, args, .. } => {
            let arguments = args.iter().map(ir_expr_source_text).collect::<Vec<_>>();
            let call = CallExpressionEvidence {
                callee: callee.clone(),
                source_expression: format!("{callee}({})", arguments.join(", ")),
                arguments,
                statement_context: statement_context.to_string(),
            };
            result.plan.call_expressions.push(call);
            push_rule_once(
                &mut result.plan.translation_rule_ids,
                "bounded-call-expression",
            );
            for arg in args {
                record_ir_call_expression_evidence_for_expr(arg, statement_context, result);
            }
        }
        typed_ir::IrExpr::Binary { lhs, rhs, .. } => {
            record_ir_call_expression_evidence_for_expr(lhs, statement_context, result);
            record_ir_call_expression_evidence_for_expr(rhs, statement_context, result);
        }
        typed_ir::IrExpr::Unary { operand, .. } => {
            record_ir_call_expression_evidence_for_expr(operand, statement_context, result);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            record_ir_call_expression_evidence_for_expr(condition, statement_context, result);
            record_ir_call_expression_evidence_for_expr(then_expr, statement_context, result);
            record_ir_call_expression_evidence_for_expr(else_expr, statement_context, result);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            record_ir_call_expression_evidence_for_expr(expr, statement_context, result);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            record_ir_call_expression_evidence_for_expr(base, statement_context, result);
            record_ir_call_expression_evidence_for_expr(index, statement_context, result);
        }
        typed_ir::IrExpr::Member { base, .. } => {
            record_ir_call_expression_evidence_for_expr(base, statement_context, result);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                record_ir_call_expression_evidence_for_expr(element, statement_context, result);
            }
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            record_ir_call_expression_evidence_for_expr(target, statement_context, result);
        }
        typed_ir::IrExpr::Deref { ptr, .. } => {
            record_ir_call_expression_evidence_for_expr(ptr, statement_context, result);
        }
        typed_ir::IrExpr::AddrOf { operand, .. }
        | typed_ir::IrExpr::MutableVoidPointerAddress { operand, .. } => {
            record_ir_call_expression_evidence_for_expr(operand, statement_context, result);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}
