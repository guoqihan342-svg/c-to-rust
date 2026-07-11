#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_assignment_call_reborrow_run_once_emits_and_runs() {
    let function_name = "advance_projected_entry_once";
    let ast = assignment_call_reborrow_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower assignment-call reborrow carrier without clang");
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        assignment_call_reborrow_policy(),
    )
    .expect("emit assignment-call reborrow carrier");
    let rust = &emitted.rust;
    assert!(rust.contains("let cursor = &mut owner.current;"), "{rust}");
    assert!(
        rust.contains("cursor.nested.leaf = sample_next(source, &mut seed_local, cursor);"),
        "{rust}"
    );
    assert!(
        rust.contains("if (cursor.nested.leaf == 4294967295u32)"),
        "{rust}"
    );
    assert_eq!(rust.matches("sample_next(").count(), 1, "{rust}");

    let runtime = format!(
        "use std::sync::atomic::{{AtomicU32, Ordering}};\n\
         static DB_BEFORE: AtomicU32 = AtomicU32::new(0);\n\
         static SEED_BEFORE: AtomicU32 = AtomicU32::new(0);\n\
         static ALIAS_BEFORE: AtomicU32 = AtomicU32::new(0);\n\
         fn sample_next(db: &mut Source, seed: &mut Seed, alias: &mut Node) -> u32 {{\
             DB_BEFORE.store(db.delta, Ordering::SeqCst);\
             SEED_BEFORE.store(seed.token, Ordering::SeqCst);\
             ALIAS_BEFORE.store(alias.nested.leaf, Ordering::SeqCst);\
             if seed.token == 1 {{ u32::MAX }} else {{ 17 }}\
         }}\n{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-assignment-call-reborrow-run-once",
        &runtime,
        r#"
    let mut hit_db = Source { delta: 3 };
    let mut hit_owner = Owner {
        current: Node { nested: Cell { leaf: 9, guard: 11 }, tag: 13 },
        marker: u32::MAX - 1,
    };
    assert!(advance_projected_entry_once(&mut hit_owner, &mut hit_db, Seed { token: 1 }));
    assert_eq!(DB_BEFORE.load(Ordering::SeqCst), 3);
    assert_eq!(SEED_BEFORE.load(Ordering::SeqCst), 1);
    assert_eq!(ALIAS_BEFORE.load(Ordering::SeqCst), 9);
    assert_eq!(hit_owner.current.nested.leaf, 0);
    assert_eq!(hit_owner.marker, 1);

    let mut miss_db = Source { delta: 5 };
    let mut miss_owner = Owner {
        current: Node { nested: Cell { leaf: 23, guard: 29 }, tag: 31 },
        marker: 7,
    };
    assert!(!advance_projected_entry_once(&mut miss_owner, &mut miss_db, Seed { token: 2 }));
    assert_eq!(DB_BEFORE.load(Ordering::SeqCst), 5);
    assert_eq!(SEED_BEFORE.load(Ordering::SeqCst), 2);
    assert_eq!(ALIAS_BEFORE.load(Ordering::SeqCst), 23);
    assert_eq!(miss_owner.current.nested.leaf, 17);
    assert_eq!(miss_owner.marker, 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn assignment_call_reborrow_accepts_explicit_u32_cast_of_negative_literal() {
    let mut function = assignment_call_reborrow_ir("advance_cast_sentinel");
    let (condition, _, _) = assignment_call_branch_mut(&mut function);
    let IrExpr::Binary { rhs, .. } = condition else {
        unreachable!()
    };
    let IrExpr::LitInt { ty: u32_ty, .. } = rhs.as_ref() else {
        unreachable!()
    };
    let u32_ty = u32_ty.clone();
    let mut i32_ty = u32_ty.clone();
    i32_ty.spelled = "int".to_string();
    i32_ty.canonical = "int".to_string();
    i32_ty.kind = IrTypeKind::Integer {
        signed: true,
        width: 32,
    };
    *rhs = Box::new(IrExpr::Cast {
        target: u32_ty,
        expr: Box::new(IrExpr::Unary {
            op: IrUnOp::Neg,
            operand: Box::new(IrExpr::LitInt {
                value: 1,
                spelling: "1".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            }),
            ty: i32_ty,
            source_span: None,
        }),
        implicit: false,
        source_span: None,
    });

    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &function,
        &[],
        assignment_call_reborrow_policy(),
    )
    .expect("emit explicit cast sentinel");
    assert!(emitted.rust.contains("as u32"), "{}", emitted.rust);
}
