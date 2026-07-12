#[cfg(feature = "typed-ir")]
fn stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("DeclStmt") => decl_stmt_skeleton_from_ast(stmt),
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            assign_stmt_skeleton_from_ast(stmt)
        }
        Some("CompoundAssignOperator") => compound_assign_stmt_skeleton_from_ast(stmt),
        Some("IfStmt") => if_stmt_skeleton_from_ast(stmt),
        Some("WhileStmt") => while_stmt_skeleton_from_ast(stmt),
        Some("DoStmt") => do_stmt_skeleton_from_ast(stmt),
        Some("ForStmt") => for_stmt_skeleton_from_ast(stmt),
        Some("UnaryOperator") => inc_dec_stmt_skeleton_from_ast(stmt, "statement"),
        Some("CallExpr") => Ok(ClangStmtSkeleton::Expr {
            expr: call_stmt_expr_skeleton_from_ast(stmt)?,
        }),
        Some("ReturnStmt") => {
            let value = inner(stmt)
                .first()
                .map(value_expr_skeleton_from_ast)
                .transpose()?;
            Ok(ClangStmtSkeleton::Return { value })
        }
        Some("BreakStmt") => Ok(ClangStmtSkeleton::Break),
        Some("ContinueStmt") => Ok(ClangStmtSkeleton::Continue),
        Some("GotoStmt" | "SwitchStmt" | "LabelStmt" | "CaseStmt" | "DefaultStmt") => {
            Ok(ClangStmtSkeleton::Unsupported {
                reason: unsupported_control_flow_stmt_reason(stmt),
            })
        }
        Some(kind) => Ok(ClangStmtSkeleton::Unsupported {
            reason: unsupported_stmt_reason(stmt, kind),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_clang_stmt".to_string(),
            message: "clang statement node is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn for_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [init, condition_var, condition, step, body] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt must have init, condition variable, condition, step, and body slots"
                .to_string(),
        });
    };
    if !is_empty_ast_slot(condition_var) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt condition variable is outside the current clang lowering skeleton"
                .to_string(),
        });
    }
    let init = if is_empty_ast_slot(init) {
        Vec::new()
    } else {
        for_init_stmt_skeletons_from_ast(init)?
    };
    if is_empty_ast_slot(condition) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt without condition is outside the current clang lowering skeleton"
                .to_string(),
        });
    }
    let step = if is_empty_ast_slot(step) {
        None
    } else {
        Some(Box::new(for_step_stmt_skeleton_from_ast(step)?))
    };
    Ok(ClangStmtSkeleton::For {
        init,
        condition: Some(condition_expr_skeleton_from_ast(condition)?),
        step,
        body: stmt_body_skeleton_from_ast(body)?,
    })
}

#[cfg(feature = "typed-ir")]
fn is_empty_ast_slot(value: &Value) -> bool {
    value.as_object().is_some_and(|object| object.is_empty())
}

#[cfg(feature = "typed-ir")]
fn for_init_stmt_skeletons_from_ast(
    stmt: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("DeclStmt") => body_stmt_skeletons_from_ast(stmt),
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some(",") => {
            for_init_comma_chain_stmt_skeletons_from_ast(stmt)
        }
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            Ok(vec![assign_stmt_skeleton_from_ast(stmt)?])
        }
        Some(kind) => Ok(vec![ClangStmtSkeleton::Unsupported {
            reason: format!("ForStmt init {kind} is outside the current clang lowering skeleton"),
        }]),
        None => Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt init slot is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn for_init_comma_chain_stmt_skeletons_from_ast(
    stmt: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(stmt, "kind").as_deref() == Some("BinaryOperator")
        && string_field(stmt, "opcode").as_deref() == Some(",")
    {
        let children = inner(stmt);
        let [lhs, rhs] = children else {
            return Err(ClangFrontendError {
                kind: "invalid_for_stmt".to_string(),
                message: "ForStmt init comma BinaryOperator must have two operands".to_string(),
            });
        };
        let mut statements = for_init_comma_chain_stmt_skeletons_from_ast(lhs)?;
        statements.extend(for_init_comma_chain_stmt_skeletons_from_ast(rhs)?);
        return Ok(statements);
    }

    Ok(vec![for_init_comma_assignment_leaf_skeleton_from_ast(
        stmt,
    )?])
}

#[cfg(feature = "typed-ir")]
fn for_init_comma_assignment_leaf_skeleton_from_ast(
    stmt: &Value,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    if string_field(stmt, "kind").as_deref() != Some("BinaryOperator")
        || string_field(stmt, "opcode").as_deref() != Some("=")
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt init comma-chain leaf must be a direct integer scalar assignment"
                .to_string(),
        });
    }

    let assignment = assign_stmt_skeleton_from_ast(stmt)?;
    let ClangStmtSkeleton::Assign { target, value } = &assignment else {
        unreachable!("assignment lowering must produce an assignment skeleton");
    };
    if let Some(reason) = for_init_comma_assignment_target_rejection_reason(target) {
        return Ok(ClangStmtSkeleton::Unsupported { reason });
    }
    if let Some(reason) = for_init_comma_assignment_rhs_rejection_reason(value) {
        return Ok(ClangStmtSkeleton::Unsupported { reason });
    }
    Ok(assignment)
}

#[cfg(feature = "typed-ir")]
fn for_init_comma_assignment_target_rejection_reason(
    target: &ClangExprSkeleton,
) -> Option<String> {
    match target {
        ClangExprSkeleton::DeclRef { ty, .. }
            if matches!(&ty.kind, ClangTypeKind::Integer { .. })
                && !clang_type_is_volatile(ty) =>
        {
            None
        }
        ClangExprSkeleton::DeclRef { ty, .. } if clang_type_is_volatile(ty) => Some(format!(
            "ForStmt init comma-chain assignment target cannot be volatile: {}",
            ty.spelled
        )),
        ClangExprSkeleton::DeclRef { ty, .. } => Some(format!(
            "ForStmt init comma-chain assignment target must be an integer scalar, got {}",
            ty.spelled
        )),
        _ => Some(
            "ForStmt init comma-chain assignment target must be a direct integer scalar DeclRef"
                .to_string(),
        ),
    }
}
