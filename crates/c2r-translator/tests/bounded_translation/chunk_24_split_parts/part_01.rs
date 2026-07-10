#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_do_while_assignment_call_record_pointer_target_and_sibling_read_runs() {
    let function_name = "rotate_sweep_cursor";
    let ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower renamed do-while record-pointer assignment-call target");

    let [IrStmt::DoWhile {
        body,
        condition,
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!("expected one normalized do-while, got {:?}", lowered.function_ir.body);
    };
    assert!(matches!(
        body.as_slice(),
        [IrStmt::Assign { target, value, .. }]
            if matches!(target, IrExpr::Member { field, is_arrow: true, .. } if field == "next_slot")
                && matches!(value, IrExpr::Call { callee, args, .. }
                    if callee == "seek_next" && args.len() == 2)
    ));
    assert!(matches!(
        condition,
        IrExpr::Binary { op: IrBinOp::Neq, lhs, .. }
            if matches!(lhs.as_ref(), IrExpr::LValueToRValue { expr, .. }
                if matches!(expr.as_ref(), IrExpr::Member { field, is_arrow: true, .. }
                    if field == "next_slot"))
    ));

    let missing_noalias =
        emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect_err("distinct mutable record owners require explicit noalias evidence");
    assert!(
        missing_noalias.reason.contains("alias proof")
            || missing_noalias.reason.contains("noalias"),
        "{missing_noalias:?}"
    );

    let emitted = emit_rust_from_ir_with_globals_and_policy(
        &lowered.function_ir,
        &lowered.globals,
        do_while_record_pointer_fixture_policy(),
    )
    .expect("emit normalized do-while record-pointer assignment-call target");
    let rust = &emitted.rust;
    assert!(
        rust.contains("walker.next_slot = seek_next(arena, walker.distance);"),
        "{rust}"
    );
    assert!(
        rust.contains("if !((walker.next_slot != 4294967295u32))"),
        "{rust}"
    );
    assert_eq!(rust.matches("seek_next(").count(), 1, "{rust}");

    let runtime_rust = format!(
        "use std::sync::atomic::{{AtomicUsize, Ordering}};\n\
         static CALLS: AtomicUsize = AtomicUsize::new(0);\n\
         fn seek_next(_arena: &mut DispatchArena, distance: u32) -> u32 {{\
             CALLS.fetch_add(1, Ordering::SeqCst);\
             assert_eq!(distance, 27);\
             u32::MAX\
         }}\n\
         {rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-do-while-record-pointer-assignment-call-sibling-read",
        &runtime_rust,
        r#"
    CALLS.store(0, Ordering::SeqCst);
    let mut arena = DispatchArena { epoch: 3 };
    let mut walker = SweepCursor { next_slot: 0, distance: 27 };
    rotate_sweep_cursor(&mut arena, &mut walker);
    assert_eq!(walker.next_slot, u32::MAX);
    assert_eq!(walker.distance, 27);
    assert_eq!(CALLS.load(Ordering::SeqCst), 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
#[ignore = "requires real clang AST smoke test opt-in"]
fn clang_ast_dump_do_while_assignment_call_record_pointer_target_and_sibling_read_runs() {
    let clang_path = real_clang_ast_test_setup();
    let out_dir = unique_out_dir("clang-real-do-while-record-pointer-assignment-call");
    fs::create_dir_all(&out_dir).unwrap();
    let source_file = out_dir.join("rotate_sweep_cursor.c");
    fs::write(
        &source_file,
        "struct DispatchArena { unsigned int epoch; };\n\
         struct SweepCursor { unsigned int next_slot; unsigned int distance; };\n\
         struct SectorMarker { unsigned int code; };\n\
         unsigned int seek_next(struct DispatchArena *arena, struct SectorMarker *marker, unsigned int distance);\n\
         void rotate_sweep_cursor(struct DispatchArena *arena, struct SweepCursor *walker) {\n\
             struct SectorMarker marker;\n\
             do { } while ((walker->next_slot = seek_next(arena, &marker, walker->distance)) != 4294967295U);\n\
         }\n",
    )
    .unwrap();
    let environment = std::collections::BTreeMap::from([(
        "CLANG_PATH".to_string(),
        clang_path.to_string_lossy().into_owned(),
    )]);

    let report = lower_function_from_clang_ast_dump_report(
        &environment,
        &source_file,
        "rotate_sweep_cursor",
    );
    assert_eq!(report.status, "lowered", "{:?}", report.errors);
    let function = report.function_ir.as_ref().expect("real clang function ir");
    let emitted = emit_rust_from_ir_with_globals_and_policy(
        function,
        &report.globals,
        do_while_record_pointer_fixture_policy(),
    )
    .expect("emit real clang do-while record-pointer assignment-call");
    let rust = &emitted.rust;
    assert!(
        rust.contains("walker.next_slot = seek_next(arena, &mut marker, walker.distance);"),
        "{rust}"
    );
    assert_eq!(rust.matches("seek_next(").count(), 1, "{rust}");

    let runtime_rust = format!(
        "use std::sync::atomic::{{AtomicUsize, Ordering}};\n\
         static CALLS: AtomicUsize = AtomicUsize::new(0);\n\
         fn seek_next(_arena: &mut DispatchArena, marker: &mut SectorMarker, distance: u32) -> u32 {{\
             CALLS.fetch_add(1, Ordering::SeqCst);\
             marker.code = 9;\
             assert_eq!(distance, 27);\
             u32::MAX\
         }}\n\
         {rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-real-clang-do-while-record-pointer-assignment-call",
        &runtime_rust,
        r#"
    CALLS.store(0, Ordering::SeqCst);
    let mut arena = DispatchArena { epoch: 3 };
    let mut walker = SweepCursor { next_slot: 0, distance: 27 };
    rotate_sweep_cursor(&mut arena, &mut walker);
    assert_eq!(walker.next_slot, u32::MAX);
    assert_eq!(walker.distance, 27);
    assert_eq!(CALLS.load(Ordering::SeqCst), 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_do_while_record_pointer_assignment_call_frontend_boundaries_fail_closed() {
    let function_name = "reject_second_pointer_hop";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let target = &mut do_while_record_pointer_fixture_assignment_mut(function)["inner"][0];
    let root = target["inner"][0].clone();
    target["inner"][0] = serde_json::json!({
        "kind": "MemberExpr",
        "name": "linked_cursor",
        "isArrow": true,
        "type": { "qualType": "struct SweepCursor *" },
        "inner": [root]
    });
    assert_do_while_record_pointer_fixture_rejected(
        &ast,
        function_name,
        "second arrow or pointer member hop",
    );

    let function_name = "reject_readonly_cursor_root";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let target = &mut do_while_record_pointer_fixture_assignment_mut(function)["inner"][0];
    target["inner"][0]["type"]["qualType"] =
        serde_json::json!("const struct SweepCursor *");
    target["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("const struct SweepCursor *");
    assert_do_while_record_pointer_fixture_rejected(
        &ast,
        function_name,
        "non-const mutable record pointer",
    );

    let function_name = "reject_volatile_cursor_root";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let target = &mut do_while_record_pointer_fixture_assignment_mut(function)["inner"][0];
    target["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct SweepCursor * volatile");
    target["inner"][0]["inner"][0]["type"]["qualType"] =
        serde_json::json!("struct SweepCursor * volatile");
    assert_do_while_record_pointer_fixture_rejected(&ast, function_name, "volatile or atomic");

    let function_name = "reject_bitcast_cursor_root";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let target = &mut do_while_record_pointer_fixture_assignment_mut(function)["inner"][0];
    let root = target["inner"][0].clone();
    target["inner"][0] = serde_json::json!({
        "kind": "ImplicitCastExpr",
        "castKind": "BitCast",
        "type": { "qualType": "struct SweepCursor *" },
        "inner": [root]
    });
    assert_do_while_record_pointer_fixture_rejected(
        &ast,
        function_name,
        "root must be a direct non-null",
    );

    let function_name = "reject_second_tail_call";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let call = &mut do_while_record_pointer_fixture_assignment_mut(function)["inner"][1];
    let second_call = call.clone();
    call["inner"]
        .as_array_mut()
        .expect("direct call operands")
        .push(second_call);
    assert_do_while_record_pointer_fixture_rejected(&ast, function_name, "second call");

    let function_name = "reject_logical_tail_suffix";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let comparison = function["inner"][2]["inner"][0]["inner"][1].clone();
    function["inner"][2]["inner"][0]["inner"][1] = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "&&",
        "type": { "qualType": "int" },
        "inner": [
            comparison,
            { "kind": "IntegerLiteral", "value": "1", "type": { "qualType": "int" } }
        ]
    });
    assert_do_while_record_pointer_fixture_rejected(
        &ast,
        function_name,
        "cannot be combined with a logical suffix",
    );

    let function_name = "reject_effectful_sibling";
    let mut ast = do_while_record_pointer_assignment_call_fixture(function_name);
    let function = do_while_record_pointer_fixture_function_mut(&mut ast, function_name);
    let call = &mut do_while_record_pointer_fixture_assignment_mut(function)["inner"][1];
    let sibling_member = call["inner"][2]["inner"][0].clone();
    call["inner"][2] = serde_json::json!({
        "kind": "UnaryOperator",
        "opcode": "++",
        "isPostfix": true,
        "type": { "qualType": "unsigned int" },
        "inner": [sibling_member]
    });
    assert_do_while_record_pointer_fixture_rejected(
        &ast,
        function_name,
        "second increment/decrement side effect",
    );
}
