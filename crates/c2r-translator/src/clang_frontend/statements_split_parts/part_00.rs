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

#[cfg(feature = "typed-ir")]
fn for_init_comma_assignment_rhs_rejection_reason(value: &ClangExprSkeleton) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty)
        }
        ClangExprSkeleton::SizeOfType { arg_type, ty }
        | ClangExprSkeleton::AlignOfType { arg_type, ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty).or_else(|| {
                clang_type_contains_pointer(arg_type).then(|| {
                    "ForStmt init comma-chain assignment RHS cannot inspect a pointer type"
                        .to_string()
                })
            })
        }
        ClangExprSkeleton::Binary { lhs, rhs, ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty)
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(lhs))
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(rhs))
        }
        ClangExprSkeleton::Unary { operand, ty, .. } => {
            for_init_comma_integer_type_rejection_reason(ty)
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(operand))
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => for_init_comma_integer_type_rejection_reason(ty)
            .or_else(|| for_init_comma_assignment_rhs_rejection_reason(condition))
            .or_else(|| for_init_comma_assignment_rhs_rejection_reason(then_expr))
            .or_else(|| for_init_comma_assignment_rhs_rejection_reason(else_expr)),
        ClangExprSkeleton::Cast { target, expr, .. }
        | ClangExprSkeleton::LValueToRValue { target, expr } => {
            for_init_comma_integer_type_rejection_reason(target)
                .or_else(|| for_init_comma_assignment_rhs_rejection_reason(expr))
        }
        ClangExprSkeleton::Call { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a call".to_string(),
        ),
        ClangExprSkeleton::Deref { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a dereference".to_string(),
        ),
        ClangExprSkeleton::AddrOf { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain address-of".to_string(),
        ),
        ClangExprSkeleton::IncDec { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain increment/decrement"
                .to_string(),
        ),
        ClangExprSkeleton::Member { .. } | ClangExprSkeleton::Index { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a memory access".to_string(),
        ),
        ClangExprSkeleton::NullPtr { .. }
        | ClangExprSkeleton::ArrayToPointerDecay { .. }
        | ClangExprSkeleton::FunctionToPointerDecay { .. } => Some(
            "ForStmt init comma-chain assignment RHS cannot contain a pointer expression"
                .to_string(),
        ),
        ClangExprSkeleton::ArrayLiteral { .. } => Some(
            "ForStmt init comma-chain assignment RHS must be a pure integer scalar expression"
                .to_string(),
        ),
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "ForStmt init comma-chain assignment RHS uses unsupported expression {node}: {reason}"
        )),
    }
}

#[cfg(feature = "typed-ir")]
fn for_init_comma_integer_type_rejection_reason(ty: &ClangTypeSkeleton) -> Option<String> {
    if clang_type_is_volatile(ty) {
        return Some(format!(
            "ForStmt init comma-chain assignment RHS cannot read volatile type {}",
            ty.spelled
        ));
    }
    if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
        return Some(format!(
            "ForStmt init comma-chain assignment RHS must be an integer scalar, got {}",
            ty.spelled
        ));
    }
    None
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_volatile(ty: &ClangTypeSkeleton) -> bool {
    [ty.spelled.as_str(), ty.canonical.as_str()]
        .into_iter()
        .any(|spelling| {
            spelling
                .split(|ch: char| !ch.is_ascii_alphanumeric() && ch != '_')
                .any(|part| part == "volatile")
        })
}

#[cfg(feature = "typed-ir")]
fn clang_type_contains_pointer(ty: &ClangTypeSkeleton) -> bool {
    match &ty.kind {
        ClangTypeKind::Pointer { .. } => true,
        ClangTypeKind::Array { element, .. } => clang_type_contains_pointer(element),
        _ => false,
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
    if !is_integer_or_target_dependent_integer_type(&target_ty)
        || !is_same_lvalue_to_rvalue_integer_type(&target_ty, &ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "{context} inc/dec target type {} is unsupported; parsed target {:?} does not match result type {} ({:?})",
                target_ty.canonical, target_ty.kind, ty.canonical, ty.kind
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
            if context != "statement" && context != "ForStmt step" {
                return Err(format!(
                    "{context} inc/dec record pointer field targets are unsupported outside standalone statements or for-loop steps"
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
    match string_field(stmt, "kind").as_deref() {
        Some("NullStmt") => return Ok(Vec::new()),
        Some("IfStmt") => return if_stmt_skeletons_from_ast(stmt),
        Some("DeclStmt") => {}
        _ => return Ok(vec![stmt_skeleton_from_ast(stmt)?]),
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
        body_stmt_skeletons_from_ast(body)
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
    if compound_assignment_target_is_direct_index(&target) {
        if let Some(reason) = index_compound_assignment_value_rejection_reason(&value) {
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
        ClangExprSkeleton::Index { base, index, ty } => {
            compound_assignment_index_target_type(base, index, ty)
        }
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
            "compound assignment target must be a simple variable or by-value record field, direct mutable record pointer field, or supported direct integer index"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_index_target_type<'a>(
    base: &ClangExprSkeleton,
    index: &ClangExprSkeleton,
    target_ty: &'a ClangTypeSkeleton,
) -> Result<&'a ClangTypeSkeleton, String> {
    let ClangExprSkeleton::DeclRef { ty: base_ty, .. } = base else {
        return Err(
            "compound assignment index target must have a direct pointer parameter or local fixed array variable base"
                .to_string(),
        );
    };
    let element_ty = compound_assignment_index_base_element_type(base_ty)?;
    if !compound_assignment_types_match(element_ty, target_ty) {
        return Err(format!(
            "compound assignment index target type must match base element type: element={}, target={}",
            element_ty.canonical, target_ty.canonical
        ));
    }
    if let Some(reason) = compound_assignment_index_rejection_reason(index) {
        return Err(reason);
    }
    Ok(target_ty)
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_index_base_element_type(
    base_ty: &ClangTypeSkeleton,
) -> Result<&ClangTypeSkeleton, String> {
    match &base_ty.kind {
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { .. }) =>
        {
            Ok(pointee)
        }
        ClangTypeKind::Pointer { pointee, .. } if clang_type_is_const(pointee) => Err(format!(
            "compound assignment index pointer base must have a mutable integer element type; got {}",
            base_ty.spelled
        )),
        ClangTypeKind::Pointer { .. } => Err(format!(
            "compound assignment index pointer base must have an integer element type; got {}",
            base_ty.spelled
        )),
        ClangTypeKind::Array {
            element,
            len: Some(len),
        } if *len > 0
            && !clang_type_is_const(base_ty)
            && !clang_type_is_const(element)
            && matches!(&element.kind, ClangTypeKind::Integer { .. }) =>
        {
            Ok(element)
        }
        ClangTypeKind::Array { len: None, .. } => Err(format!(
            "compound assignment index array base must have a complete fixed length; got {}",
            base_ty.spelled
        )),
        ClangTypeKind::Array { element, .. }
            if clang_type_is_const(base_ty) || clang_type_is_const(element) =>
        {
            Err(format!(
                "compound assignment index array base must have a mutable integer element type; got {}",
                base_ty.spelled
            ))
        }
        ClangTypeKind::Array { .. } => Err(format!(
            "compound assignment index array base must be a non-empty fixed integer array; got {}",
            base_ty.spelled
        )),
        _ => Err(format!(
            "compound assignment index base must be a mutable integer pointer or local complete fixed integer array; got {}",
            base_ty.spelled
        )),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_index_rejection_reason(index: &ClangExprSkeleton) -> Option<String> {
    match index {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. } => {
            if matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                None
            } else {
                Some(format!(
                    "compound assignment index must be an integer literal, variable, or integral cast; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. }
        | ClangExprSkeleton::LValueToRValue { target, expr } => {
            if !matches!(&target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "compound assignment index cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            compound_assignment_index_rejection_reason(expr)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "compound assignment index uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "compound assignment index must be a side-effect-free integer literal, variable, or integral cast"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_direct_index(target: &ClangExprSkeleton) -> bool {
    matches!(target, ClangExprSkeleton::Index { .. })
}

#[cfg(feature = "typed-ir")]
fn index_compound_assignment_value_rejection_reason(value: &ClangExprSkeleton) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. } => {
            if matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                None
            } else {
                Some(format!(
                    "index compound assignment RHS must be a side-effect-free integer expression; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. }
        | ClangExprSkeleton::LValueToRValue { target, expr } => {
            if !matches!(&target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "index compound assignment RHS cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            index_compound_assignment_value_rejection_reason(expr)
        }
        ClangExprSkeleton::Binary {
            op,
            lhs,
            rhs,
            ty,
        } if matches!(
            op,
            ClangBinaryOperator::Add
                | ClangBinaryOperator::Sub
                | ClangBinaryOperator::Mul
                | ClangBinaryOperator::Div
                | ClangBinaryOperator::Mod
                | ClangBinaryOperator::BitAnd
                | ClangBinaryOperator::BitOr
                | ClangBinaryOperator::BitXor
                | ClangBinaryOperator::Shl
                | ClangBinaryOperator::Shr
        ) => {
            if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "index compound assignment RHS binary result must be an integer; got {}",
                    ty.spelled
                ));
            }
            index_compound_assignment_value_rejection_reason(lhs)
                .or_else(|| index_compound_assignment_value_rejection_reason(rhs))
        }
        ClangExprSkeleton::Unary {
            op: ClangUnaryOperator::Neg | ClangUnaryOperator::BitNot,
            operand,
            ty,
        } => {
            if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "index compound assignment RHS unary result must be an integer; got {}",
                    ty.spelled
                ));
            }
            index_compound_assignment_value_rejection_reason(operand)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "index compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "index compound assignment RHS must be built from integer literals, variables, casts, and side-effect-free arithmetic or bitwise operators"
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
