use serde_json::Value;

use super::{
    is_simple_c_identifier, string_field, ClangExprSkeleton, ClangFrontendError,
    ClangFunctionSkeleton, ClangStmtSkeleton, ClangTypeKind, ClangTypeSkeleton,
};
use crate::TargetAbiProfile;

#[cfg(feature = "typed-ir")]
pub(super) fn function_return_type(
    qual_type: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let Some((return_type, _)) = split_function_qual_type(qual_type) else {
        if qual_type.contains("(*") {
            return Err(ClangFrontendError {
                kind: "unsupported_function_type".to_string(),
                message: format!(
                    "function pointer return type requires explicit function-pointer return lowering evidence: {qual_type}"
                ),
            });
        }
        return Err(ClangFrontendError {
            kind: "unsupported_function_type".to_string(),
            message: format!("unsupported function qualType: {qual_type}"),
        });
    };
    type_from_qual_type(return_type.trim())
}

#[cfg(feature = "typed-ir")]
pub(super) fn function_return_type_from_type_object(
    type_object: &Value,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_ast_type_object_with_parser(
        type_object,
        function_return_type,
        "invalid_function_decl",
        "FunctionDecl is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_ast_type_object(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    validate_fixed_width_typedef_desugaring(type_object, target_abi)?;
    type_from_ast_type_object_with_parser(
        type_object,
        |qual_type| type_from_qual_type_with_target_abi(qual_type, target_abi),
        "invalid_clang_type",
        "clang type object is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_ast_type_object_with_parser<F>(
    type_object: &Value,
    mut parse: F,
    missing_kind: &str,
    missing_message: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError>
where
    F: FnMut(&str) -> Result<ClangTypeSkeleton, ClangFrontendError>,
{
    let candidates = clang_type_candidate_spellings(type_object);
    if candidates.is_empty() {
        return Err(ClangFrontendError {
            kind: missing_kind.to_string(),
            message: missing_message.to_string(),
        });
    }

    let mut first_unsupported = None;
    let mut first_error = None;
    for candidate in candidates {
        match parse(&candidate) {
            Ok(ty) if !matches!(ty.kind, ClangTypeKind::Unsupported { .. }) => return Ok(ty),
            Ok(ty) => {
                if first_unsupported.is_none() {
                    first_unsupported = Some(ty);
                }
            }
            Err(error) => {
                if first_error.is_none() {
                    first_error = Some(error);
                }
            }
        }
    }

    if let Some(ty) = first_unsupported {
        Ok(ty)
    } else if let Some(error) = first_error {
        Err(error)
    } else {
        Err(ClangFrontendError {
            kind: missing_kind.to_string(),
            message: missing_message.to_string(),
        })
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn clang_type_candidate_spellings(type_object: &Value) -> Vec<String> {
    ["qualType", "desugaredQualType", "canonicalQualType"]
        .into_iter()
        .filter_map(|field| string_field(type_object, field))
        .collect()
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Copy)]
struct FixedWidthInteger {
    signed: bool,
    width: u16,
}

#[cfg(feature = "typed-ir")]
pub(super) fn validate_fixed_width_typedef_desugaring(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<(), ClangFrontendError> {
    let Some(qual_type) = string_field(type_object, "qualType") else {
        return Ok(());
    };
    let Some(expected) = fixed_width_integer_signature(qual_type.trim()) else {
        return Ok(());
    };

    for field in ["desugaredQualType", "canonicalQualType"] {
        let Some(spelling) = string_field(type_object, field) else {
            continue;
        };
        let spelling = spelling.trim();
        if spelling == qual_type.trim() {
            continue;
        }
        let parsed = type_from_qual_type_with_target_abi(spelling, target_abi)?;
        match parsed.kind {
            ClangTypeKind::Integer { signed, width }
                if signed == expected.signed && width == expected.width => {}
            ClangTypeKind::Integer { signed, width } => {
                return Err(fixed_width_typedef_mismatch_error(
                    qual_type.trim(),
                    expected,
                    field,
                    spelling,
                    Some((signed, width)),
                    None,
                ));
            }
            ClangTypeKind::Unsupported { reason } => {
                if target_abi.is_none() && reason.contains("requires target ABI width provenance") {
                    continue;
                }
                return Err(fixed_width_typedef_mismatch_error(
                    qual_type.trim(),
                    expected,
                    field,
                    spelling,
                    None,
                    Some(reason.as_str()),
                ));
            }
            _ => {
                return Err(fixed_width_typedef_mismatch_error(
                    qual_type.trim(),
                    expected,
                    field,
                    spelling,
                    None,
                    Some("desugared type is not an integer"),
                ));
            }
        }
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn fixed_width_typedef_mismatch_error(
    qual_type: &str,
    expected: FixedWidthInteger,
    field: &str,
    spelling: &str,
    actual: Option<(bool, u16)>,
    reason: Option<&str>,
) -> ClangFrontendError {
    let actual_text = actual
        .map(|(signed, width)| format!("signed={signed}, width={width}"))
        .or_else(|| reason.map(str::to_string))
        .unwrap_or_else(|| "unresolved".to_string());
    ClangFrontendError {
        kind: "fixed_width_typedef_desugaring_mismatch".to_string(),
        message: format!(
            "{qual_type} requires {field}={spelling} to prove the same fixed-width integer contract (expected signed={}, width={}; actual {actual_text})",
            expected.signed, expected.width
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn fixed_width_integer_signature(spelling: &str) -> Option<FixedWidthInteger> {
    match spelling {
        "int8_t" => Some(FixedWidthInteger {
            signed: true,
            width: 8,
        }),
        "uint8_t" => Some(FixedWidthInteger {
            signed: false,
            width: 8,
        }),
        "int16_t" => Some(FixedWidthInteger {
            signed: true,
            width: 16,
        }),
        "uint16_t" => Some(FixedWidthInteger {
            signed: false,
            width: 16,
        }),
        "int32_t" => Some(FixedWidthInteger {
            signed: true,
            width: 32,
        }),
        "uint32_t" => Some(FixedWidthInteger {
            signed: false,
            width: 32,
        }),
        "int64_t" => Some(FixedWidthInteger {
            signed: true,
            width: 64,
        }),
        "uint64_t" => Some(FixedWidthInteger {
            signed: false,
            width: 64,
        }),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
/// Parses clang `qualType` spelling into the frontend's narrow type skeleton.
///
/// The mapper is intentionally conservative: pointers, `const`, arrays, record
/// names, and fixed-width integer spellings are accepted; target-dependent or
/// ambiguous C spellings fail closed so the typed IR emitter never receives a
/// type whose width or layout was inferred by string guesswork.
pub(super) fn type_from_qual_type(
    qual_type: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_qual_type_with_target_abi(qual_type, None)
}

#[cfg(feature = "typed-ir")]
pub(super) fn type_from_qual_type_with_target_abi(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    if let Some(function_pointer) = split_function_pointer_qual_type(trimmed) {
        let function = function_type_skeleton(function_pointer.function.trim(), target_abi)?;
        let canonical = format!("{} *", function.canonical);
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(function),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(pointer) = split_pointer_qual_type(trimmed) {
        let pointee = type_from_qual_type_with_target_abi(pointer.pointee.trim(), target_abi)?;
        let canonical = match pointer.restrict_qualifier {
            Some(qualifier) => format!("{} *{qualifier}", pointee.canonical),
            None => format!("{} *", pointee.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(pointee),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(unqualified) = trimmed.strip_prefix("const ") {
        let unqualified = type_from_qual_type_with_target_abi(unqualified.trim(), target_abi)?;
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: unqualified.canonical,
            kind: unqualified.kind,
        });
    }
    if let Some((element, len)) = split_array_qual_type(trimmed)? {
        let element = type_from_qual_type_with_target_abi(element, target_abi)?;
        let canonical = match len {
            Some(len) => format!("{}[{len}]", element.canonical),
            None => format!("{}[]", element.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Array {
                element: Box::new(element),
                len,
            },
        });
    }
    if split_function_qual_type(trimmed).is_some() {
        return function_type_skeleton(trimmed, target_abi);
    }
    if let Some(name) = trimmed.strip_prefix("struct ") {
        let name = name.trim();
        if is_simple_c_identifier(name) {
            return Ok(ClangTypeSkeleton {
                spelled: trimmed.to_string(),
                canonical: trimmed.to_string(),
                kind: ClangTypeKind::Record {
                    name: name.to_string(),
                },
            });
        }
    }

    match trimmed {
        "void" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        }),
        "int" => Ok(profile_or_default_int_type(
            "int", "int", true, 32, target_abi,
        )),
        "signed char" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "signed char".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        }),
        "int8_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int8_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        }),
        "int16_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int16_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 16,
            },
        }),
        "int32_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int32_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 32,
            },
        }),
        "int64_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int64_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 64,
            },
        }),
        "uint16_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "uint16_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 16,
            },
        }),
        "unsigned int" => Ok(profile_or_default_int_type(
            "unsigned int",
            "unsigned int",
            false,
            32,
            target_abi,
        )),
        "uint32_t" => Ok(ClangTypeSkeleton {
            spelled: qual_type.trim().to_string(),
            canonical: "uint32_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 32,
            },
        }),
        "unsigned char" | "uint8_t" => Ok(ClangTypeSkeleton {
            spelled: qual_type.trim().to_string(),
            canonical: "uint8_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 8,
            },
        }),
        "uint64_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "uint64_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        }),
        "char" | "short" | "unsigned short" | "long" | "unsigned long" | "long long"
        | "unsigned long long" | "size_t" | "__size_t" => Ok(
            target_dependent_integer_type_with_profile(trimmed, target_abi),
        ),
        other => Ok(ClangTypeSkeleton {
            spelled: other.to_string(),
            canonical: other.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!("{other} is outside the current type skeleton"),
            },
        }),
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn profile_or_default_int_type(
    spelling: &str,
    canonical: &str,
    signed: bool,
    default_width: u16,
    target_abi: Option<&TargetAbiProfile>,
) -> ClangTypeSkeleton {
    let width = match target_abi {
        Some(abi) => match nonzero_width(abi.int_width) {
            Some(width) => width,
            None => {
                return ClangTypeSkeleton {
                    spelled: spelling.to_string(),
                    canonical: canonical.to_string(),
                    kind: ClangTypeKind::Unsupported {
                        reason: format!(
                            "{spelling} requires an explicit target ABI int_width before typed IR lowering"
                        ),
                    },
                };
            }
        },
        None => default_width,
    };

    ClangTypeSkeleton {
        spelled: spelling.to_string(),
        canonical: canonical.to_string(),
        kind: ClangTypeKind::Integer { signed, width },
    }
}

#[cfg(feature = "typed-ir")]
pub(super) fn target_dependent_integer_type_with_profile(
    spelling: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> ClangTypeSkeleton {
    if let Some((signed, width)) = target_dependent_integer_width(spelling, target_abi) {
        return ClangTypeSkeleton {
            spelled: spelling.to_string(),
            canonical: spelling.to_string(),
            kind: ClangTypeKind::Integer { signed, width },
        };
    }

    ClangTypeSkeleton {
        spelled: spelling.to_string(),
        canonical: spelling.to_string(),
        kind: ClangTypeKind::Unsupported {
            reason: if target_abi.is_some() {
                format!(
                    "{spelling} requires an explicit target ABI width field before typed IR lowering"
                )
            } else {
                format!("{spelling} requires target ABI width provenance before typed IR lowering")
            },
        },
    }
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
            ..
        } => {
            bind_target_abi_to_type(arg_type, target_abi);
            *alignment_bits = target_abi_alignment_bits_for_type(arg_type, target_abi);
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
