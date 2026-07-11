#[derive(Clone, Debug)]
struct RecordPointerMemberPath<'a> {
    root_name: &'a str,
    root_ty: &'a IrType,
    fields: Vec<&'a str>,
    ty: &'a IrType,
}

fn record_pointer_member_path_from_expr<'a>(
    expr: &'a IrExpr,
) -> Result<Option<RecordPointerMemberPath<'a>>, String> {
    match expr {
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow: true,
            ..
        } => {
            let IrExpr::Var {
                name,
                ty: root_ty,
                ..
            } = base.as_ref()
            else {
                if record_member_path_has_arrow(base) {
                    return Err(
                        "record pointer member path must not contain a second arrow or pointer member hop"
                            .to_string(),
                    );
                }
                return Ok(None);
            };
            let Some(record_ty) = record_pointer_pointee_type(root_ty) else {
                return Ok(None);
            };
            validate_declared_record_member(record_ty, field, ty, "record pointer member root")?;
            Ok(Some(RecordPointerMemberPath {
                root_name: name.as_str(),
                root_ty,
                fields: vec![field.as_str()],
                ty,
            }))
        }
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow: false,
            ..
        } => {
            let Some(mut path) = record_pointer_member_path_from_expr(base)? else {
                return Ok(None);
            };
            let Some(base_ty) = expr_type(base) else {
                return Err("nested record pointer member base type is unsupported".to_string());
            };
            if !matches!(base_ty.kind, IrTypeKind::Record { .. }) {
                return Err(format!(
                    "nested record pointer member base has unsupported type {}",
                    type_label(base_ty)
                ));
            }
            validate_declared_record_member(base_ty, field, ty, "nested record pointer member")?;
            path.fields.push(field.as_str());
            path.ty = ty;
            Ok(Some(path))
        }
        _ => Ok(None),
    }
}

fn record_member_path_has_arrow(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Member { is_arrow, base, .. } => *is_arrow || record_member_path_has_arrow(base),
        _ => false,
    }
}

fn validate_declared_record_member(
    record_ty: &IrType,
    field: &str,
    use_ty: &IrType,
    context: &str,
) -> Result<(), String> {
    let IrTypeKind::Record { name, fields } = &record_ty.kind else {
        return Err(format!(
            "{context} base has unsupported type {}",
            type_label(record_ty)
        ));
    };
    let Some(fields) = fields.as_ref() else {
        return Ok(());
    };
    let declared = fields.iter().find(|candidate| candidate.name == field).ok_or_else(|| {
        format!("{context} record {name} has no declared field {field}")
    })?;
    if !types_match_ignoring_spelling(use_ty, &declared.ty)
        && !propagated_const_record_member_matches(record_ty, use_ty, &declared.ty)
    {
        return Err(format!(
            "{context} field {name}.{field} type {} does not match declared type {}",
            type_label(use_ty),
            type_label(&declared.ty)
        ));
    }
    Ok(())
}

fn propagated_const_record_member_matches(
    record_ty: &IrType,
    use_ty: &IrType,
    declared_ty: &IrType,
) -> bool {
    if !record_ty.is_const || !use_ty.is_const || declared_ty.is_const {
        return false;
    }
    if strip_single_top_level_const(&use_ty.spelled).is_none() {
        return false;
    }
    let Some(use_canonical) = canonical_without_top_level_const(&use_ty.canonical) else {
        return false;
    };
    let declared_canonical = declared_ty.canonical.trim();
    !declared_canonical.is_empty()
        && !contains_type_qualifier(declared_canonical)
        && use_canonical == declared_canonical
        && use_ty.kind == declared_ty.kind
        && use_ty.width_bits == declared_ty.width_bits
}

fn strip_single_top_level_const(spelling: &str) -> Option<&str> {
    let rest = spelling.trim().strip_prefix("const ")?.trim_start();
    (!rest.is_empty() && !contains_type_qualifier(rest)).then_some(rest)
}

fn canonical_without_top_level_const(canonical: &str) -> Option<&str> {
    let canonical = canonical.trim();
    let canonical = canonical
        .strip_prefix("const ")
        .map(str::trim_start)
        .unwrap_or(canonical);
    (!canonical.is_empty() && !contains_type_qualifier(canonical)).then_some(canonical)
}

fn contains_type_qualifier(spelling: &str) -> bool {
    spelling
        .split(|ch: char| !ch.is_ascii_alphanumeric() && ch != '_')
        .any(|token| {
            matches!(
                token,
                "const" | "volatile" | "restrict" | "__restrict" | "__restrict__" | "_Atomic"
            )
        })
}

fn record_pointer_member_path_key(path: &RecordPointerMemberPath<'_>) -> String {
    path.fields.join(".")
}

fn emit_record_pointer_member_path(
    path: &RecordPointerMemberPath<'_>,
    root_label: &str,
    field_label: &str,
) -> Result<String, String> {
    let root = emit_identifier(path.root_name, root_label)?;
    let fields = path
        .fields
        .iter()
        .map(|field| emit_identifier(field, field_label))
        .collect::<Result<Vec<_>, _>>()?
        .join(".");
    Ok(format!("{root}.{fields}"))
}
