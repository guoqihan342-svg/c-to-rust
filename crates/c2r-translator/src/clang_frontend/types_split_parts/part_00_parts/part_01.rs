
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
        "bool" | "_Bool" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "_Bool".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 8,
            },
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
