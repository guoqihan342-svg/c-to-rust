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
        ClangExprSkeleton::Cast { expr, .. } | ClangExprSkeleton::LValueToRValue { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::ArrayToPointerDecay { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::FunctionToPointerDecay { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::SizeOfType { arg_type, .. } => {
            bind_target_abi_to_type(arg_type, target_abi);
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

#[cfg(feature = "typed-ir")]
pub(super) fn bind_target_abi_to_type(ty: &mut ClangTypeSkeleton, target_abi: &TargetAbiProfile) {
    if let Ok(bound) = type_from_qual_type_with_target_abi(&ty.spelled, Some(target_abi)) {
        if !matches!(bound.kind, ClangTypeKind::Unsupported { .. }) {
            *ty = bound;
        }
    }
    match &mut ty.kind {
        ClangTypeKind::Pointer { pointee, .. } => bind_target_abi_to_type(pointee, target_abi),
        ClangTypeKind::Array { element, .. } => bind_target_abi_to_type(element, target_abi),
        _ => {}
    }
}

#[cfg(feature = "typed-ir")]
struct PointerQualType<'a> {
    pointee: &'a str,
    restrict_qualifier: Option<&'static str>,
}

#[cfg(feature = "typed-ir")]
struct FunctionPointerQualType<'a> {
    function: String,
    _source: &'a str,
}

#[cfg(feature = "typed-ir")]
fn split_function_pointer_qual_type(qual_type: &str) -> Option<FunctionPointerQualType<'_>> {
    let trimmed = qual_type.trim();
    let marker = "(*";
    let marker_index = trimmed.find(marker)?;
    let suffix = &trimmed[marker_index + marker.len()..];
    let close_pointer = suffix.find(')')?;
    if !suffix[..close_pointer].trim().is_empty() {
        return None;
    }
    let params = suffix[close_pointer + 1..].trim();
    if !params.starts_with('(') || !params.ends_with(')') {
        return None;
    }
    let return_type = trimmed[..marker_index].trim();
    if return_type.is_empty() || return_type.contains('(') || return_type.contains(')') {
        return None;
    }
    Some(FunctionPointerQualType {
        function: format!("{return_type} {params}"),
        _source: trimmed,
    })
}

#[cfg(feature = "typed-ir")]
pub(super) fn split_function_qual_type(qual_type: &str) -> Option<(&str, &str)> {
    let trimmed = qual_type.trim();
    let open = trimmed.find('(')?;
    let close = matching_close_paren(trimmed, open)?;
    if close != trimmed.len() - 1 {
        return None;
    }
    let return_type = trimmed[..open].trim();
    let params = trimmed[open + 1..close].trim();
    if return_type.is_empty() {
        return None;
    }
    Some((return_type, params))
}

#[cfg(feature = "typed-ir")]
pub(super) fn matching_close_paren(text: &str, open: usize) -> Option<usize> {
    let mut depth = 0usize;
    for (offset, ch) in text[open..].char_indices() {
        match ch {
            '(' => depth += 1,
            ')' => {
                depth = depth.checked_sub(1)?;
                if depth == 0 {
                    return Some(open + offset);
                }
            }
            _ => {}
        }
    }
    None
}

#[cfg(feature = "typed-ir")]
pub(super) fn function_type_skeleton(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    let Some((return_type, _params)) = split_function_qual_type(trimmed) else {
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!("{trimmed} is outside the current function type skeleton"),
            },
        });
    };
    let return_type = type_from_qual_type_with_target_abi(return_type, target_abi)?;
    if matches!(return_type.kind, ClangTypeKind::Unsupported { .. }) {
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!(
                    "function return type {} is outside the current type skeleton",
                    return_type.spelled
                ),
            },
        });
    }
    Ok(ClangTypeSkeleton {
        spelled: trimmed.to_string(),
        canonical: trimmed.to_string(),
        kind: ClangTypeKind::Function,
    })
}

#[cfg(feature = "typed-ir")]
fn split_pointer_qual_type(qual_type: &str) -> Option<PointerQualType<'_>> {
    let trimmed = qual_type.trim();
    if let Some(pointee) = trimmed.strip_suffix('*') {
        return Some(PointerQualType {
            pointee: pointee.trim_end(),
            restrict_qualifier: None,
        });
    }

    for qualifier in ["__restrict__", "__restrict", "restrict"] {
        let Some(prefix) = trimmed.strip_suffix(qualifier) else {
            continue;
        };
        let Some(pointee) = prefix.trim_end().strip_suffix('*') else {
            continue;
        };
        return Some(PointerQualType {
            pointee: pointee.trim_end(),
            restrict_qualifier: Some(qualifier),
        });
    }

    None
}

#[cfg(feature = "typed-ir")]
pub(super) fn split_array_qual_type(
    qual_type: &str,
) -> Result<Option<(&str, Option<usize>)>, ClangFrontendError> {
    let Some(prefix) = qual_type.strip_suffix(']') else {
        return Ok(None);
    };
    let Some(open_index) = prefix.rfind('[') else {
        return Ok(None);
    };
    let element = prefix[..open_index].trim();
    if element.is_empty() {
        return Ok(None);
    }
    if element.contains('[') || element.contains(']') {
        return Err(ClangFrontendError {
            kind: "invalid_array_type".to_string(),
            message: format!(
                "multi-dimensional array qualType requires explicit layout evidence before typed IR lowering: {qual_type}"
            ),
        });
    }
    let len_spelling = prefix[open_index + 1..].trim();
    let len = if len_spelling.is_empty() {
        None
    } else {
        Some(
            len_spelling
                .parse::<usize>()
                .map_err(|error| ClangFrontendError {
                    kind: "invalid_array_type".to_string(),
                    message: format!("array length is not usize: {error}"),
                })?,
        )
    };
    Ok(Some((element, len)))
}
