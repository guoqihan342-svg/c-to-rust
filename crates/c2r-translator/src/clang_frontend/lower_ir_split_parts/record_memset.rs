#[cfg(feature = "typed-ir")]
fn lower_record_memset_statement(
    expr: &ClangExprSkeleton,
) -> Result<Option<IrStmt>, ClangFrontendError> {
    let ClangExprSkeleton::Call { callee, args, ty } = expr else {
        return Ok(None);
    };
    if callee != "memset" {
        return Ok(None);
    }
    let [destination, byte, count] = args.as_slice() else {
        return Ok(None);
    };
    let ClangExprSkeleton::DeclRef {
        ty: destination_ty,
        ..
    } = destination
    else {
        return Ok(None);
    };
    let Some(destination_record) = clang_mutable_record_pointer_record_name(destination_ty) else {
        return Ok(None);
    };

    let ClangExprSkeleton::IntegerLiteral { value: 0, .. } = byte else {
        return Err(record_memset_error(
            "record destination requires an integer literal zero byte value",
        ));
    };
    let ClangExprSkeleton::SizeOfType {
        arg_type,
        record_layout: Some(layout),
        target_abi,
        ..
    } = count
    else {
        return Err(record_memset_error(
            "record destination requires sizeof(record) with bound layout provenance",
        ));
    };
    let ClangTypeKind::Record { name: count_record } = &arg_type.kind else {
        return Err(record_memset_error(
            "record destination size argument must name the destination record type",
        ));
    };
    if destination_record != count_record {
        return Err(record_memset_error(&format!(
            "destination record {destination_record} does not match sizeof record {count_record}"
        )));
    }
    let size_bytes = record_layout_size_bytes(arg_type, target_abi.as_ref(), layout)?;
    let _ = lower_type(ty)?;
    Ok(Some(IrStmt::RecordMemset {
        destination: lower_expr(destination)?,
        byte: 0,
        write_len_bytes: size_bytes,
        layout: lower_record_layout_binding(layout),
        source_span: None,
    }))
}

#[cfg(feature = "typed-ir")]
fn lower_record_layout_binding(layout: &ClangRecordLayoutBinding) -> IrRecordLayoutBinding {
    IrRecordLayoutBinding {
        record_type: layout.record_type.clone(),
        size_bytes: layout.size_bytes,
        align_bytes: layout.align_bytes,
        dump_sha256: layout.dump_sha256.clone(),
        diagnostics_sha256: layout.diagnostics_sha256.clone(),
        compile_arguments_sha256: layout.compile_arguments_sha256.clone(),
        compile_database_sha256: layout.compile_database_sha256.clone(),
        target_abi: layout.target_abi.clone(),
    }
}

#[cfg(feature = "typed-ir")]
fn record_memset_error(message: &str) -> ClangFrontendError {
    ClangFrontendError {
        kind: "unsupported_record_memset".to_string(),
        message: format!("memset record zero-fill {message}"),
    }
}
