/// Renders typed IR expressions as source-like text for evidence fields only.
///
/// The output is intentionally diagnostic, not a round-trippable C or Rust
/// emitter. Rust generation remains in `typed_ir`; this helper gives reviewers
/// stable labels for call arguments and pointer graph evidence.
fn ir_expr_source_text(expr: &typed_ir::IrExpr) -> String {
    match expr {
        typed_ir::IrExpr::Var { name, .. } => name.clone(),
        typed_ir::IrExpr::LitInt { spelling, .. } => spelling.clone(),
        typed_ir::IrExpr::NullPtr { .. } => "NULL".to_string(),
        typed_ir::IrExpr::Binary { op, lhs, rhs, .. } => format!(
            "({} {} {})",
            ir_expr_source_text(lhs),
            ir_bin_op_source(op),
            ir_expr_source_text(rhs)
        ),
        typed_ir::IrExpr::Unary { op, operand, .. } => {
            format!("({}{})", ir_un_op_source(op), ir_expr_source_text(operand))
        }
        typed_ir::IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => format!(
            "({} ? {} : {})",
            ir_expr_source_text(condition),
            ir_expr_source_text(then_expr),
            ir_expr_source_text(else_expr)
        ),
        typed_ir::IrExpr::Cast { target, expr, .. } => {
            format!("({} as {})", ir_expr_source_text(expr), ir_c_type(target))
        }
        typed_ir::IrExpr::LValueToRValue { expr, .. } => ir_expr_source_text(expr),
        typed_ir::IrExpr::ArrayToPointerDecay { expr, .. } => {
            format!("array_to_pointer_decay({})", ir_expr_source_text(expr))
        }
        typed_ir::IrExpr::FunctionToPointerDecay { expr, .. } => {
            format!("function_to_pointer_decay({})", ir_expr_source_text(expr))
        }
        typed_ir::IrExpr::Index { base, index, .. } => {
            format!(
                "{}[{}]",
                ir_expr_source_text(base),
                ir_expr_source_text(index)
            )
        }
        typed_ir::IrExpr::Member {
            base,
            field,
            is_arrow,
            ..
        } => {
            let op = if *is_arrow { "->" } else { "." };
            format!("{}{}{}", ir_member_base_source_text(base), op, field)
        }
        typed_ir::IrExpr::ArrayLiteral { elements, .. } => format!(
            "[{}]",
            elements
                .iter()
                .map(ir_expr_source_text)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        typed_ir::IrExpr::Call { callee, args, .. } => format!(
            "{callee}({})",
            args.iter()
                .map(ir_expr_source_text)
                .collect::<Vec<_>>()
                .join(", ")
        ),
        typed_ir::IrExpr::IncDec {
            target, op, prefix, ..
        } => {
            let marker = ir_inc_dec_op_source(op);
            let target = ir_expr_source_text(target);
            if *prefix {
                format!("{marker}{target}")
            } else {
                format!("{target}{marker}")
            }
        }
        typed_ir::IrExpr::Deref { ptr, .. } => format!("*{}", ir_expr_source_text(ptr)),
        typed_ir::IrExpr::AddrOf { operand, .. } => format!("&{}", ir_expr_source_text(operand)),
        typed_ir::IrExpr::MutableVoidPointerAddress { operand, .. } => {
            format!("(void *)&{}", ir_expr_source_text(operand))
        }
        typed_ir::IrExpr::Unsupported { node, .. } => format!("unsupported({node})"),
    }
}

fn ir_member_base_source_text(base: &typed_ir::IrExpr) -> String {
    let source = ir_expr_source_text(base);
    match base {
        typed_ir::IrExpr::Var { .. }
        | typed_ir::IrExpr::Call { .. }
        | typed_ir::IrExpr::Index { .. }
        | typed_ir::IrExpr::Member { .. } => source,
        _ => format!("({source})"),
    }
}

fn ir_bin_op_source(op: &typed_ir::IrBinOp) -> &'static str {
    match op {
        typed_ir::IrBinOp::Add => "+",
        typed_ir::IrBinOp::Sub => "-",
        typed_ir::IrBinOp::Mul => "*",
        typed_ir::IrBinOp::Div => "/",
        typed_ir::IrBinOp::Mod => "%",
        typed_ir::IrBinOp::BitAnd => "&",
        typed_ir::IrBinOp::BitOr => "|",
        typed_ir::IrBinOp::BitXor => "^",
        typed_ir::IrBinOp::Shl => "<<",
        typed_ir::IrBinOp::Shr => ">>",
        typed_ir::IrBinOp::Eq => "==",
        typed_ir::IrBinOp::Neq => "!=",
        typed_ir::IrBinOp::Lt => "<",
        typed_ir::IrBinOp::Le => "<=",
        typed_ir::IrBinOp::Gt => ">",
        typed_ir::IrBinOp::Ge => ">=",
        typed_ir::IrBinOp::LogAnd => "&&",
        typed_ir::IrBinOp::LogOr => "||",
        typed_ir::IrBinOp::Assign => "=",
        typed_ir::IrBinOp::Comma => ",",
    }
}

fn ir_un_op_source(op: &typed_ir::IrUnOp) -> &'static str {
    match op {
        typed_ir::IrUnOp::Neg => "-",
        typed_ir::IrUnOp::Not => "!",
        typed_ir::IrUnOp::BitNot => "~",
    }
}

fn ir_inc_dec_op_source(op: &typed_ir::IrIncDecOp) -> &'static str {
    match op {
        typed_ir::IrIncDecOp::Inc => "++",
        typed_ir::IrIncDecOp::Dec => "--",
    }
}

fn record_ir_type_mapping(
    symbol: &str,
    ty: &typed_ir::IrType,
    profile: &BuildProfile,
    result: &mut TranslationResult,
) {
    record_ir_type_mapping_with_rust_type_override(symbol, ty, profile, None, result);
}

fn record_ir_type_mapping_with_rust_type_override(
    symbol: &str,
    ty: &typed_ir::IrType,
    _profile: &BuildProfile,
    rust_type_override: Option<String>,
    result: &mut TranslationResult,
) {
    let c_type = ir_c_type(ty);
    let Some(rust_type) = rust_type_override.or_else(|| ir_rust_type(ty)) else {
        let reason = format!(
            "clang-lowered typed IR type {} is outside the current evidence mapping subset",
            type_label_for_evidence(ty)
        );
        result.type_map.uncertainties.push(TypeUncertainty {
            symbol: symbol.to_string(),
            c_type,
            reason: reason.clone(),
        });
        result.errors.push(TranslationError {
            kind: "type_uncertainty".to_string(),
            message: format!("{symbol}: {reason}"),
            source_span: Some(type_label_for_evidence(ty)),
        });
        return;
    };

    result.type_map.mappings.push(TypeMapping {
        c_type,
        rust_type,
        symbol: symbol.to_string(),
        reason: "clang-lowered typed IR mapping".to_string(),
    });
}

fn ir_rust_type(ty: &typed_ir::IrType) -> Option<String> {
    if let Ok(Some(function_pointer)) = typed_ir::emit_function_pointer_param_type(ty) {
        return Some(function_pointer);
    }
    match &ty.kind {
        typed_ir::IrTypeKind::Void => Some("()".to_string()),
        typed_ir::IrTypeKind::Integer { signed, width } => {
            if is_size_t_ir_type(ty) {
                return Some("usize".to_string());
            }
            match (*signed, *width) {
                (true, 8) => Some("i8".to_string()),
                (true, 16) => Some("i16".to_string()),
                (true, 32) => Some("i32".to_string()),
                (true, 64) => Some("i64".to_string()),
                (false, 8) => Some("u8".to_string()),
                (false, 16) => Some("u16".to_string()),
                (false, 32) => Some("u32".to_string()),
                (false, 64) => Some("u64".to_string()),
                _ => None,
            }
        }
        typed_ir::IrTypeKind::Pointer { pointee } => match &pointee.kind {
            typed_ir::IrTypeKind::Void => Some(if ty.is_const || pointee.is_const {
                "*const core::ffi::c_void".to_string()
            } else {
                "*mut core::ffi::c_void".to_string()
            }),
            typed_ir::IrTypeKind::Record { name, .. } => Some(if ty.is_const || pointee.is_const {
                format!("&{}", record_type_name_for_evidence(name))
            } else {
                format!("&mut {}", record_type_name_for_evidence(name))
            }),
            _ => ir_rust_type(pointee).map(|inner| {
                if ty.is_const || pointee.is_const {
                    format!("*const {inner}")
                } else {
                    format!("*mut {inner}")
                }
            }),
        },
        typed_ir::IrTypeKind::Array { element, len } => {
            ir_rust_type(element).map(|inner| match len {
                Some(len) => format!("[{inner}; {len}]"),
                None => format!("*const {inner}"),
            })
        }
        typed_ir::IrTypeKind::Record { name, .. } => Some(record_type_name_for_evidence(name)),
        typed_ir::IrTypeKind::Function | typed_ir::IrTypeKind::Unsupported { .. } => None,
    }
}

fn is_size_t_ir_type(ty: &typed_ir::IrType) -> bool {
    let spelled = ty.spelled.trim();
    let canonical = ty.canonical.trim();
    spelled == "size_t" || canonical == "size_t"
}

fn record_type_name_for_evidence(name: &str) -> String {
    let raw = name.trim().strip_prefix("struct ").unwrap_or(name.trim());
    let mut out = String::new();
    let mut uppercase_next = true;
    for ch in raw.chars() {
        if ch == '_' || ch == '-' || ch == ' ' {
            uppercase_next = true;
        } else if uppercase_next {
            out.extend(ch.to_uppercase());
            uppercase_next = false;
        } else {
            out.push(ch);
        }
    }
    if out.is_empty() {
        "Record".to_string()
    } else {
        out
    }
}

fn type_label_for_evidence(ty: &typed_ir::IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        ty.spelled.clone()
    } else if !ty.canonical.trim().is_empty() {
        ty.canonical.clone()
    } else {
        format!("{:?}", ty.kind)
    }
}

fn ir_c_type(ty: &typed_ir::IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        return ty.spelled.clone();
    }
    if !ty.canonical.trim().is_empty() {
        return ty.canonical.clone();
    }
    match &ty.kind {
        typed_ir::IrTypeKind::Void => "void".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: false,
            width: 8,
        } => "uint8_t".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: false,
            width: 32,
        } => "uint32_t".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: false,
            width: 64,
        } => "size_t".to_string(),
        typed_ir::IrTypeKind::Integer {
            signed: true,
            width: 32,
        } => "int".to_string(),
        typed_ir::IrTypeKind::Pointer { pointee } => {
            let pointee_type = ir_c_type(pointee);
            if ty.is_const && !pointee_type.starts_with("const ") {
                format!("const {pointee_type} *")
            } else {
                format!("{pointee_type} *")
            }
        }
        typed_ir::IrTypeKind::Array { element, .. } => format!("{}[]", ir_c_type(element)),
        typed_ir::IrTypeKind::Record { name, .. } => format!("struct {name}"),
        typed_ir::IrTypeKind::Function => "function".to_string(),
        typed_ir::IrTypeKind::Unsupported { reason } => format!("unsupported:{reason}"),
        _ => ty.canonical.clone(),
    }
}
