
#[cfg(feature = "typed-ir")]
fn type_alias_skeleton(
    name: &str,
    aliases: &TypeAliasInventory,
) -> Option<ClangTypeSkeleton> {
    let entry = aliases.by_name.get(name)?;
    Some(match entry {
        Ok(ty) => ClangTypeSkeleton {
            spelled: name.to_string(),
            canonical: ty.canonical.clone(),
            kind: ty.kind.clone(),
        },
        Err(reason) => ClangTypeSkeleton {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: reason.clone(),
            },
        },
    })
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

#[cfg(all(feature = "typed-ir", test))]
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
