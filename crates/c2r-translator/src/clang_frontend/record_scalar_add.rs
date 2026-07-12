#[cfg(feature = "typed-ir")]
pub fn lower_function_and_globals_from_clang_ast_json_value(
    ast: &Value,
    function_name: &str,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    lower_function_and_globals_from_clang_ast_json_value_with_target_abi(ast, function_name, None)
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
    ast: &Value,
    function_name: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    let mut used_record_layouts = Vec::new();
    lower_function_and_globals_from_clang_ast_json_value_with_context(
        ast,
        function_name,
        target_abi,
        None,
        &mut used_record_layouts,
    )
}

#[cfg(feature = "typed-ir")]
fn lower_function_and_globals_from_clang_ast_json_value_with_context(
    ast: &Value,
    function_name: &str,
    target_abi: Option<&TargetAbiProfile>,
    record_layout_dump: Option<&RecordLayoutDump>,
    used_record_layouts: &mut Vec<ClangRecordLayoutBinding>,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    let record_inventory = record_inventory_from_ast_with_target_abi(ast, target_abi);
    let enum_constant_inventory = enum_constant_inventory_from_ast(ast);
    let enum_type_inventory = enum_type_inventory_from_ast(ast, target_abi);
    let type_alias_inventory = type_alias_inventory_from_ast(ast, target_abi);
    let function = find_function_decl(ast, function_name).ok_or_else(|| ClangFrontendError {
        kind: "missing_function_decl".to_string(),
        message: format!("clang AST JSON does not contain FunctionDecl named {function_name}"),
    })?;
    if let Some(record_layout_dump) = record_layout_dump {
        *used_record_layouts =
            record_layout_bindings_from_function_ast(function, record_layout_dump);
    }
    validate_interior_reborrow_typedef_provenance(ast, function, target_abi)?;
    let mut function = function.clone();
    rewrite_enum_constant_decl_refs_to_integer_literals(&mut function, &enum_constant_inventory)?;
    let mut skeleton =
        function_skeleton_from_ast_with_aliases(&function, &type_alias_inventory, target_abi)?;
    rewrite_supported_enum_types_in_function_skeleton(&mut skeleton, &enum_type_inventory)?;
    if let Some(target_abi) = target_abi {
        bind_target_abi_to_function_skeleton(&mut skeleton, target_abi);
    }
    if let Some(record_layout_dump) = record_layout_dump {
        let bound = bind_record_layouts_to_function_skeleton(&mut skeleton, record_layout_dump);
        if !bound.is_empty() {
            *used_record_layouts = bound;
        }
    }
    let mut function_ir = lower_function_skeleton(&skeleton)?;
    attach_record_inventory_to_function(&mut function_ir, &record_inventory);
    validate_nested_record_scalar_adds(&function_ir)?;
    let globals = readonly_globals_from_ast(ast)?;

    Ok(LoweredFunctionWithGlobals {
        function_ir,
        globals,
    })
}

#[cfg(feature = "typed-ir")]
fn validate_nested_record_scalar_adds(function: &IrFunction) -> Result<(), ClangFrontendError> {
    validate_nested_record_scalar_add_stmt_list(function, &function.body)
}

#[cfg(feature = "typed-ir")]
fn validate_nested_record_scalar_add_stmt_list(
    function: &IrFunction,
    statements: &[IrStmt],
) -> Result<(), ClangFrontendError> {
    for statement in statements {
        match statement {
            IrStmt::Assign { target, value, .. } => {
                validate_nested_record_scalar_add(function, target, value)?;
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                validate_nested_record_scalar_add_stmt_list(function, then_body)?;
                validate_nested_record_scalar_add_stmt_list(function, else_body)?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                validate_nested_record_scalar_add_stmt_list(function, body)?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                validate_nested_record_scalar_add_stmt_list(function, init)?;
                if let Some(step) = step {
                    validate_nested_record_scalar_add_stmt_list(
                        function,
                        std::slice::from_ref(step.as_ref()),
                    )?;
                }
                validate_nested_record_scalar_add_stmt_list(function, body)?;
            }
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn validate_nested_record_scalar_add(
    function: &IrFunction,
    target: &IrExpr,
    value: &IrExpr,
) -> Result<(), ClangFrontendError> {
    let Some(target_path) = nested_mutable_record_target(target) else {
        return Ok(());
    };
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: result_ty,
        ..
    } = value
    else {
        return Ok(());
    };
    let Some(source) = direct_record_field_read(lhs) else {
        return Ok(());
    };
    if source.is_arrow {
        return record_scalar_add_error("record scalar add source must be a by-value record");
    }
    let Some((extent_name, extent_ty)) = direct_scalar_read(rhs) else {
        return record_scalar_add_error(
            "record scalar add extent must be a side-effect-free direct u32 scalar parameter read",
        );
    };

    validate_record_scalar_add_target(function, &target_path)?;
    validate_record_scalar_add_source(function, &source)?;
    validate_record_scalar_add_extent(function, extent_name, extent_ty)?;
    for (label, ty) in [
        ("target leaf", target_path.leaf_ty),
        ("source field", source.field_ty),
        ("extent", extent_ty),
        ("result", result_ty),
    ] {
        if !is_exact_u32(ty) {
            return record_scalar_add_error(&format!(
                "record scalar add {label} must have proven u32 type"
            ));
        }
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
struct NestedRecordTarget<'a> {
    root_name: &'a str,
    root_ty: &'a IrType,
    nested_field: &'a str,
    nested_ty: &'a IrType,
    leaf_field: &'a str,
    leaf_ty: &'a IrType,
}

#[cfg(feature = "typed-ir")]
fn nested_mutable_record_target(expr: &IrExpr) -> Option<NestedRecordTarget<'_>> {
    let IrExpr::Member {
        base,
        field: leaf_field,
        ty: leaf_ty,
        is_arrow: false,
        ..
    } = expr
    else {
        return None;
    };
    let IrExpr::Member {
        base,
        field: nested_field,
        ty: nested_ty,
        is_arrow: true,
        ..
    } = base.as_ref()
    else {
        return None;
    };
    let (root_name, root_ty) = direct_var(base)?;
    Some(NestedRecordTarget {
        root_name,
        root_ty,
        nested_field,
        nested_ty,
        leaf_field,
        leaf_ty,
    })
}

#[cfg(feature = "typed-ir")]
struct RecordFieldRead<'a> {
    root_name: &'a str,
    root_ty: &'a IrType,
    field: &'a str,
    field_ty: &'a IrType,
    is_arrow: bool,
}

#[cfg(feature = "typed-ir")]
fn direct_record_field_read(expr: &IrExpr) -> Option<RecordFieldRead<'_>> {
    let expr = lvalue_read_expr(expr)?;
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow,
        ..
    } = expr
    else {
        return None;
    };
    let (root_name, root_ty) = direct_var(base)?;
    matches!(
        root_ty.kind,
        IrTypeKind::Record { .. } | IrTypeKind::Pointer { .. }
    )
    .then_some(RecordFieldRead {
        root_name,
        root_ty,
        field,
        field_ty: ty,
        is_arrow: *is_arrow,
    })
}

#[cfg(feature = "typed-ir")]
fn direct_scalar_read(expr: &IrExpr) -> Option<(&str, &IrType)> {
    direct_var(lvalue_read_expr(expr)?)
}

#[cfg(feature = "typed-ir")]
fn lvalue_read_expr(expr: &IrExpr) -> Option<&IrExpr> {
    match expr {
        IrExpr::LValueToRValue { expr, .. } => Some(expr),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn direct_var(expr: &IrExpr) -> Option<(&str, &IrType)> {
    match expr {
        IrExpr::Var { name, ty, .. } => Some((name, ty)),
        IrExpr::LValueToRValue { expr, .. } => direct_var(expr),
        _ => None,
    }
}
