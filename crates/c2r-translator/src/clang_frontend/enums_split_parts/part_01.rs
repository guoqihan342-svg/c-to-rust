#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_stmts(
    statements: &mut [ClangStmtSkeleton],
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    for statement in statements {
        rewrite_supported_enum_types_in_stmt(statement, inventory)?;
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_stmt(
    statement: &mut ClangStmtSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    match statement {
        ClangStmtSkeleton::Decl { ty, init, .. } => {
            rewrite_supported_enum_type(ty, inventory)?;
            if let Some(init) = init {
                rewrite_supported_enum_types_in_expr(init, inventory)?;
            }
        }
        ClangStmtSkeleton::Assign { target, value } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_types_in_expr(value, inventory)?;
        }
        ClangStmtSkeleton::CompoundAssign {
            target,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            ..
        } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_types_in_expr(value, inventory)?;
            rewrite_supported_enum_type(result_ty, inventory)?;
            rewrite_supported_enum_type(compute_lhs_ty, inventory)?;
            rewrite_supported_enum_type(compute_result_ty, inventory)?;
        }
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_stmts(then_body, inventory)?;
            rewrite_supported_enum_types_in_stmts(else_body, inventory)?;
        }
        ClangStmtSkeleton::While { condition, body } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
        }
        ClangStmtSkeleton::DoWhile { body, condition } => {
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
        }
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => {
            rewrite_supported_enum_types_in_stmts(init, inventory)?;
            if let Some(condition) = condition {
                rewrite_supported_enum_types_in_expr(condition, inventory)?;
            }
            if let Some(step) = step {
                rewrite_supported_enum_types_in_stmt(step, inventory)?;
            }
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
        }
        ClangStmtSkeleton::Return { value } => {
            if let Some(value) = value {
                rewrite_supported_enum_types_in_expr(value, inventory)?;
            }
        }
        ClangStmtSkeleton::Expr { expr } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
        }
        ClangStmtSkeleton::Break
        | ClangStmtSkeleton::Continue
        | ClangStmtSkeleton::Unsupported { .. } => {}
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_expr(
    expr: &mut ClangExprSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::NullPtr { ty } => {
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::SizeOfType { ty, .. } | ClangExprSkeleton::AlignOfType { ty, .. } => {
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Binary { lhs, rhs, ty, .. } => {
            rewrite_supported_enum_types_in_expr(lhs, inventory)?;
            rewrite_supported_enum_types_in_expr(rhs, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Unary { operand, ty, .. } => {
            rewrite_supported_enum_types_in_expr(operand, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_expr(then_expr, inventory)?;
            rewrite_supported_enum_types_in_expr(else_expr, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Cast { expr, target, .. }
        | ClangExprSkeleton::LValueToRValue { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::Call { args, ty, .. } => {
            for arg in args {
                rewrite_supported_enum_types_in_expr(arg, inventory)?;
            }
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::IncDec { target, ty, .. } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Deref { ptr, ty } => {
            rewrite_supported_enum_types_in_expr(ptr, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::AddrOf { operand, ty } => {
            rewrite_supported_enum_types_in_expr(operand, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::ArrayToPointerDecay { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::FunctionToPointerDecay { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::Index { base, index, ty } => {
            rewrite_supported_enum_types_in_expr(base, inventory)?;
            rewrite_supported_enum_types_in_expr(index, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::ArrayLiteral { elements, ty } => {
            for element in elements {
                rewrite_supported_enum_types_in_expr(element, inventory)?;
            }
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Member { base, ty, .. } => {
            rewrite_supported_enum_types_in_expr(base, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Unsupported { .. } => {}
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_type(
    ty: &mut ClangTypeSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    let candidates = enum_type_inventory_candidates(ty);
    if candidates.is_empty() {
        return Ok(());
    }

    for name in &candidates {
        if let Some(entry) = inventory.by_name.get(name) {
            match entry {
                Ok(mapped) => {
                    *ty = mapped.clone();
                    return Ok(());
                }
                Err(reason) => {
                    return Err(ClangFrontendError {
                        kind: "unsupported_clang_type".to_string(),
                        message: format!("enum {name}: {reason}"),
                    });
                }
            }
        }
    }

    let Some(name) = direct_enum_type_name(ty) else {
        return Ok(());
    };
    Err(ClangFrontendError {
        kind: "unsupported_clang_type".to_string(),
        message: format!(
            "enum {name} is not present in the clang enum type inventory; enum type lowering requires a complete EnumDecl"
        ),
    })
}

#[cfg(feature = "typed-ir")]
fn enum_type_inventory_candidates(ty: &ClangTypeSkeleton) -> Vec<String> {
    let mut candidates = Vec::new();
    push_enum_type_inventory_candidate(&mut candidates, &ty.spelled);
    push_enum_type_inventory_candidate(&mut candidates, &ty.canonical);
    candidates
}

#[cfg(feature = "typed-ir")]
fn push_enum_type_inventory_candidate(candidates: &mut Vec<String>, spelling: &str) {
    if let Some(name) = direct_enum_name_from_spelling(spelling)
        .or_else(|| direct_typedef_enum_alias_from_spelling(spelling))
    {
        if !candidates.contains(&name) {
            candidates.push(name);
        }
    }
}

#[cfg(feature = "typed-ir")]
fn direct_enum_type_name(ty: &ClangTypeSkeleton) -> Option<String> {
    direct_enum_name_from_spelling(&ty.spelled)
        .or_else(|| direct_enum_name_from_spelling(&ty.canonical))
}

#[cfg(feature = "typed-ir")]
fn direct_enum_name_from_spelling(spelling: &str) -> Option<String> {
    let name = spelling.trim().strip_prefix("enum ")?.trim();
    if is_simple_c_identifier(name) {
        Some(name.to_string())
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
fn direct_typedef_enum_alias_from_spelling(spelling: &str) -> Option<String> {
    let alias = spelling.trim();
    if is_simple_c_identifier(alias) {
        Some(alias.to_string())
    } else {
        None
    }
}
