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
    if is_empty_ast_slot(step) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt without step is outside the current clang lowering skeleton"
                .to_string(),
        });
    }
    Ok(ClangStmtSkeleton::For {
        init,
        condition: Some(condition_expr_skeleton_from_ast(condition)?),
        step: Some(Box::new(for_step_stmt_skeleton_from_ast(step)?)),
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
fn for_step_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            assign_stmt_skeleton_from_ast(stmt)
        }
        Some("CompoundAssignOperator") => compound_assign_stmt_skeleton_from_ast(stmt),
        Some("UnaryOperator") => inc_dec_for_step_skeleton_from_ast(stmt),
        Some(kind) => Ok(ClangStmtSkeleton::Unsupported {
            reason: format!("ForStmt step {kind} is outside the current clang lowering skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt step slot is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn inc_dec_for_step_skeleton_from_ast(
    stmt: &Value,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    inc_dec_stmt_skeleton_from_ast(stmt, "ForStmt step")
}

#[cfg(feature = "typed-ir")]
fn inc_dec_stmt_skeleton_from_ast(
    stmt: &Value,
    context: &str,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let step = inc_dec_expr_skeleton_from_ast(stmt, true, false)?;
    let ClangExprSkeleton::IncDec { target, op, ty, .. } = step else {
        let reason = match step {
            ClangExprSkeleton::Unsupported { reason, .. } => reason,
            _ => format!("{context} must be an increment/decrement expression"),
        };
        return Ok(ClangStmtSkeleton::Unsupported { reason });
    };
    let target_ty = match inc_dec_assignment_target_type(target.as_ref(), context) {
        Ok(target_ty) => target_ty,
        Err(reason) => {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    }
    .clone();
    if !matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
        || !compound_assignment_types_match(&target_ty, &ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "{context} inc/dec target type {} is unsupported",
                target_ty.canonical
            ),
        });
    }
    let bin_op = match op {
        ClangIncDecOperator::Inc => ClangBinaryOperator::Add,
        ClangIncDecOperator::Dec => ClangBinaryOperator::Sub,
    };
    Ok(ClangStmtSkeleton::Assign {
        target: target.as_ref().clone(),
        value: ClangExprSkeleton::Binary {
            op: bin_op,
            lhs: target,
            rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: target_ty.clone(),
            }),
            ty: target_ty.clone(),
        },
    })
}

#[cfg(feature = "typed-ir")]
fn inc_dec_assignment_target_type<'a>(
    target: &'a ClangExprSkeleton,
    context: &str,
) -> Result<&'a ClangTypeSkeleton, String> {
    match target {
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ty),
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: true,
            ..
        } => {
            if context != "statement" {
                return Err(format!(
                    "{context} inc/dec record pointer field targets are unsupported outside standalone statements"
                ));
            }
            match base.as_ref() {
                ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                    if clang_type_is_mutable_record_pointer(base_ty) =>
                {
                    Ok(ty)
                }
                ClangExprSkeleton::DeclRef { .. } => Err(format!(
                    "{context} inc/dec record pointer field target base must be a non-const record pointer variable"
                )),
                _ => Err(format!(
                    "{context} inc/dec record pointer field target must have a direct record pointer variable base"
                )),
            }
        }
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: false,
            ..
        } => {
            if context != "statement" && context != "ForStmt step" {
                return Err(format!(
                    "{context} inc/dec record field targets are unsupported outside standalone statements"
                ));
            }
            match base.as_ref() {
                ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                    if matches!(&base_ty.kind, ClangTypeKind::Record { .. }) =>
                {
                    Ok(ty)
                }
                ClangExprSkeleton::DeclRef { .. } => Err(format!(
                    "{context} inc/dec record field target base must be a record variable"
                )),
                _ => Err(format!(
                    "{context} inc/dec record field target must have a direct record variable base"
                )),
            }
        }
        _ => Err(format!(
            "{context} inc/dec target must be a simple variable, by-value record field, or direct mutable record pointer field"
        )),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_body_skeleton_from_ast(
    compound: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(compound, "kind").as_deref() != Some("CompoundStmt") {
        return Err(ClangFrontendError {
            kind: "invalid_compound_stmt".to_string(),
            message: "expected CompoundStmt body".to_string(),
        });
    }

    let mut body = Vec::new();
    for stmt in inner(compound) {
        body.extend(body_stmt_skeletons_from_ast(stmt)?);
    }
    Ok(body)
}

#[cfg(feature = "typed-ir")]
fn body_stmt_skeletons_from_ast(
    stmt: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(stmt, "kind").as_deref() != Some("DeclStmt") {
        return Ok(vec![stmt_skeleton_from_ast(stmt)?]);
    }

    let var_decls = decl_stmt_var_decls(stmt);
    if var_decls.is_empty() {
        return Ok(vec![ClangStmtSkeleton::Unsupported {
            reason: decl_stmt_var_decl_count_reason(0),
        }]);
    }

    var_decls
        .into_iter()
        .map(var_decl_skeleton_from_ast)
        .collect()
}

#[cfg(feature = "typed-ir")]
fn stmt_body_skeleton_from_ast(body: &Value) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(body, "kind").as_deref() == Some("CompoundStmt") {
        compound_body_skeleton_from_ast(body)
    } else {
        Ok(vec![stmt_skeleton_from_ast(body)?])
    }
}

#[cfg(feature = "typed-ir")]
fn assign_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [target, value] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_assignment_operator".to_string(),
            message: "assignment BinaryOperator must have two operands".to_string(),
        });
    };

    Ok(ClangStmtSkeleton::Assign {
        target: expr_skeleton_from_ast(target)?,
        value: value_expr_skeleton_from_ast(value)?,
    })
}

#[cfg(feature = "typed-ir")]
fn compound_assign_stmt_skeleton_from_ast(
    stmt: &Value,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let op = compound_assignment_operator_from_opcode(string_field(stmt, "opcode").as_deref())?;
    let result_ty = expr_type(stmt)?;
    let compute_lhs_ty = compound_assignment_type_field(stmt, "computeLHSType")?;
    let compute_result_ty = compound_assignment_type_field(stmt, "computeResultType")?;
    let children = inner(stmt);
    let [target, value] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: "CompoundAssignOperator must have two operands".to_string(),
        });
    };
    let target = expr_skeleton_from_ast(target)?;
    let target_ty = match compound_assignment_target_type(&target) {
        Ok(target_ty) => target_ty,
        Err(reason) => {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    };
    if !compound_assignment_types_match(target_ty, &result_ty) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "compound assignment result type must match target type: target={}, result={}",
                target_ty.canonical, result_ty.canonical
            ),
        });
    }
    if !compound_assignment_integer_types_supported(target_ty, &compute_lhs_ty, &compute_result_ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "compound assignment integer promotion types are unsupported: target={}, compute_lhs={}, compute_result={}",
                target_ty.canonical, compute_lhs_ty.canonical, compute_result_ty.canonical
            ),
        });
    }
    let preserve_integral_casts = preserves_integral_operand_casts(&op);
    let value = expr_skeleton_from_ast_with_options(value, preserve_integral_casts)?;
    if compound_assignment_target_is_direct_record_field(&target) {
        if let Some(reason) = record_field_compound_assignment_value_rejection_reason(&value) {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    }

    Ok(ClangStmtSkeleton::CompoundAssign {
        target,
        op,
        value,
        result_ty,
        compute_lhs_ty,
        compute_result_ty,
    })
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_type(
    target: &ClangExprSkeleton,
) -> Result<&ClangTypeSkeleton, String> {
    match target {
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ty),
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: true,
            ..
        } => match base.as_ref() {
            ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                if clang_type_is_mutable_record_pointer(base_ty) =>
            {
                Ok(ty)
            }
            ClangExprSkeleton::DeclRef { .. } => Err(
                "compound assignment arrow member target base must be a non-const record pointer variable"
                    .to_string(),
            ),
            _ => Err(
                "compound assignment arrow member target must have a direct record pointer variable base"
                    .to_string(),
            ),
        },
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: false,
            ..
        } => match base.as_ref() {
            ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                if matches!(&base_ty.kind, ClangTypeKind::Record { .. }) =>
            {
                Ok(ty)
            }
            ClangExprSkeleton::DeclRef { .. } => Err(
                "compound assignment record field target base must be a record variable"
                    .to_string(),
            ),
            _ => Err(
                "compound assignment record field target must have a direct record variable base"
                    .to_string(),
            ),
        },
        _ => Err(
            "compound assignment target must be a simple variable or by-value record field, or direct mutable record pointer field"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_direct_record_field(target: &ClangExprSkeleton) -> bool {
    compound_assignment_target_is_by_value_record_field(target)
        || compound_assignment_target_is_mutable_record_pointer_field(target)
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_by_value_record_field(target: &ClangExprSkeleton) -> bool {
    matches!(
        target,
        ClangExprSkeleton::Member {
            base,
            is_arrow: false,
            ..
        } if matches!(
            base.as_ref(),
            ClangExprSkeleton::DeclRef {
                ty: ClangTypeSkeleton {
                    kind: ClangTypeKind::Record { .. },
                    ..
                },
                ..
            }
        )
    )
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_mutable_record_pointer_field(target: &ClangExprSkeleton) -> bool {
    matches!(
        target,
        ClangExprSkeleton::Member {
            base,
            is_arrow: true,
            ..
        } if matches!(
            base.as_ref(),
            ClangExprSkeleton::DeclRef {
                ty,
                ..
            } if clang_type_is_mutable_record_pointer(ty)
        )
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_record_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Record { .. })
    )
}

#[cfg(feature = "typed-ir")]
fn record_field_compound_assignment_value_rejection_reason(
    value: &ClangExprSkeleton,
) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. } => {
            if matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                None
            } else {
                Some(format!(
                    "record field compound assignment RHS must be a simple integer variable, literal, or integral cast; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. } => {
            if !matches!(&target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "record field compound assignment RHS cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            record_field_compound_assignment_value_rejection_reason(expr)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "record field compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "record field compound assignment RHS must be a simple integer variable, literal, or integral cast"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_type_field(
    stmt: &Value,
    field: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    stmt.get(field)
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: format!("CompoundAssignOperator is missing {field}.qualType"),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_types_match(lhs: &ClangTypeSkeleton, rhs: &ClangTypeSkeleton) -> bool {
    lhs.canonical == rhs.canonical && lhs.kind == rhs.kind
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_integer_types_supported(
    target_ty: &ClangTypeSkeleton,
    compute_lhs_ty: &ClangTypeSkeleton,
    compute_result_ty: &ClangTypeSkeleton,
) -> bool {
    matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
        && matches!(&compute_lhs_ty.kind, ClangTypeKind::Integer { .. })
        && compound_assignment_types_match(compute_lhs_ty, compute_result_ty)
}

#[cfg(feature = "typed-ir")]
fn if_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let (condition, then_body, else_body) = match children {
        [condition, then_body] => (condition, then_body, None),
        [condition, then_body, else_body] => (condition, then_body, Some(else_body)),
        _ => {
            return Err(ClangFrontendError {
                kind: "invalid_if_stmt".to_string(),
                message: "IfStmt must have condition and then body".to_string(),
            })
        }
    };
    let else_body = match else_body {
        Some(else_body) => stmt_body_skeleton_from_ast(else_body)?,
        None => Vec::new(),
    };

    Ok(ClangStmtSkeleton::If {
        condition: condition_expr_skeleton_from_ast(condition)?,
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
    Ok(ClangStmtSkeleton::DoWhile {
        body: stmt_body_skeleton_from_ast(body)?,
        condition: condition_expr_skeleton_from_ast(condition)?,
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
