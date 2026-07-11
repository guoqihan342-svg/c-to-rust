#[allow(clippy::result_large_err)]
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<EmittedRust, IrEmitError> {
    emit_scalar_rust_from_ir(function)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}

#[allow(clippy::result_large_err)]
/// Emits Rust for typed IR with readonly globals, preserving fail-closed errors.
///
/// This is the public typed-IR generation boundary used by clang-lowered
/// translation. Unsupported IR does not fall back to legacy templates; it is
/// returned as an `IrEmitError` with the same route metadata used by evidence
/// gates.
pub fn emit_rust_from_ir_with_globals(
    function: &IrFunction,
    globals: &[IrGlobal],
) -> Result<EmittedRust, IrEmitError> {
    emit_rust_from_ir_with_globals_and_policy(function, globals, EmitPolicy::default())
}

#[allow(clippy::result_large_err)]
pub fn emit_rust_from_ir_with_globals_and_policy(
    function: &IrFunction,
    globals: &[IrGlobal],
    policy: EmitPolicy,
) -> Result<EmittedRust, IrEmitError> {
    emit_scalar_rust_from_ir_with_globals_and_policy(function, globals, policy)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}

fn emit_scalar_rust_from_ir(function: &IrFunction) -> Result<String, String> {
    emit_scalar_rust_from_ir_with_globals(function, &[])
}

fn emit_scalar_rust_from_ir_with_globals(
    function: &IrFunction,
    globals: &[IrGlobal],
) -> Result<String, String> {
    emit_scalar_rust_from_ir_with_globals_and_policy(function, globals, EmitPolicy::default())
}

/// Lowers the supported scalar subset into one Rust function plus constants.
///
/// The function first builds the semantic emission context and runs
/// fail-closed validation, then emits globals, record definitions, parameters,
/// and statements. Anything outside the current typed IR contract returns a
/// path-rich error before a partial Rust candidate can escape.
fn emit_scalar_rust_from_ir_with_globals_and_policy(
    function: &IrFunction,
    globals: &[IrGlobal],
    policy: EmitPolicy,
) -> Result<String, String> {
    let return_type = emit_function_return_type(function)?;
    if return_type.is_some() && !ends_with_return_value(&function.body) {
        return Err("non-void function must end with a return value".to_string());
    }
    let mut context = EmitContext::from_function_and_globals_and_policy(function, globals, policy)?;
    let definite_assignment = validate_definite_assignment(function, globals, &context)?;
    context.mutable_record_pointer_read_fields =
        definite_assignment.mutable_record_pointer_read_fields;
    context.mutable_pointer_read_slots = definite_assignment.mutable_pointer_read_slots;
    let returned_mutable_param = returned_mutable_record_pointer_param(function, &context)?;
    let explicit_return_lifetime =
        returned_mutable_param.filter(|_| emitted_borrow_param_count(function, &context) > 1);
    let function_name = emit_identifier(&function.name, "function")?;
    let params = function
        .params
        .iter()
        .map(|param| {
            let explicit_lifetime = explicit_return_lifetime
                .filter(|returned_param| *returned_param == param.name.as_str())
                .map(|_| "a");
            emit_param(
                param,
                &context.assigned_vars,
                &context,
                explicit_lifetime,
            )
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    let mut symbols = collect_param_symbols(&function.params)?;

    let mut rust = String::new();
    for global in globals {
        rust.push_str(&emit_global_const(global)?);
    }
    if !globals.is_empty() {
        rust.push('\n');
    }
    let record_definitions = emit_record_definitions(function, &context)?;
    for definition in &record_definitions {
        rust.push_str(definition);
    }
    if !record_definitions.is_empty() {
        rust.push('\n');
    }
    let function_lifetime = if explicit_return_lifetime.is_some() {
        "<'a>"
    } else {
        ""
    };
    rust.push_str(&format!("pub fn {function_name}{function_lifetime}({params})"));
    if let Some(mut return_type) = return_type {
        if explicit_return_lifetime.is_some() {
            return_type = add_explicit_borrow_lifetime(&return_type, "a")
                .map_err(|detail| format!("return type {detail}"))?;
        }
        rust.push_str(&format!(" -> {}", return_type));
    }
    rust.push_str(" {\n");
    for (index, stmt) in function.body.iter().enumerate() {
        if let Some(line) = emit_interior_reborrow_decl(stmt, 1, &mut symbols, &context)
            .map_err(|detail| format!("stmt[{index}].{detail}"))?
        {
            rust.push_str(&line);
            continue;
        }
        let line = emit_stmt(
            stmt,
            &function.return_type,
            1,
            &mut symbols,
            &context,
            LoopContext::None,
        )
        .map_err(|detail| format!("stmt[{index}].{detail}"))?;
        rust.push_str(&line);
    }
    rust.push_str("}\n");
    Ok(rust)
}
