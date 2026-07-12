fn expr_has_post_increment_byte_read(expr: &IrExpr, cursor: &str) -> bool {
    match expr {
        IrExpr::Deref { ptr, ty, .. } => is_u8(ty) && is_post_inc_var(ptr, cursor),
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_has_post_increment_byte_read(lhs, cursor)
                || expr_has_post_increment_byte_read(rhs, cursor)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => {
            expr_has_post_increment_byte_read(operand, cursor)
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || expr_has_post_increment_byte_read(then_expr, cursor)
                || expr_has_post_increment_byte_read(else_expr, cursor)
        }
        IrExpr::ArrayLiteral { elements, .. } => elements
            .iter()
            .any(|element| expr_has_post_increment_byte_read(element, cursor)),
        IrExpr::Index { base, index, .. } => {
            expr_has_post_increment_byte_read(base, cursor)
                || expr_has_post_increment_byte_read(index, cursor)
        }
        IrExpr::Member { base, .. } => expr_has_post_increment_byte_read(base, cursor),
        IrExpr::Call { args, .. } => args
            .iter()
            .any(|arg| expr_has_post_increment_byte_read(arg, cursor)),
        IrExpr::IncDec { target, .. } => expr_has_post_increment_byte_read(target, cursor),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn count_post_increment_byte_reads(expr: &IrExpr) -> usize {
    match expr {
        IrExpr::Deref { ptr, ty, .. } if is_u8(ty) && is_post_inc_expr(ptr) => 1,
        IrExpr::Deref { ptr, .. } => count_post_increment_byte_reads(ptr),
        IrExpr::Binary { lhs, rhs, .. } => {
            count_post_increment_byte_reads(lhs) + count_post_increment_byte_reads(rhs)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::MutableVoidPointerAddress { operand, .. } => {
            count_post_increment_byte_reads(operand)
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            count_post_increment_byte_reads(condition)
                + count_post_increment_byte_reads(then_expr)
                + count_post_increment_byte_reads(else_expr)
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            elements.iter().map(count_post_increment_byte_reads).sum()
        }
        IrExpr::Index { base, index, .. } => {
            count_post_increment_byte_reads(base) + count_post_increment_byte_reads(index)
        }
        IrExpr::Member { base, .. } => count_post_increment_byte_reads(base),
        IrExpr::Call { args, .. } => args.iter().map(count_post_increment_byte_reads).sum(),
        IrExpr::IncDec { target, .. } => count_post_increment_byte_reads(target),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => 0,
    }
}
