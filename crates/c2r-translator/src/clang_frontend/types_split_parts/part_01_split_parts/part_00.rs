#[cfg(feature = "typed-ir")]
pub(super) fn is_target_dependent_integer_spelling(spelling: &str) -> bool {
    matches!(
        spelling.trim(),
        "char"
            | "short"
            | "unsigned short"
            | "long"
            | "unsigned long"
            | "long long"
            | "unsigned long long"
            | "size_t"
            | "__size_t"
    )
}

#[cfg(feature = "typed-ir")]
pub(super) fn target_dependent_integer_width(
    spelling: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<(bool, u16)> {
    let abi = target_abi?;
    match spelling {
        "char" => {
            let width = nonzero_width(abi.char_width)?;
            let signed = abi.plain_char_signed?;
            Some((signed, width))
        }
        "short" => nonzero_width(abi.short_width).map(|width| (true, width)),
        "unsigned short" => nonzero_width(abi.short_width).map(|width| (false, width)),
        "long" => nonzero_width(abi.long_width).map(|width| (true, width)),
        "unsigned long" => nonzero_width(abi.long_width).map(|width| (false, width)),
        "long long" => nonzero_width(abi.long_long_width).map(|width| (true, width)),
        "unsigned long long" => nonzero_width(abi.long_long_width).map(|width| (false, width)),
        "size_t" | "__size_t" => nonzero_width(abi.pointer_width).map(|width| (false, width)),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn target_dependent_integer_alignment(
    spelling: &str,
    target_abi: &TargetAbiProfile,
) -> Option<u16> {
    match spelling {
        "char" | "signed char" | "unsigned char" => nonzero_width(target_abi.char_align),
        "short" | "unsigned short" => nonzero_width(target_abi.short_align),
        "int" | "unsigned int" => nonzero_width(target_abi.int_align),
        "long" | "unsigned long" => nonzero_width(target_abi.long_align),
        "long long" | "unsigned long long" => nonzero_width(target_abi.long_long_align),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn target_abi_alignment_bits_for_type(
    ty: &ClangTypeSkeleton,
    target_abi: &TargetAbiProfile,
) -> Option<u16> {
    match &ty.kind {
        ClangTypeKind::Integer { .. } => {
            target_dependent_integer_alignment(&ty.canonical, target_abi)
                .or_else(|| target_dependent_integer_alignment(&ty.spelled, target_abi))
        }
        ClangTypeKind::Pointer { .. } => nonzero_width(target_abi.pointer_align),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn target_abi_alignment_bits_for_alignof_type(
    ty: &ClangTypeSkeleton,
    alignment_type_spellings: &[String],
    target_abi: &TargetAbiProfile,
) -> Option<u16> {
    target_abi_alignment_bits_for_type(ty, target_abi).or_else(|| {
        if !alignment_type_spellings
            .iter()
            .any(|spelling| matches!(spelling.trim(), "size_t" | "__size_t"))
        {
            return None;
        }
        alignment_type_spellings
            .iter()
            .filter_map(|spelling| {
                type_from_qual_type_with_target_abi(spelling, Some(target_abi)).ok()
            })
            .find_map(|candidate| target_abi_alignment_bits_for_type(&candidate, target_abi))
    })
}

#[cfg(feature = "typed-ir")]
pub(super) fn nonzero_width(width: u16) -> Option<u16> {
    if width == 0 {
        None
    } else {
        Some(width)
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn bind_target_abi_to_function_skeleton(
    function: &mut ClangFunctionSkeleton,
    target_abi: &TargetAbiProfile,
) {
    bind_target_abi_to_type(&mut function.return_type, target_abi);
    for param in &mut function.params {
        bind_target_abi_to_type(&mut param.ty, target_abi);
    }
    bind_target_abi_to_stmts(&mut function.body, target_abi);
}

#[cfg(feature = "typed-ir")]
pub(super) fn bind_target_abi_to_stmts(
    statements: &mut [ClangStmtSkeleton],
    target_abi: &TargetAbiProfile,
) {
    for statement in statements {
        bind_target_abi_to_stmt(statement, target_abi);
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn bind_target_abi_to_stmt(
    statement: &mut ClangStmtSkeleton,
    target_abi: &TargetAbiProfile,
) {
    match statement {
        ClangStmtSkeleton::Decl { ty, init, .. } => {
            bind_target_abi_to_type(ty, target_abi);
            if let Some(init) = init {
                bind_target_abi_to_expr(init, target_abi);
            }
        }
        ClangStmtSkeleton::Assign { target, value } => {
            bind_target_abi_to_expr(target, target_abi);
            bind_target_abi_to_expr(value, target_abi);
        }
        ClangStmtSkeleton::CompoundAssign {
            target,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            ..
        } => {
            bind_target_abi_to_expr(target, target_abi);
            bind_target_abi_to_expr(value, target_abi);
            bind_target_abi_to_type(result_ty, target_abi);
            bind_target_abi_to_type(compute_lhs_ty, target_abi);
            bind_target_abi_to_type(compute_result_ty, target_abi);
        }
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => {
            bind_target_abi_to_expr(condition, target_abi);
            bind_target_abi_to_stmts(then_body, target_abi);
            bind_target_abi_to_stmts(else_body, target_abi);
        }
        ClangStmtSkeleton::While { condition, body } => {
            bind_target_abi_to_expr(condition, target_abi);
            bind_target_abi_to_stmts(body, target_abi);
        }
        ClangStmtSkeleton::DoWhile { body, condition } => {
            bind_target_abi_to_stmts(body, target_abi);
            bind_target_abi_to_expr(condition, target_abi);
        }
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => {
            bind_target_abi_to_stmts(init, target_abi);
            if let Some(condition) = condition {
                bind_target_abi_to_expr(condition, target_abi);
            }
            if let Some(step) = step {
                bind_target_abi_to_stmt(step, target_abi);
            }
            bind_target_abi_to_stmts(body, target_abi);
        }
        ClangStmtSkeleton::Return { value } => {
            if let Some(value) = value {
                bind_target_abi_to_expr(value, target_abi);
            }
        }
        ClangStmtSkeleton::Expr { expr } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangStmtSkeleton::Break
        | ClangStmtSkeleton::Continue
        | ClangStmtSkeleton::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn bind_target_abi_to_expr(expr: &mut ClangExprSkeleton, target_abi: &TargetAbiProfile) {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. }
        | ClangExprSkeleton::AlignOfType { ty, .. }
        | ClangExprSkeleton::NullPtr { ty }
        | ClangExprSkeleton::Binary { ty, .. }
        | ClangExprSkeleton::Unary { ty, .. }
        | ClangExprSkeleton::Conditional { ty, .. }
        | ClangExprSkeleton::IncDec { ty, .. }
        | ClangExprSkeleton::Deref { ty, .. }
        | ClangExprSkeleton::AddrOf { ty, .. }
        | ClangExprSkeleton::Index { ty, .. }
        | ClangExprSkeleton::ArrayLiteral { ty, .. }
        | ClangExprSkeleton::Call { ty, .. }
        | ClangExprSkeleton::Member { ty, .. } => {
            bind_target_abi_to_type(ty, target_abi);
        }
        ClangExprSkeleton::MutableVoidPointerAddress {
            source_pointer,
            target,
            ..
        } => {
            bind_target_abi_to_type(source_pointer, target_abi);
            bind_target_abi_to_type(target, target_abi);
        }
        ClangExprSkeleton::Cast { target, .. }
        | ClangExprSkeleton::LValueToRValue { target, .. }
        | ClangExprSkeleton::ArrayToPointerDecay { target, .. }
        | ClangExprSkeleton::FunctionToPointerDecay { target, .. } => {
            bind_target_abi_to_type(target, target_abi);
        }
        ClangExprSkeleton::Unsupported { .. } => {}
    }

    match expr {
        ClangExprSkeleton::Binary { lhs, rhs, .. } => {
            bind_target_abi_to_expr(lhs, target_abi);
            bind_target_abi_to_expr(rhs, target_abi);
        }
        ClangExprSkeleton::Unary { operand, .. } => {
            bind_target_abi_to_expr(operand, target_abi);
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            bind_target_abi_to_expr(condition, target_abi);
            bind_target_abi_to_expr(then_expr, target_abi);
            bind_target_abi_to_expr(else_expr, target_abi);
        }
        ClangExprSkeleton::IncDec { target, .. } => {
            bind_target_abi_to_expr(target, target_abi);
        }
        ClangExprSkeleton::Deref { ptr, .. } => {
            bind_target_abi_to_expr(ptr, target_abi);
        }
        ClangExprSkeleton::AddrOf { operand, .. } => {
            bind_target_abi_to_expr(operand, target_abi);
        }
        ClangExprSkeleton::MutableVoidPointerAddress { operand, .. } => {
            bind_target_abi_to_expr(operand, target_abi);
        }
        ClangExprSkeleton::Cast { expr, .. } | ClangExprSkeleton::LValueToRValue { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::ArrayToPointerDecay { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::FunctionToPointerDecay { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::SizeOfType {
            arg_type,
            target_abi: bound_target_abi,
            ..
        } => {
            bind_target_abi_to_type(arg_type, target_abi);
            *bound_target_abi = Some(target_abi.clone());
        }
        ClangExprSkeleton::AlignOfType {
            arg_type,
            alignment_bits,
            alignment_type_spellings,
            ..
        } => {
            bind_target_abi_to_type(arg_type, target_abi);
            *alignment_bits = target_abi_alignment_bits_for_alignof_type(
                arg_type,
                alignment_type_spellings,
                target_abi,
            );
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            bind_target_abi_to_expr(base, target_abi);
            bind_target_abi_to_expr(index, target_abi);
        }
        ClangExprSkeleton::ArrayLiteral { elements, .. } => {
            for element in elements {
                bind_target_abi_to_expr(element, target_abi);
            }
        }
        ClangExprSkeleton::Call { args, .. } => {
            for arg in args {
                bind_target_abi_to_expr(arg, target_abi);
            }
        }
        ClangExprSkeleton::Member { base, .. } => {
            bind_target_abi_to_expr(base, target_abi);
        }
        ClangExprSkeleton::DeclRef { .. }
        | ClangExprSkeleton::IntegerLiteral { .. }
        | ClangExprSkeleton::NullPtr { .. }
        | ClangExprSkeleton::Unsupported { .. } => {}
    }
}
