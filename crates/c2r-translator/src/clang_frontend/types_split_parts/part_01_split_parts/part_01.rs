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
