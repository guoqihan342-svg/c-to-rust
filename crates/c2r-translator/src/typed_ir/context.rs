#[derive(Clone, Debug, Default)]
struct EmitContext {
    policy: EmitPolicy,
    assigned_vars: HashSet<String>,
    byte_slice_params: HashSet<String>,
    byte_cursor_sources: HashMap<String, String>,
    nullable_pointer_params: HashSet<String>,
    readonly_pointer_read_params: HashSet<String>,
    readonly_pointer_mentioned_params: HashSet<String>,
    readonly_mutable_pointer_index_params: HashSet<String>,
    readonly_record_pointer_read_params: HashSet<String>,
    mutable_pointer_write_params: HashSet<String>,
    opaque_pointer_call_arg_params: HashSet<String>,
    raw_direct_call_pointer_params: HashSet<String>,
    mutable_record_pointer_write_params: HashSet<String>,
    record_pointer_field_value_params: HashSet<String>,
    mutable_record_pointer_read_fields: HashSet<MutableRecordPointerFieldKey>,
    assignment_call_sibling_record_read: Option<MutableRecordPointerFieldKey>,
    mutable_pointer_read_slots: HashSet<MutablePointerSlotKey>,
    zero_initialized_record_locals: HashSet<String>,
    interior_reborrows: HashMap<String, InteriorReborrowPlan>,
    readonly_globals: HashMap<String, IrGlobal>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct EmittedExpr {
    prelude: String,
    expr: String,
}

#[derive(Clone, Debug)]
struct RecordFieldUse<'a> {
    name: &'a str,
    ty: &'a IrType,
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct MutableRecordPointerFieldKey {
    base: String,
    field: String,
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct MutablePointerSlotKey {
    base: String,
}

#[derive(Clone, Debug, Default)]
struct ReadonlyPointerParamUses {
    read_params: HashSet<String>,
    mentioned_params: HashSet<String>,
}

impl EmitContext {
    fn from_function_and_globals_and_policy(
        function: &IrFunction,
        globals: &[IrGlobal],
        policy: EmitPolicy,
    ) -> Result<Self, String> {
        let assigned_vars = collect_assigned_vars(&function.body);
        let interior_reborrows = analyze_interior_reborrow(function, &policy)?;
        let byte_cursor_sources = collect_byte_cursor_sources(&function.body);
        let mut byte_slice_params = HashSet::new();
        for source in byte_cursor_sources.values() {
            if function
                .params
                .iter()
                .any(|param| param.name == *source && is_const_void_pointer(&param.ty))
            {
                byte_slice_params.insert(source.clone());
            }
        }
        let nullable_pointer_params =
            collect_nullable_pointer_params(&function.body, &function.params)?;
        let readonly_pointer_uses =
            collect_readonly_pointer_param_uses(&function.body, &function.params)?;
        validate_readonly_pointer_slice_lowering_evidence(
            &function.params,
            &byte_slice_params,
            &nullable_pointer_params,
            &readonly_pointer_uses.read_params,
            &readonly_pointer_uses.mentioned_params,
        )?;
        validate_mutable_pointer_write_alias_boundary(&function.body, &function.params, &policy)?;
        let mutable_pointer_params = function
            .params
            .iter()
            .filter(|param| mutable_pointer_slice_element_type(&param.ty).is_some())
            .map(|param| (param.name.as_str(), &param.ty))
            .collect::<HashMap<_, _>>();
        let mut mutable_pointer_write_params = HashSet::new();
        collect_mutable_pointer_write_params_from_body(
            &function.body,
            &mutable_pointer_params,
            &mut mutable_pointer_write_params,
        )?;
        let opaque_pointer_call_arg_params =
            collect_opaque_pointer_call_arg_params(&function.body, &function.params);
        let raw_direct_call_pointer_params =
            collect_raw_direct_call_pointer_params(&function.body, &function.params);
        let readonly_mutable_pointer_index_params =
            collect_readonly_mutable_pointer_index_params(
                &function.body,
                &function.params,
                &assigned_vars,
                &nullable_pointer_params,
                &mutable_pointer_write_params,
                &policy,
            )?;
        let mut mutable_record_pointer_write_params =
            collect_mutable_record_pointer_write_params(&function.body, &function.params, &policy)?;
        for plan in interior_reborrows.values() {
            mutable_record_pointer_write_params.insert(plan.owner.clone());
            mutable_record_pointer_write_params.insert(plan.alias.clone());
        }
        let readonly_record_pointer_array_index_params =
            collect_readonly_record_pointer_array_index_params(
                &function.body,
                &function.params,
                &assigned_vars,
                &nullable_pointer_params,
                &mutable_pointer_write_params,
                &mutable_record_pointer_write_params,
                &policy,
            )?;
        let mut readonly_record_pointer_read_params = collect_readonly_record_pointer_read_params(
            &function.body,
            &function.params,
            &mutable_record_pointer_write_params,
            &policy,
        )?;
        readonly_record_pointer_read_params.extend(readonly_record_pointer_array_index_params);
        let record_pointer_field_value_params =
            collect_record_pointer_field_value_params(
                &function.body,
                &function.params,
                &mutable_record_pointer_write_params,
            )?;
        let zero_initialized_record_locals =
            collect_zero_initialized_record_locals(&function.body)?;
        let mut readonly_globals = HashMap::new();
        for global in globals {
            if readonly_globals
                .insert(global.name.clone(), global.clone())
                .is_some()
            {
                return Err(format!(
                    "global {} duplicates an existing global",
                    global.name
                ));
            }
        }
        Ok(Self {
            policy,
            assigned_vars,
            byte_slice_params,
            byte_cursor_sources,
            nullable_pointer_params,
            readonly_pointer_read_params: readonly_pointer_uses.read_params,
            readonly_pointer_mentioned_params: readonly_pointer_uses.mentioned_params,
            readonly_mutable_pointer_index_params,
            readonly_record_pointer_read_params,
            mutable_pointer_write_params,
            opaque_pointer_call_arg_params,
            raw_direct_call_pointer_params,
            mutable_record_pointer_write_params,
            record_pointer_field_value_params,
            mutable_record_pointer_read_fields: HashSet::new(),
            assignment_call_sibling_record_read: None,
            mutable_pointer_read_slots: HashSet::new(),
            zero_initialized_record_locals,
            interior_reborrows,
            readonly_globals,
        })
    }

    fn is_assigned_var(&self, name: &str) -> bool {
        self.assigned_vars.contains(name)
    }

    fn byte_cursor_source(&self, cursor: &str) -> Option<&str> {
        self.byte_cursor_sources.get(cursor).map(String::as_str)
    }

    fn is_byte_slice_param(&self, name: &str) -> bool {
        self.byte_slice_params.contains(name)
    }

    fn is_nullable_pointer_param(&self, name: &str) -> bool {
        self.nullable_pointer_params.contains(name)
    }

    fn is_readonly_pointer_read_param(&self, name: &str) -> bool {
        self.readonly_pointer_read_params.contains(name)
    }

    fn is_readonly_pointer_mentioned_param(&self, name: &str) -> bool {
        self.readonly_pointer_mentioned_params.contains(name)
    }

    fn is_readonly_mutable_pointer_index_param(&self, name: &str) -> bool {
        self.readonly_mutable_pointer_index_params.contains(name)
    }

    fn is_readonly_record_pointer_read_param(&self, name: &str) -> bool {
        self.readonly_record_pointer_read_params.contains(name)
    }

    fn is_mutable_pointer_write_param(&self, name: &str) -> bool {
        self.mutable_pointer_write_params.contains(name)
    }

    fn is_mutable_record_pointer_write_param(&self, name: &str) -> bool {
        self.mutable_record_pointer_write_params.contains(name)
    }

    fn is_record_pointer_field_value_param(&self, name: &str) -> bool {
        self.record_pointer_field_value_params.contains(name)
    }

    fn is_opaque_pointer_call_arg_param(&self, name: &str) -> bool {
        self.opaque_pointer_call_arg_params.contains(name)
    }

    fn is_raw_direct_call_pointer_param(&self, name: &str) -> bool {
        self.raw_direct_call_pointer_params.contains(name)
    }

    fn is_zero_initialized_record_local(&self, name: &str) -> bool {
        self.zero_initialized_record_locals.contains(name)
    }

    fn interior_reborrow(&self, alias: &str) -> Option<&InteriorReborrowPlan> {
        self.interior_reborrows.get(alias)
    }

    fn is_mutable_record_pointer_read_field(&self, name: &str, field: &str) -> bool {
        let key = if let Some(plan) = self.interior_reborrow(name) {
            MutableRecordPointerFieldKey {
                base: plan.owner.clone(),
                field: format!("{}.{}", plan.owner_path.join("."), field),
            }
        } else {
            MutableRecordPointerFieldKey {
                base: name.to_string(),
                field: field.to_string(),
            }
        };
        self.mutable_record_pointer_read_fields.contains(&key)
    }

    fn is_assignment_call_sibling_record_read(&self, name: &str, field: &str) -> bool {
        self.assignment_call_sibling_record_read
            .as_ref()
            .is_some_and(|key| key.base == name && key.field == field)
    }

    fn is_mutable_pointer_read_slot(&self, name: &str) -> bool {
        self.mutable_pointer_read_slots
            .contains(&MutablePointerSlotKey {
                base: name.to_string(),
            })
    }

    fn readonly_global(&self, name: &str) -> Option<&IrGlobal> {
        self.readonly_globals.get(name)
    }

    fn global_rust_name(&self, name: &str) -> Result<String, String> {
        emit_global_const_identifier(name)
    }
}
