#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_lowers_emits_and_updates_owner() {
    let function_name = "set_nested_leaf_via_projection";
    let ast = interior_reborrow_fixture(function_name);
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
        .expect("lower renamed interior reborrow without clang");
    assert!(matches!(
        lowered.function_ir.body.as_slice(),
        [
            IrStmt::Decl {
                name,
                init: Some(IrExpr::AddrOf { operand, .. }),
                ..
            },
            IrStmt::Assign { target, .. },
            IrStmt::Return {
                value: Some(IrExpr::LitInt { value: 1, ty, .. }),
                ..
            }
        ] if name == "cursor"
            && matches!(operand.as_ref(), IrExpr::Member { field, is_arrow: true, .. }
                if field == "current")
            && matches!(target, IrExpr::Member { field, is_arrow: false, .. }
                if field == "leaf")
            && matches!(ty.kind, IrTypeKind::Integer { signed: false, width: 8 })
    ));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("emit safe interior reborrow Rust");
    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    let rust = &emitted.rust;
    assert!(
        rust.contains("let cursor = &mut owner.current;"),
        "{rust}"
    );
    assert!(rust.contains("cursor.nested.leaf = 37u32;"), "{rust}");
    assert!(rust.contains("return true;"), "{rust}");
    assert!(!rust.contains("unsafe"), "{rust}");
    assert!(!rust.contains("*mut"), "{rust}");
    assert!(!rust.contains("noalias"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-interior-reborrow-owner-state",
        rust,
        r#"
    let mut owner = Owner {
        current: Node {
            nested: Cell { leaf: 5, guard: 11 },
            tag: 13,
        },
        marker: 17,
    };
    assert!(set_nested_leaf_via_projection(&mut owner));
    assert_eq!(owner.current.nested.leaf, 37);
    assert_eq!(owner.current.nested.guard, 11);
    assert_eq!(owner.current.tag, 13);
    assert_eq!(owner.marker, 17);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_needs_typedef_pointer_provenance() {
    let function_name = "reject_direct_pointer_projection";
    let mut ast = interior_reborrow_fixture(function_name);
    let function = interior_reborrow_function_mut(&mut ast, function_name);
    let body = interior_reborrow_body_mut(function);
    body[0]["inner"][0]["type"] = serde_json::json!({
        "qualType": "struct Node *"
    });
    let reason = interior_reborrow_failure(&ast, function_name);
    assert!(reason.contains("typedef") || reason.contains("pointer"), "{reason}");
}
