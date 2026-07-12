fn emit_record_memset_statement(
    destination: &IrExpr,
    byte: u8,
    write_len_bytes: u64,
    layout: &IrRecordLayoutBinding,
    symbols: &HashSet<String>,
) -> Result<String, String> {
    let (name, pointee) = validate_record_memset_binding(
        destination,
        byte,
        write_len_bytes,
        layout,
    )?;
    let name = emit_identifier(name, "C record memset destination")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C record memset destination {name} is not a function parameter or local binding"
        ));
    }
    let initializer = emit_record_byte_zero_initializer(pointee)?;
    Ok(format!(
        "*{name} = {initializer}; /* compiler-bound C object size: {write_len_bytes} bytes */"
    ))
}

fn validate_record_memset_binding<'a>(
    destination: &'a IrExpr,
    byte: u8,
    write_len_bytes: u64,
    layout: &IrRecordLayoutBinding,
) -> Result<(&'a str, &'a IrType), String> {
    let IrExpr::Var { name, ty, .. } = destination else {
        return Err("C record memset destination must be a direct parameter".to_string());
    };
    let pointee = mutable_record_pointer_pointee_type(ty).ok_or_else(|| {
        format!(
            "C record memset destination is not a mutable record pointer: {}",
            type_label(ty)
        )
    })?;
    let IrTypeKind::Record {
        name: record_name,
        fields: Some(fields),
    } = &pointee.kind
    else {
        return Err("C record memset destination requires complete field inventory".to_string());
    };
    if fields.is_empty() {
        return Err(format!("C record memset destination {record_name} has no fields"));
    }
    if byte != 0 {
        return Err("C record memset supports only a zero byte value".to_string());
    }
    validate_record_layout_binding(layout, record_name, write_len_bytes)?;
    validate_record_byte_zero_type(pointee, record_name)?;
    Ok((name, pointee))
}

fn validate_record_layout_binding(
    layout: &IrRecordLayoutBinding,
    record_name: &str,
    write_len_bytes: u64,
) -> Result<(), String> {
    let hash_is_valid = |value: &str| {
        value.len() == 64
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    };
    if layout.record_type != format!("struct {record_name}")
        || layout.size_bytes == 0
        || layout.size_bytes != write_len_bytes
        || layout.align_bytes == 0
        || !layout.align_bytes.is_power_of_two()
        || !layout.size_bytes.is_multiple_of(layout.align_bytes)
        || !hash_is_valid(&layout.dump_sha256)
        || !hash_is_valid(&layout.diagnostics_sha256)
        || !hash_is_valid(&layout.compile_arguments_sha256)
        || !hash_is_valid(&layout.compile_database_sha256)
        || layout.target_abi.triple_or_abi.trim().is_empty()
        || layout.target_abi.char_width != 8
        || layout.target_abi.int_width == 0
        || layout.target_abi.pointer_width == 0
    {
        return Err(
            "C record memset layout provenance is incomplete, mismatched, or malformed"
                .to_string(),
        );
    }
    Ok(())
}

fn validate_record_byte_zero_type(ty: &IrType, path: &str) -> Result<(), String> {
    match &ty.kind {
        IrTypeKind::Integer { .. } => Ok(()),
        IrTypeKind::Array {
            element,
            len: Some(len),
        } if *len > 0 => validate_record_byte_zero_type(element, path),
        IrTypeKind::Record {
            name,
            fields: Some(fields),
        } if !fields.is_empty() => {
            for field in fields {
                validate_record_byte_zero_type(&field.ty, &format!("{path}.{}", field.name))?;
            }
            let _ = emit_record_type_name(name)?;
            Ok(())
        }
        _ => Err(format!(
            "C record memset field {path} has non-zero-safe type {}",
            type_label(ty)
        )),
    }
}

fn emit_record_byte_zero_initializer(ty: &IrType) -> Result<String, String> {
    match &ty.kind {
        IrTypeKind::Integer { .. } => emit_integer_literal(0, ty),
        IrTypeKind::Array {
            element,
            len: Some(len),
        } if *len > 0 => Ok(format!(
            "[{}; {len}]",
            emit_record_byte_zero_initializer(element)?
        )),
        IrTypeKind::Record {
            name,
            fields: Some(fields),
        } if !fields.is_empty() => {
            let rust_name = emit_record_type_name(name)?;
            let fields = fields
                .iter()
                .map(|field| {
                    Ok(format!(
                        "{}: {}",
                        emit_identifier(&field.name, "record memset field")?,
                        emit_record_byte_zero_initializer(&field.ty)?
                    ))
                })
                .collect::<Result<Vec<_>, String>>()?
                .join(", ");
            Ok(format!("{rust_name} {{ {fields} }}"))
        }
        _ => Err(format!(
            "C record memset zero initializer rejects type {}",
            type_label(ty)
        )),
    }
}
