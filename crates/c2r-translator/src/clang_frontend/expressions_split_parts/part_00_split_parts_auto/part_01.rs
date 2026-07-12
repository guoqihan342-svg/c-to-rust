
#[cfg(feature = "typed-ir")]
fn string_literal_expr_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let spelling = string_field(expr, "value").ok_or_else(|| ClangFrontendError {
        kind: "invalid_string_literal".to_string(),
        message: "StringLiteral is missing value".to_string(),
    })?;
    let bytes = c_string_literal_bytes(&spelling)?;
    let element_ty = unsigned_char_type_skeleton();
    let ty = ClangTypeSkeleton {
        spelled: format!("const unsigned char[{}]", bytes.len()),
        canonical: format!("const unsigned char[{}]", bytes.len()),
        kind: ClangTypeKind::Array {
            element: Box::new(element_ty.clone()),
            len: Some(bytes.len()),
        },
    };
    let elements = bytes
        .into_iter()
        .map(|byte| ClangExprSkeleton::IntegerLiteral {
            value: u64::from(byte),
            spelling: byte.to_string(),
            ty: element_ty.clone(),
        })
        .collect();

    Ok(ClangExprSkeleton::ArrayLiteral { elements, ty })
}

#[cfg(feature = "typed-ir")]
fn unsigned_char_type_skeleton() -> ClangTypeSkeleton {
    ClangTypeSkeleton {
        spelled: "unsigned char".to_string(),
        canonical: "unsigned char".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 8,
        },
    }
}

#[cfg(feature = "typed-ir")]
fn c_string_literal_bytes(spelling: &str) -> Result<Vec<u8>, ClangFrontendError> {
    let literal = spelling.trim();
    let body = literal
        .strip_prefix('"')
        .and_then(|body| body.strip_suffix('"'))
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_string_literal".to_string(),
            message: format!("StringLiteral value {spelling:?} must be a quoted C string"),
        })?;
    let mut chars = body.chars().peekable();
    let mut bytes = Vec::new();

    while let Some(ch) = chars.next() {
        if ch != '\\' {
            if ch.is_ascii() {
                bytes.push(ch as u8);
                continue;
            }
            return Err(ClangFrontendError {
                kind: "unsupported_string_literal".to_string(),
                message: format!(
                    "non-ASCII string literal character U+{:04X} requires explicit encoding provenance",
                    ch as u32
                ),
            });
        }

        let escaped = chars.next().ok_or_else(|| ClangFrontendError {
            kind: "invalid_string_literal".to_string(),
            message: "StringLiteral ends with an incomplete escape".to_string(),
        })?;
        match escaped {
            'n' => bytes.push(b'\n'),
            'r' => bytes.push(b'\r'),
            't' => bytes.push(b'\t'),
            '0'..='7' => {
                let mut value = escaped.to_digit(8).unwrap();
                for _ in 0..2 {
                    let Some(next) = chars.peek().copied() else {
                        break;
                    };
                    let Some(digit) = next.to_digit(8) else {
                        break;
                    };
                    chars.next();
                    value = value * 8 + digit;
                }
                let byte = u8::try_from(value).map_err(|_| ClangFrontendError {
                    kind: "unsupported_string_literal".to_string(),
                    message: format!(
                        "octal escape value {value} exceeds the bounded byte string literal subset"
                    ),
                })?;
                bytes.push(byte);
            }
            'x' => {
                let mut value = 0u32;
                let mut saw_digit = false;
                while let Some(next) = chars.peek().copied() {
                    let Some(digit) = next.to_digit(16) else {
                        break;
                    };
                    chars.next();
                    value = value * 16 + digit;
                    saw_digit = true;
                }
                if !saw_digit {
                    return Err(ClangFrontendError {
                        kind: "invalid_string_literal".to_string(),
                        message: "hex string literal escape requires at least one digit"
                            .to_string(),
                    });
                }
                let byte = u8::try_from(value).map_err(|_| ClangFrontendError {
                    kind: "unsupported_string_literal".to_string(),
                    message: format!(
                        "hex escape value {value} exceeds the bounded byte string literal subset"
                    ),
                })?;
                bytes.push(byte);
            }
            '\\' => bytes.push(b'\\'),
            '"' => bytes.push(b'"'),
            '\'' => bytes.push(b'\''),
            '?' => bytes.push(b'?'),
            'a' => bytes.push(0x07),
            'b' => bytes.push(0x08),
            'f' => bytes.push(0x0c),
            'v' => bytes.push(0x0b),
            other => {
                return Err(ClangFrontendError {
                    kind: "unsupported_string_literal".to_string(),
                    message: format!(
                        "escape \\{other} is outside the bounded byte string literal subset"
                    ),
                });
            }
        }
    }

    bytes.push(0);
    Ok(bytes)
}

#[cfg(feature = "typed-ir")]
fn unary_expr_or_type_trait_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let name = string_field(expr, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_expr_or_type_trait_expr".to_string(),
        message: "UnaryExprOrTypeTraitExpr is missing name".to_string(),
    })?;
    if name != "sizeof" && name != "_Alignof" {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryExprOrTypeTraitExpr".to_string(),
            reason: format!("{name} requires explicit alignment/lowering support"),
        });
    }
    let arg_type_object = if let Some(arg_type) = expr.get("argType") {
        arg_type
    } else if let Some(inner) = expr.get("inner").and_then(Value::as_array) {
        let [operand] = inner.as_slice() else {
            return Err(ClangFrontendError {
                kind: format!("unsupported_{name}_operand"),
                message: format!(
                    "{name} expression requires exactly one typed clang operand before typed IR lowering"
                ),
            });
        };
        operand.get("type").ok_or_else(|| ClangFrontendError {
            kind: format!("unsupported_{name}_operand"),
            message: format!(
                "{name} expression operand is missing type.qualType before typed IR lowering"
            ),
        })?
    } else {
        return Err(ClangFrontendError {
            kind: "invalid_unary_expr_or_type_trait_expr".to_string(),
            message: format!("{name} type operand is missing argType.qualType"),
        });
    };
    if clang_type_candidate_spellings(arg_type_object)
        .iter()
        .any(|spelling| is_enum_qual_type_spelling(spelling))
    {
        let spelled = string_field(arg_type_object, "qualType")
            .or_else(|| string_field(arg_type_object, "desugaredQualType"))
            .or_else(|| string_field(arg_type_object, "canonicalQualType"))
            .unwrap_or_else(|| "enum".to_string());
        return Err(ClangFrontendError {
            kind: format!("unsupported_{name}_type"),
            message: format!(
                "{name}({spelled}) requires explicit C layout/ABI provenance before typed IR lowering"
            ),
        });
    }
    let arg_type = type_from_ast_type_object(arg_type_object, None)?;
    let supported_type = matches!(
        arg_type.kind,
        ClangTypeKind::Integer { .. }
            | ClangTypeKind::Array { .. }
            | ClangTypeKind::Pointer { .. }
            | ClangTypeKind::Unsupported { .. }
    ) || (name == "sizeof" && matches!(arg_type.kind, ClangTypeKind::Record { .. }));
    if !supported_type {
        return Err(ClangFrontendError {
            kind: format!("unsupported_{name}_type"),
            message: format!(
                "{name}({}) requires explicit C layout/ABI provenance before typed IR lowering",
                arg_type.spelled
            ),
        });
    }
    let ty = expr_type(expr)?;
    if name == "_Alignof" {
        Ok(ClangExprSkeleton::AlignOfType {
            arg_type,
            ty,
            alignment_bits: None,
            alignment_type_spellings: clang_type_candidate_spellings(arg_type_object),
        })
    } else {
        Ok(ClangExprSkeleton::SizeOfType {
            arg_type,
            ty,
            record_layout: None,
            target_abi: None,
        })
    }
}
