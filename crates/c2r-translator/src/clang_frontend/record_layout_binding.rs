#[cfg(feature = "typed-ir")]
fn bind_record_layouts_to_function_skeleton(
    function: &mut ClangFunctionSkeleton,
    dump: &RecordLayoutDump,
) -> Vec<ClangRecordLayoutBinding> {
    let mut used = BTreeMap::new();
    bind_record_layouts_to_stmts(&mut function.body, dump, &mut used);
    used.into_values().collect()
}

#[cfg(feature = "typed-ir")]
fn record_layout_bindings_from_function_ast(
    function: &Value,
    dump: &RecordLayoutDump,
) -> Vec<ClangRecordLayoutBinding> {
    fn visit(
        node: &Value,
        dump: &RecordLayoutDump,
        used: &mut BTreeMap<String, ClangRecordLayoutBinding>,
    ) {
        if string_field(node, "kind").as_deref() == Some("UnaryExprOrTypeTraitExpr")
            && string_field(node, "name").as_deref() == Some("sizeof")
        {
            let type_object = node.get("argType").or_else(|| {
                let [operand] = node.get("inner")?.as_array()?.as_slice() else {
                    return None;
                };
                operand.get("type")
            });
            if let Some(type_object) = type_object {
                for spelling in clang_type_candidate_spellings(type_object) {
                    let Some(name) = spelling.trim().strip_prefix("struct ") else {
                        continue;
                    };
                    let record_type = format!("struct {}", name.trim());
                    if let Some(layout) = dump.layouts.get(&record_type) {
                        used.entry(record_type.clone()).or_insert_with(|| {
                            record_layout_binding(record_type, layout, dump)
                        });
                        break;
                    }
                }
            }
        }
        if let Some(children) = node.get("inner").and_then(Value::as_array) {
            for child in children {
                visit(child, dump, used);
            }
        }
    }

    let mut used = BTreeMap::new();
    visit(function, dump, &mut used);
    used.into_values().collect()
}

#[cfg(feature = "typed-ir")]
fn record_layout_binding(
    record_type: String,
    layout: &ClangRecordLayout,
    dump: &RecordLayoutDump,
) -> ClangRecordLayoutBinding {
    ClangRecordLayoutBinding {
        record_type,
        size_bytes: layout.size_bytes,
        align_bytes: layout.align_bytes,
        dump_sha256: dump.dump_sha256.clone(),
        diagnostics_sha256: dump.diagnostics_sha256.clone(),
        compile_arguments_sha256: dump.compile_arguments_sha256.clone(),
        compile_database_sha256: dump.compile_database_sha256.clone(),
        target_abi: dump.target_abi.clone(),
    }
}

#[cfg(feature = "typed-ir")]
fn bind_record_layouts_to_stmts(
    statements: &mut [ClangStmtSkeleton],
    dump: &RecordLayoutDump,
    used: &mut BTreeMap<String, ClangRecordLayoutBinding>,
) {
    for statement in statements {
        match statement {
            ClangStmtSkeleton::Decl { init, .. } => {
                if let Some(init) = init {
                    bind_record_layouts_to_expr(init, dump, used);
                }
            }
            ClangStmtSkeleton::Assign { target, value }
            | ClangStmtSkeleton::CompoundAssign { target, value, .. } => {
                bind_record_layouts_to_expr(target, dump, used);
                bind_record_layouts_to_expr(value, dump, used);
            }
            ClangStmtSkeleton::If {
                condition,
                then_body,
                else_body,
            } => {
                bind_record_layouts_to_expr(condition, dump, used);
                bind_record_layouts_to_stmts(then_body, dump, used);
                bind_record_layouts_to_stmts(else_body, dump, used);
            }
            ClangStmtSkeleton::While { condition, body } => {
                bind_record_layouts_to_expr(condition, dump, used);
                bind_record_layouts_to_stmts(body, dump, used);
            }
            ClangStmtSkeleton::DoWhile { body, condition } => {
                bind_record_layouts_to_stmts(body, dump, used);
                bind_record_layouts_to_expr(condition, dump, used);
            }
            ClangStmtSkeleton::For {
                init,
                condition,
                step,
                body,
            } => {
                bind_record_layouts_to_stmts(init, dump, used);
                if let Some(condition) = condition {
                    bind_record_layouts_to_expr(condition, dump, used);
                }
                if let Some(step) = step {
                    bind_record_layouts_to_stmts(
                        std::slice::from_mut(step.as_mut()),
                        dump,
                        used,
                    );
                }
                bind_record_layouts_to_stmts(body, dump, used);
            }
            ClangStmtSkeleton::Return { value } => {
                if let Some(value) = value {
                    bind_record_layouts_to_expr(value, dump, used);
                }
            }
            ClangStmtSkeleton::Expr { expr } => {
                bind_record_layouts_to_expr(expr, dump, used);
            }
            ClangStmtSkeleton::Break
            | ClangStmtSkeleton::Continue
            | ClangStmtSkeleton::Unsupported { .. } => {}
        }
    }
}

#[cfg(feature = "typed-ir")]
fn bind_record_layouts_to_expr(
    expr: &mut ClangExprSkeleton,
    dump: &RecordLayoutDump,
    used: &mut BTreeMap<String, ClangRecordLayoutBinding>,
) {
    if let ClangExprSkeleton::SizeOfType {
        arg_type,
        record_layout,
        ..
    } = expr
    {
        if let ClangTypeKind::Record { name } = &arg_type.kind {
            let record_type = format!("struct {name}");
            if let Some(layout) = dump.layouts.get(&record_type) {
                let binding = record_layout_binding(record_type.clone(), layout, dump);
                *record_layout = Some(binding.clone());
                used.insert(record_type, binding);
            }
        }
    }

    match expr {
        ClangExprSkeleton::Binary { lhs, rhs, .. } => {
            bind_record_layouts_to_expr(lhs, dump, used);
            bind_record_layouts_to_expr(rhs, dump, used);
        }
        ClangExprSkeleton::Unary { operand, .. }
        | ClangExprSkeleton::AddrOf { operand, .. }
        | ClangExprSkeleton::MutableVoidPointerAddress { operand, .. } => {
            bind_record_layouts_to_expr(operand, dump, used);
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            bind_record_layouts_to_expr(condition, dump, used);
            bind_record_layouts_to_expr(then_expr, dump, used);
            bind_record_layouts_to_expr(else_expr, dump, used);
        }
        ClangExprSkeleton::IncDec { target, .. } => {
            bind_record_layouts_to_expr(target, dump, used);
        }
        ClangExprSkeleton::Deref { ptr, .. } => {
            bind_record_layouts_to_expr(ptr, dump, used);
        }
        ClangExprSkeleton::Cast { expr, .. }
        | ClangExprSkeleton::LValueToRValue { expr, .. }
        | ClangExprSkeleton::ArrayToPointerDecay { expr, .. }
        | ClangExprSkeleton::FunctionToPointerDecay { expr, .. } => {
            bind_record_layouts_to_expr(expr, dump, used);
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            bind_record_layouts_to_expr(base, dump, used);
            bind_record_layouts_to_expr(index, dump, used);
        }
        ClangExprSkeleton::ArrayLiteral { elements, .. } => {
            for element in elements {
                bind_record_layouts_to_expr(element, dump, used);
            }
        }
        ClangExprSkeleton::Call { args, .. } => {
            for arg in args {
                bind_record_layouts_to_expr(arg, dump, used);
            }
        }
        ClangExprSkeleton::Member { base, .. } => {
            bind_record_layouts_to_expr(base, dump, used);
        }
        ClangExprSkeleton::DeclRef { .. }
        | ClangExprSkeleton::IntegerLiteral { .. }
        | ClangExprSkeleton::SizeOfType { .. }
        | ClangExprSkeleton::AlignOfType { .. }
        | ClangExprSkeleton::NullPtr { .. }
        | ClangExprSkeleton::Unsupported { .. } => {}
    }
}
