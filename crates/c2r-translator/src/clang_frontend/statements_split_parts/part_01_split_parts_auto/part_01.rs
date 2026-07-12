
#[cfg(feature = "typed-ir")]
fn if_stmt_skeleton_from_parts(
    condition: ClangExprSkeleton,
    then_body: &Value,
    else_body: Option<&Value>,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let else_body = match else_body {
        Some(else_body) => stmt_body_skeleton_from_ast(else_body)?,
        None => Vec::new(),
    };

    Ok(ClangStmtSkeleton::If {
        condition,
        then_body: stmt_body_skeleton_from_ast(then_body)?,
        else_body,
    })
}

#[cfg(feature = "typed-ir")]
fn while_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [condition, body] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_while_stmt".to_string(),
            message: "WhileStmt must have condition and body".to_string(),
        });
    };
    Ok(ClangStmtSkeleton::While {
        condition: while_condition_expr_skeleton_from_ast(condition)?,
        body: stmt_body_skeleton_from_ast(body)?,
    })
}

#[cfg(feature = "typed-ir")]
fn do_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [body, condition] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_do_stmt".to_string(),
            message: "DoStmt must have body and condition".to_string(),
        });
    };
    let mut body = stmt_body_skeleton_from_ast(body)?;
    let condition = match do_while_tail_call_assignment_from_ast(condition)? {
        AssignmentCallComparisonNormalization::NotMatched => {
            condition_expr_skeleton_from_ast(condition)?
        }
        AssignmentCallComparisonNormalization::Rejected(reason) => {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
        AssignmentCallComparisonNormalization::Accepted {
            assignment,
            condition,
        } => {
            do_while_body_insert_tail_assignment_before_current_level_continue(
                &mut body,
                &assignment,
            );
            body.push(assignment);
            condition
        }
    };
    Ok(ClangStmtSkeleton::DoWhile {
        body,
        condition,
    })
}

#[cfg(feature = "typed-ir")]
fn unsupported_stmt_reason(stmt: &Value, kind: &str) -> String {
    match string_field(stmt, "opcode") {
        Some(opcode) => {
            format!("{kind} opcode {opcode} is outside the current clang lowering skeleton")
        }
        None => format!("{kind} is outside the current clang lowering skeleton"),
    }
}

#[cfg(feature = "typed-ir")]
fn unsupported_control_flow_stmt_reason(stmt: &Value) -> String {
    let kind = string_field(stmt, "kind").unwrap_or_else(|| "unknown".to_string());
    let mut reason =
        format!("unsupported control-flow {kind} requires structured CFG/relooper support");
    match kind.as_str() {
        "GotoStmt" => {
            if let Some(label) = inner(stmt)
                .iter()
                .find(|child| string_field(child, "kind").as_deref() == Some("LabelDecl"))
                .and_then(|child| string_field(child, "name"))
            {
                reason.push_str(&format!(" before lowering target label {label}"));
            }
        }
        "LabelStmt" => {
            if let Some(label) = string_field(stmt, "name") {
                reason.push_str(&format!(" before lowering label {label}"));
            }
        }
        "CaseStmt" => {
            if let Some(value) = inner(stmt).first().and_then(case_label_value) {
                reason.push_str(&format!(" before lowering case {value}"));
            }
        }
        _ => {}
    }
    if let Some(source_range) = clang_source_range_summary(stmt) {
        reason.push_str(&format!(" source_range={source_range}"));
    }
    reason
}

#[cfg(feature = "typed-ir")]
fn clang_source_range_summary(node: &Value) -> Option<String> {
    let (begin_node, end_node) = match node.get("range") {
        Some(range) => (range.get("begin")?, range.get("end")?),
        None => {
            let loc = node.get("loc")?;
            (loc, loc)
        }
    };
    let begin = clang_location_summary(begin_node)?;
    let end = clang_location_summary(end_node)?;
    Some(format!("{begin}-{end}"))
}

#[cfg(feature = "typed-ir")]
fn clang_location_summary(node: &Value) -> Option<String> {
    let location = node
        .get("spellingLoc")
        .or_else(|| node.get("expansionLoc"))
        .unwrap_or(node);
    let line = integer_field(location, "line")?;
    let col = integer_field(location, "col")?;
    Some(format!("{line}:{col}"))
}

#[cfg(feature = "typed-ir")]
fn case_label_value(node: &Value) -> Option<String> {
    match string_field(node, "kind").as_deref() {
        Some("IntegerLiteral") => string_field(node, "value"),
        Some("ImplicitCastExpr" | "ParenExpr") => inner(node).first().and_then(case_label_value),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn decl_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let var_decls = decl_stmt_var_decls(stmt);
    let [var_decl] = var_decls.as_slice() else {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: decl_stmt_var_decl_count_reason(var_decls.len()),
        });
    };
    var_decl_skeleton_from_ast(var_decl)
}

#[cfg(feature = "typed-ir")]
fn decl_stmt_var_decls(stmt: &Value) -> Vec<&Value> {
    inner(stmt)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("VarDecl"))
        .collect()
}

#[cfg(feature = "typed-ir")]
fn decl_stmt_var_decl_count_reason(count: usize) -> String {
    format!("DeclStmt with {count} VarDecl children is outside the current clang lowering skeleton")
}

#[cfg(feature = "typed-ir")]
fn var_decl_skeleton_from_ast(var_decl: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let name = string_field(var_decl, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_var_decl".to_string(),
        message: "VarDecl is missing name".to_string(),
    })?;
    let ty = var_decl
        .get("type")
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_var_decl".to_string(),
            message: format!("VarDecl {name} is missing qualType"),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))?;
    let initializer_children = inner(var_decl);
    let init = match initializer_children {
        [] if var_decl.get("init").is_none() => None,
        [] => {
            return Ok(ClangStmtSkeleton::Unsupported {
                reason: "VarDecl initializer marker without initializer child is outside the current clang lowering skeleton".to_string(),
            });
        }
        [initializer] => Some(value_expr_skeleton_from_ast(initializer)?),
        _ => {
            return Ok(ClangStmtSkeleton::Unsupported {
                reason: format!(
                    "VarDecl with {} initializer children is outside the current clang lowering skeleton",
                    initializer_children.len()
                ),
            });
        }
    };

    Ok(ClangStmtSkeleton::Decl { name, ty, init })
}
