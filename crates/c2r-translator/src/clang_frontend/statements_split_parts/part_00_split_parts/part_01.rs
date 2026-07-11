
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
