use std::collections::{HashMap, HashSet};
use std::hash::Hash;

use super::{
    assignment_call_sibling_record_read, emit_function_pointer_param_type,
    emit_mutable_record_pointer_field_type, emit_scalar_type, interior_reborrow_decl_parts,
    mutable_pointer_slice_element_type, mutable_record_pointer_pointee_type,
    record_pointer_member_path_from_expr, record_pointer_member_path_key, type_label, EmitContext,
    InteriorReborrowPlan, IrExpr, IrFunction, IrGlobal, IrStmt, IrType, MutablePointerSlotKey,
    MutableRecordPointerFieldKey,
};

#[derive(Clone, Debug, Default)]
struct DefiniteAssignmentState {
    declared: HashSet<String>,
    initialized: HashSet<String>,
    mutable_pointer_write_params: HashSet<String>,
    mutable_pointer_slots: HashSet<MutablePointerSlotKey>,
    validated_mutable_pointer_read_slots: HashSet<MutablePointerSlotKey>,
    mutable_record_pointer_write_params: HashSet<String>,
    interior_reborrows: HashMap<String, InteriorReborrowPlan>,
    mutable_record_pointer_fields: HashSet<MutableRecordPointerFieldKey>,
    validated_mutable_record_pointer_read_fields: HashSet<MutableRecordPointerFieldKey>,
}

#[derive(Clone, Debug, Default)]
pub(super) struct DefiniteAssignmentEvidence {
    pub(super) mutable_record_pointer_read_fields: HashSet<MutableRecordPointerFieldKey>,
    pub(super) mutable_pointer_read_slots: HashSet<MutablePointerSlotKey>,
}

impl DefiniteAssignmentState {
    fn from_function_and_globals(
        function: &IrFunction,
        globals: &[IrGlobal],
        context: &EmitContext,
    ) -> Self {
        let mut state = Self {
            mutable_pointer_write_params: context.mutable_pointer_write_params.clone(),
            mutable_record_pointer_write_params: context
                .mutable_record_pointer_write_params
                .clone(),
            interior_reborrows: context.interior_reborrows.clone(),
            ..Self::default()
        };
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

    fn assign_mutable_pointer_slot(&mut self, key: MutablePointerSlotKey) {
        self.mutable_pointer_slots.insert(key);
    }

    fn require_mutable_pointer_slot_initialized(
        &mut self,
        key: &MutablePointerSlotKey,
    ) -> Result<(), String> {
        if !self.mutable_pointer_slots.contains(key) {
            return Err(format!(
                "mutable pointer slot {}[0] is read before definite assignment",
                key.base
            ));
        }
        self.validated_mutable_pointer_read_slots
            .insert(key.clone());
        Ok(())
    }

    fn assign_mutable_record_pointer_field(&mut self, key: MutableRecordPointerFieldKey) {
        self.mutable_record_pointer_fields.insert(key);
    }

    fn require_mutable_record_pointer_field_initialized(
        &mut self,
        key: &MutableRecordPointerFieldKey,
    ) -> Result<(), String> {
        let initialized_call_root = self
            .interior_reborrows
            .values()
            .any(|plan| plan.call_root.as_deref() == Some(key.base.as_str()));
        let entry_initialized_reborrow_path = self.interior_reborrows.values().any(|plan| {
            plan.entry_initialized_field_path
                .as_ref()
                .is_some_and(|field_path| {
                    key.base == plan.owner
                        && key.field
                            == format!("{}.{}", plan.owner_path.join("."), field_path.join("."))
                })
        });
        let owner_sibling_size_add_read = self.interior_reborrows.values().any(|plan| {
            plan.allows_owner_sibling_size_add_read
                && key.base == plan.owner
                && key
                    .field
                    .strip_prefix(&format!("{}.", plan.owner_path.join(".")))
                    .is_some_and(|field| !field.is_empty() && !field.contains('.'))
        });
        if !self.mutable_record_pointer_fields.contains(key)
            && !initialized_call_root
            && !entry_initialized_reborrow_path
            && !owner_sibling_size_add_read
        {
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
) -> Result<DefiniteAssignmentEvidence, String> {
    let mut state = DefiniteAssignmentState::from_function_and_globals(function, globals, context);
    validate_definite_assignment_body(&function.body, &mut state)?;
    Ok(DefiniteAssignmentEvidence {
        mutable_record_pointer_read_fields: state.validated_mutable_record_pointer_read_fields,
        mutable_pointer_read_slots: state.validated_mutable_pointer_read_slots,
    })
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
