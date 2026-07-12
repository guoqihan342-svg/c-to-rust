fn collect_opaque_pointer_call_arg_params_from_stmt(
    stmt: &IrStmt,
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                collect_opaque_pointer_call_arg_params_from_expr(
                    init,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrStmt::Assign { target, value, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(target, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(value, param_types, call_arg_params);
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_body(
                then_body,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_body(
                else_body,
                param_types,
                call_arg_params,
            );
        }
        IrStmt::While {
            condition, body, ..
        } => {
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_body(body, param_types, call_arg_params);
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            collect_opaque_pointer_call_arg_params_from_body(body, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            collect_opaque_pointer_call_arg_params_from_body(init, param_types, call_arg_params);
            if let Some(condition) = condition {
                collect_opaque_pointer_call_arg_params_from_expr(
                    condition,
                    param_types,
                    call_arg_params,
                );
            }
            if let Some(step) = step.as_deref() {
                collect_opaque_pointer_call_arg_params_from_stmt(
                    step,
                    param_types,
                    call_arg_params,
                );
            }
            collect_opaque_pointer_call_arg_params_from_body(body, param_types, call_arg_params);
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                collect_opaque_pointer_call_arg_params_from_expr(
                    value,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrStmt::Expr { expr, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(expr, param_types, call_arg_params);
        }
        IrStmt::RecordMemset { .. } => {}
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}

fn collect_opaque_pointer_call_arg_params_from_expr(
    expr: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    call_arg_params: &mut HashSet<String>,
) {
    match expr {
        IrExpr::Call { args, .. } => {
            for arg in args {
                if let IrExpr::Var { name, ty, .. } = arg {
                    if let Some(param_ty) = param_types.get(name.as_str()) {
                        if opaque_void_pointer_call_arg_types_match(param_ty, ty) {
                            call_arg_params.insert(name.clone());
                        }
                    }
                }
                collect_opaque_pointer_call_arg_params_from_expr(arg, param_types, call_arg_params);
            }
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(lhs, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(rhs, param_types, call_arg_params);
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. }
        | IrExpr::Member { base: operand, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(operand, param_types, call_arg_params);
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_opaque_pointer_call_arg_params_from_expr(
                condition,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_expr(
                then_expr,
                param_types,
                call_arg_params,
            );
            collect_opaque_pointer_call_arg_params_from_expr(
                else_expr,
                param_types,
                call_arg_params,
            );
        }
        IrExpr::Index { base, index, .. } => {
            collect_opaque_pointer_call_arg_params_from_expr(base, param_types, call_arg_params);
            collect_opaque_pointer_call_arg_params_from_expr(index, param_types, call_arg_params);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_opaque_pointer_call_arg_params_from_expr(
                    element,
                    param_types,
                    call_arg_params,
                );
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn opaque_void_pointer_call_arg_types_match(param_ty: &IrType, arg_ty: &IrType) -> bool {
    emit_opaque_void_pointer_type(param_ty).is_some()
        && emit_opaque_void_pointer_type(arg_ty).is_some()
        && pointer_types_match_ignoring_spelling(param_ty, arg_ty)
}

fn pointer_types_match_ignoring_spelling(lhs: &IrType, rhs: &IrType) -> bool {
    lhs.canonical == rhs.canonical && lhs.kind == rhs.kind && lhs.is_const == rhs.is_const
}

fn collect_raw_direct_call_pointer_params(body: &[IrStmt], params: &[IrParam]) -> HashSet<String> {
    let param_types: HashMap<&str, &IrType> = params
        .iter()
        .map(|param| (param.name.as_str(), &param.ty))
        .collect();
    let mut call_arg_params = HashSet::new();
    collect_raw_direct_call_pointer_params_from_body(body, &param_types, &mut call_arg_params);
    call_arg_params
}
