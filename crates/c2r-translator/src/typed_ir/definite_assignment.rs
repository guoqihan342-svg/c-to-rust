use std::collections::HashSet;
use std::hash::Hash;

use super::{
    emit_function_pointer_param_type, emit_mutable_record_pointer_field_type, emit_scalar_type,
    mutable_record_pointer_pointee_type, type_label, EmitContext, IrExpr, IrFunction, IrGlobal,
    IrStmt, IrType, MutableRecordPointerFieldKey,
};

#[derive(Clone, Debug, Default)]
struct DefiniteAssignmentState {
    declared: HashSet<String>,
    initialized: HashSet<String>,
    mutable_record_pointer_write_params: HashSet<String>,
    mutable_record_pointer_fields: HashSet<MutableRecordPointerFieldKey>,
    validated_mutable_record_pointer_read_fields: HashSet<MutableRecordPointerFieldKey>,
}

impl DefiniteAssignmentState {
    fn from_function_and_globals(
        function: &IrFunction,
        globals: &[IrGlobal],
        context: &EmitContext,
    ) -> Self {
        let mut state = Self::default();
        state.mutable_record_pointer_write_params =
            context.mutable_record_pointer_write_params.clone();
        for param in &function.params {
            state.declared.insert(param.name.clone());
            state.initialized.insert(param.name.clone());
        }
        for global in globals {
            state.declared.insert(global.name.clone());
            state.initialized.insert(global.name.clone());
        }
        state
    }

    fn declare(&mut self, name: &str, initialized: bool) -> Result<(), String> {
        if self.declared.contains(name) {
            return Err(format!("decl {name} duplicates an existing symbol"));
        }
        self.declared.insert(name.to_string());
        if initialized {
            self.initialized.insert(name.to_string());
        }
        Ok(())
    }

    fn assign(&mut self, name: &str) -> Result<(), String> {
        if !self.declared.contains(name) {
            return Err(format!("assign target {name} is not declared"));
        }
        self.initialized.insert(name.to_string());
        Ok(())
    }

    fn require_initialized(&self, name: &str) -> Result<(), String> {
        if !self.declared.contains(name) {
            return Err(format!("var {name} is not declared"));
        }
        if !self.initialized.contains(name) {
            return Err(format!("var {name} is read before assignment"));
        }
        Ok(())
    }

    fn assign_mutable_record_pointer_field(&mut self, key: MutableRecordPointerFieldKey) {
        self.mutable_record_pointer_fields.insert(key);
    }

    fn require_mutable_record_pointer_field_initialized(
        &mut self,
        key: &MutableRecordPointerFieldKey,
    ) -> Result<(), String> {
        if !self.mutable_record_pointer_fields.contains(key) {
            return Err(format!(
                "mutable record pointer field {}.{} is read before definite assignment",
                key.base, key.field
            ));
        }
        self.validated_mutable_record_pointer_read_fields
            .insert(key.clone());
        Ok(())
    }
}

pub(super) fn validate_definite_assignment(
    function: &IrFunction,
    globals: &[IrGlobal],
    context: &EmitContext,
) -> Result<HashSet<MutableRecordPointerFieldKey>, String> {
    let mut state = DefiniteAssignmentState::from_function_and_globals(function, globals, context);
    validate_definite_assignment_body(&function.body, &mut state)?;
    Ok(state.validated_mutable_record_pointer_read_fields)
}

fn validate_definite_assignment_body(
    body: &[IrStmt],
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    for (index, stmt) in body.iter().enumerate() {
        validate_definite_assignment_stmt(stmt, state)
            .map_err(|detail| format!("stmt[{index}].{detail}"))?;
    }
    Ok(())
}

fn validate_definite_assignment_labeled_body(
    body: &[IrStmt],
    state: &mut DefiniteAssignmentState,
    label: &str,
) -> Result<(), String> {
    for (index, stmt) in body.iter().enumerate() {
        validate_definite_assignment_stmt(stmt, state)
            .map_err(|detail| format!("{label}[{index}].{detail}"))?;
    }
    Ok(())
}

fn body_definitely_returns(body: &[IrStmt]) -> bool {
    body.iter().any(stmt_definitely_returns)
}

fn stmt_definitely_returns(stmt: &IrStmt) -> bool {
    match stmt {
        IrStmt::Return { .. } => true,
        IrStmt::If {
            then_body,
            else_body,
            ..
        } => {
            !else_body.is_empty()
                && body_definitely_returns(then_body)
                && body_definitely_returns(else_body)
        }
        IrStmt::Decl { .. }
        | IrStmt::Assign { .. }
        | IrStmt::While { .. }
        | IrStmt::DoWhile { .. }
        | IrStmt::For { .. }
        | IrStmt::Break { .. }
        | IrStmt::Continue { .. }
        | IrStmt::Expr { .. }
        | IrStmt::Unsupported { .. } => false,
    }
}

fn merge_definite_branch_set<T>(
    before: &HashSet<T>,
    then_set: &HashSet<T>,
    then_returns: bool,
    else_set: &HashSet<T>,
    else_returns: bool,
) -> HashSet<T>
where
    T: Clone + Eq + Hash,
{
    if then_returns && else_returns {
        return before.clone();
    }
    before
        .iter()
        .chain(then_set.iter())
        .chain(else_set.iter())
        .filter(|item| {
            before.contains(*item)
                || ((then_returns || then_set.contains(*item))
                    && (else_returns || else_set.contains(*item)))
        })
        .cloned()
        .collect()
}

/// Checks one statement against the emitter's conservative initialization model.
///
/// This pass is intentionally narrower than full C data-flow analysis. It only
/// carries facts that are definitely true on all non-returning paths, avoids
/// assuming loops execute, and treats mutable record-pointer fields as separate
/// facts so reads cannot be emitted before an observed write.
fn validate_definite_assignment_stmt(
    stmt: &IrStmt,
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { name, init, .. } => {
            if let Some(init) = init {
                validate_definite_assignment_expr(init, state)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
            }
            state.declare(name, init.is_some())
        }
        IrStmt::Assign { target, value, .. } => {
            let mutable_record_pointer_target =
                mutable_record_pointer_field_key_for_definite_assignment(target, state)?;
            let assigned_var = validate_definite_assignment_target(target, state)?;
            match &mutable_record_pointer_target {
                Some(target_key) => {
                    validate_definite_assignment_assign_value(value, state, target_key)
                        .map_err(|detail| format!("assign value {detail}"))?
                }
                None => validate_definite_assignment_expr(value, state)
                    .map_err(|detail| format!("assign value {detail}"))?,
            }
            if let Some(name) = assigned_var {
                state.assign(&name)?;
            }
            if let Some(key) = mutable_record_pointer_target {
                state.assign_mutable_record_pointer_field(key);
            }
            Ok(())
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                validate_definite_assignment_expr(value, state)
                    .map_err(|detail| format!("return expr {detail}"))?;
            }
            Ok(())
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } => Ok(()),
        IrStmt::Expr { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("expr {detail}")),
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("if condition {detail}"))?;
            let before = state.clone();
            let mut then_state = before.clone();
            validate_definite_assignment_labeled_body(then_body, &mut then_state, "if then")?;
            let mut else_state = before.clone();
            validate_definite_assignment_labeled_body(else_body, &mut else_state, "if else")?;
            let then_returns = body_definitely_returns(then_body);
            let else_returns = body_definitely_returns(else_body);

            state.initialized = merge_definite_branch_set(
                &before.initialized,
                &then_state.initialized,
                then_returns,
                &else_state.initialized,
                else_returns,
            );
            state
                .initialized
                .retain(|name| before.declared.contains(name));
            state.mutable_record_pointer_fields = merge_definite_branch_set(
                &before.mutable_record_pointer_fields,
                &then_state.mutable_record_pointer_fields,
                then_returns,
                &else_state.mutable_record_pointer_fields,
                else_returns,
            );
            state
                .validated_mutable_record_pointer_read_fields
                .extend(then_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_record_pointer_read_fields
                .extend(else_state.validated_mutable_record_pointer_read_fields);
            Ok(())
        }
        IrStmt::While {
            condition, body, ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("while condition {detail}"))?;
            let mut body_state = state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "while body")?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            Ok(())
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            let mut body_state = state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "do while body")?;
            validate_definite_assignment_expr(condition, &mut body_state)
                .map_err(|detail| format!("do while condition {detail}"))?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            Ok(())
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            let mut loop_state = state.clone();
            for (index, init) in init.iter().enumerate() {
                validate_definite_assignment_stmt(init, &mut loop_state)
                    .map_err(|detail| format!("for init[{index}] {detail}"))?;
            }
            if let Some(condition) = condition {
                validate_definite_assignment_expr(condition, &mut loop_state)
                    .map_err(|detail| format!("for condition {detail}"))?;
            }
            let loop_reads = loop_state
                .validated_mutable_record_pointer_read_fields
                .clone();
            let mut body_state = loop_state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "for body")?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(loop_reads);
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            if let Some(step) = step {
                let mut step_state = loop_state;
                validate_definite_assignment_stmt(step, &mut step_state)
                    .map_err(|detail| format!("for step {detail}"))?;
                state
                    .validated_mutable_record_pointer_read_fields
                    .extend(step_state.validated_mutable_record_pointer_read_fields);
            }
            Ok(())
        }
        IrStmt::Unsupported { .. } => Ok(()),
    }
}

fn validate_definite_assignment_target(
    target: &IrExpr,
    state: &mut DefiniteAssignmentState,
) -> Result<Option<String>, String> {
    match target {
        IrExpr::Var { name, ty, .. } if should_track_definite_assignment_type(ty) => {
            if !state.declared.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            Ok(Some(name.clone()))
        }
        IrExpr::Var { .. } => Ok(None),
        IrExpr::Index { base, index, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("assign index base {detail}"))?;
            validate_definite_assignment_expr(index, state)
                .map_err(|detail| format!("assign index operand {detail}"))?;
            Ok(None)
        }
        IrExpr::Deref { ptr, .. } => {
            validate_definite_assignment_expr(ptr, state)
                .map_err(|detail| format!("assign deref pointer {detail}"))?;
            Ok(None)
        }
        IrExpr::Member { base, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("assign member base {detail}"))?;
            Ok(None)
        }
        _ => Err(
            "assign target must be Var, local fixed array Index, pointer Deref, or by-value record Member"
                .to_string(),
        ),
    }
}

fn validate_definite_assignment_assign_value(
    value: &IrExpr,
    state: &mut DefiniteAssignmentState,
    target_key: &MutableRecordPointerFieldKey,
) -> Result<(), String> {
    if let IrExpr::Binary { lhs, rhs, .. } = value {
        if mutable_record_pointer_field_key_for_definite_assignment(lhs, state)?.as_ref()
            == Some(target_key)
        {
            return validate_definite_assignment_expr(rhs, state)
                .map_err(|detail| format!("binary rhs {detail}"));
        }
    }
    validate_definite_assignment_expr(value, state)
}

fn validate_definite_assignment_expr(
    expr: &IrExpr,
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. } if should_track_definite_assignment_type(ty) => {
            state.require_initialized(name)
        }
        IrExpr::Var { .. } => Ok(()),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_definite_assignment_expr(lhs, state)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            validate_definite_assignment_expr(rhs, state)
                .map_err(|detail| format!("binary rhs {detail}"))
        }
        IrExpr::Unary { operand, .. } => validate_definite_assignment_expr(operand, state)
            .map_err(|detail| format!("unary operand {detail}")),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("conditional condition {detail}"))?;
            validate_definite_assignment_expr(then_expr, state)
                .map_err(|detail| format!("conditional then {detail}"))?;
            validate_definite_assignment_expr(else_expr, state)
                .map_err(|detail| format!("conditional else {detail}"))
        }
        IrExpr::Cast { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("cast expr {detail}")),
        IrExpr::LValueToRValue { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("lvalue-to-rvalue expr {detail}")),
        IrExpr::ArrayToPointerDecay { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("array-to-pointer decay expr {detail}")),
        IrExpr::FunctionToPointerDecay { expr, .. } => {
            validate_definite_assignment_expr(expr, state)
                .map_err(|detail| format!("function-to-pointer decay expr {detail}"))
        }
        IrExpr::Index { base, index, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("index base {detail}"))?;
            validate_definite_assignment_expr(index, state)
                .map_err(|detail| format!("index operand {detail}"))
        }
        IrExpr::Member { base, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("member base {detail}"))?;
            if let Some(key) =
                mutable_record_pointer_field_key_for_definite_assignment(expr, state)?
            {
                state.require_mutable_record_pointer_field_initialized(&key)?;
            }
            Ok(())
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for (index, element) in elements.iter().enumerate() {
                validate_definite_assignment_expr(element, state)
                    .map_err(|detail| format!("array element[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::Call { callee, args, .. } => {
            if state.declared.contains(callee) {
                state
                    .require_initialized(callee)
                    .map_err(|detail| format!("call callee {detail}"))?;
            }
            for (index, arg) in args.iter().enumerate() {
                validate_definite_assignment_expr(arg, state)
                    .map_err(|detail| format!("call arg[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::IncDec { target, .. } => validate_definite_assignment_expr(target, state)
            .map_err(|detail| format!("inc/dec target {detail}")),
        IrExpr::Deref { ptr, .. } => validate_definite_assignment_expr(ptr, state)
            .map_err(|detail| format!("deref pointer {detail}")),
        IrExpr::AddrOf { operand, .. } => validate_definite_assignment_expr(operand, state)
            .map_err(|detail| format!("address-of operand {detail}")),
        IrExpr::LitInt { .. } | IrExpr::NullPtr { .. } | IrExpr::Unsupported { .. } => Ok(()),
    }
}

fn mutable_record_pointer_field_key_for_definite_assignment(
    expr: &IrExpr,
    state: &DefiniteAssignmentState,
) -> Result<Option<MutableRecordPointerFieldKey>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if !state.mutable_record_pointer_write_params.contains(name) {
        return Ok(None);
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "mutable record pointer field {name}.{field} has unsupported base type {}",
            type_label(base_ty)
        )
    })?;
    emit_mutable_record_pointer_field_type(ty)
        .map_err(|detail| format!("mutable record pointer field {name}.{field} has {detail}"))?;
    Ok(Some(MutableRecordPointerFieldKey {
        base: name.clone(),
        field: field.clone(),
    }))
}

fn should_track_definite_assignment_type(ty: &IrType) -> bool {
    emit_scalar_type(ty).is_ok() || matches!(emit_function_pointer_param_type(ty), Ok(Some(_)))
}
