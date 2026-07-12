#[cfg(feature = "clang-lowering-report")]
fn typed_ir_candidate_evidence(
    function_ir: Option<&typed_ir::IrFunction>,
    globals: &[typed_ir::IrGlobal],
    emit_policy: typed_ir::EmitPolicy,
) -> serde_json::Value {
    let readonly_globals = globals
        .iter()
        .map(readonly_global_summary)
        .collect::<Vec<_>>();
    let Some(function_ir) = function_ir else {
        return json!({
            "status": "not_available",
            "candidate_route": null,
            "readonly_globals": readonly_globals,
            "runtime_preconditions": [],
            "rust_draft_generated": false,
            "semantic_pass": false,
            "reason": "function_ir_missing",
        });
    };

    match typed_ir::emit_rust_from_ir_with_globals_and_policy(function_ir, globals, emit_policy) {
        Ok(emitted) => json!({
            "status": "generated",
            "candidate_route": emitted.route,
            "readonly_globals": readonly_globals,
            "runtime_preconditions": runtime_precondition_summary(function_ir),
            "rust_draft_generated": true,
            "semantic_pass": false,
        }),
        Err(error) => json!({
            "status": "unsupported",
            "candidate_route": error.route,
            "readonly_globals": readonly_globals,
            "runtime_preconditions": [],
            "rust_draft_generated": false,
            "semantic_pass": false,
            "unsupported_reason": error.reason,
        }),
    }
}

#[cfg(feature = "clang-lowering-report")]
use crate::clang_lowered_translation::emit_policy_from_spec;

#[cfg(feature = "clang-lowering-report")]
fn runtime_precondition_summary(function_ir: &typed_ir::IrFunction) -> Vec<serde_json::Value> {
    let mut preconditions = Vec::new();
    collect_stmt_runtime_preconditions(&function_ir.body, &mut preconditions);
    preconditions
}

#[cfg(feature = "clang-lowering-report")]
fn collect_stmt_runtime_preconditions(
    stmts: &[typed_ir::IrStmt],
    preconditions: &mut Vec<serde_json::Value>,
) {
    for stmt in stmts {
        match stmt {
            typed_ir::IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_expr_runtime_preconditions(init, preconditions);
                }
            }
            typed_ir::IrStmt::Assign { target, value, .. } => {
                collect_expr_runtime_preconditions(target, preconditions);
                collect_expr_runtime_preconditions(value, preconditions);
            }
            typed_ir::IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_expr_runtime_preconditions(condition, preconditions);
                collect_stmt_runtime_preconditions(then_body, preconditions);
                collect_stmt_runtime_preconditions(else_body, preconditions);
            }
            typed_ir::IrStmt::While {
                condition, body, ..
            } => {
                collect_expr_runtime_preconditions(condition, preconditions);
                collect_stmt_runtime_preconditions(body, preconditions);
            }
            typed_ir::IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_stmt_runtime_preconditions(body, preconditions);
                collect_expr_runtime_preconditions(condition, preconditions);
            }
            typed_ir::IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_stmt_runtime_preconditions(init, preconditions);
                if let Some(condition) = condition {
                    collect_expr_runtime_preconditions(condition, preconditions);
                }
                if let Some(step) = step {
                    collect_stmt_runtime_preconditions(std::slice::from_ref(step), preconditions);
                }
                collect_stmt_runtime_preconditions(body, preconditions);
            }
            typed_ir::IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_expr_runtime_preconditions(value, preconditions);
                }
            }
            typed_ir::IrStmt::Expr { expr, .. } => {
                collect_expr_runtime_preconditions(expr, preconditions);
            }
            typed_ir::IrStmt::RecordMemset { destination, .. } => {
                collect_expr_runtime_preconditions(destination, preconditions);
            }
            typed_ir::IrStmt::Break { .. }
            | typed_ir::IrStmt::Continue { .. }
            | typed_ir::IrStmt::Unsupported { .. } => {}
        }
    }
}

#[cfg(feature = "clang-lowering-report")]
fn collect_expr_runtime_preconditions(
    expr: &typed_ir::IrExpr,
    preconditions: &mut Vec<serde_json::Value>,
) {
    match expr {
        typed_ir::IrExpr::Binary {
            op,
            lhs,
            rhs,
            ty,
            source_span,
        } => {
            collect_expr_runtime_preconditions(lhs, preconditions);
            collect_expr_runtime_preconditions(rhs, preconditions);
            collect_binary_runtime_preconditions(op, ty, source_span, preconditions);
        }
        typed_ir::IrExpr::Unary {
            op,
            operand,
            ty,
            source_span,
        } => {
            collect_expr_runtime_preconditions(operand, preconditions);
            collect_unary_runtime_preconditions(op, ty, source_span, preconditions);
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_expr_runtime_preconditions(condition, preconditions);
            collect_expr_runtime_preconditions(then_expr, preconditions);
            collect_expr_runtime_preconditions(else_expr, preconditions);
        }
        typed_ir::IrExpr::Cast { expr, .. } => {
            collect_expr_runtime_preconditions(expr, preconditions);
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => {
            collect_expr_runtime_preconditions(expr, preconditions);
        }
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            collect_expr_runtime_preconditions(expr, preconditions);
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            collect_expr_runtime_preconditions(expr, preconditions);
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            collect_expr_runtime_preconditions(base, preconditions);
            collect_expr_runtime_preconditions(index, preconditions);
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_expr_runtime_preconditions(element, preconditions);
            }
        }
        typed_ir::IrExpr::Call { args, .. } => {
            for arg in args {
                collect_expr_runtime_preconditions(arg, preconditions);
            }
        }
        typed_ir::IrExpr::Member { base, .. } => {
            collect_expr_runtime_preconditions(base, preconditions);
        }
        typed_ir::IrExpr::IncDec { target, .. } => {
            collect_expr_runtime_preconditions(target, preconditions);
        }
        typed_ir::IrExpr::Deref { ptr, .. } => {
            collect_expr_runtime_preconditions(ptr, preconditions);
        }
        typed_ir::IrExpr::AddrOf { operand, .. }
        | typed_ir::IrExpr::MutableVoidPointerAddress { operand, .. } => {
            collect_expr_runtime_preconditions(operand, preconditions);
        }
        typed_ir::IrExpr::LitInt { .. }
        | typed_ir::IrExpr::NullPtr { .. }
        | typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Unsupported { .. } => {}
    }
}
