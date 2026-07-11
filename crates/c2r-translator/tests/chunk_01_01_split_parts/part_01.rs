
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_array_decay_pointer_sub_deref_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/array_decay_pointer_add_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table_sub")
            .expect("array decay through pointer-sub deref should stay visible in typed IR");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("array decay through pointer-sub deref must stay fail-closed at emission");

    assert!(
        error.reason.contains("array-to-pointer decay")
            || error
                .reason
                .contains("deref expression requires readonly pointer evidence")
            || error.reason.contains("deref pointer must be Var"),
        "unexpected error: {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_sparse_designated_array_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "lookup_sparse_designated_table",
    )
    .expect("sparse designated fixed array initializer should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("sparse designated fixed array initializer should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_sparse_designated_table() -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [0i32, 7i32, 0i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[1i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-sparse-designated-array-initializer",
        rust,
        r#"
    assert_eq!(lookup_sparse_designated_table(), 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_unexpanded_designated_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let error = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "reject_unexpanded_designated_table",
    )
    .expect_err("unexpanded DesignatedInitExpr must stay fail-closed");

    assert!(
        error.message.contains("DesignatedInitExpr"),
        "unexpected error: {error}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_sparse_designated_global_array_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/global_designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_global_sparse")
            .expect("sparse designated readonly global initializer should lower");
    assert_eq!(lowered.globals.len(), 1);
    assert_eq!(lowered.globals[0].name, "table");
    assert_eq!(
        lowered.globals[0].init,
        IrGlobalInit::IntegerArray(vec![0, 7, 0])
    );

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("sparse designated readonly global initializer should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("const TABLE: [i32; 3] = [0i32, 7i32, 0i32];"),
        "{rust}"
    );
    assert!(rust.contains("return TABLE[1i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-sparse-designated-global-array-initializer",
        rust,
        r#"
    assert_eq!(lookup_global_sparse(), 7);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_sparse_designated_array_lookup_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/sparse_designated_array_lookup_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "sparse_designated_array_lookup",
    )
    .expect("sparse designated readonly array lookup should lower");
    assert_eq!(lowered.globals.len(), 1);
    assert_eq!(lowered.globals[0].name, "table");
    assert_eq!(
        lowered.globals[0].init,
        IrGlobalInit::IntegerArray(vec![0, 0, 7, 0])
    );

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("sparse designated readonly array lookup should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("const TABLE: [i32; 4] = [0i32, 0i32, 7i32, 0i32];"),
        "{rust}"
    );
    assert!(
        rust.contains("pub fn sparse_designated_array_lookup(index: i32) -> i32"),
        "{rust}"
    );
    assert!(rust.contains("return TABLE[index as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-sparse-designated-array-lookup",
        rust,
        r#"
    assert_eq!(sparse_designated_array_lookup(0), 0);
    assert_eq!(sparse_designated_array_lookup(1), 0);
    assert_eq!(sparse_designated_array_lookup(2), 7);
    assert_eq!(sparse_designated_array_lookup(3), 0);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_referenced_unexpanded_global_designated_initializer_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/global_designated_array_initializer_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(
        &ast,
        "reject_unexpanded_global_sparse",
    )
    .expect("function shape should lower before unsupported global dependency is emitted");
    assert!(
        lowered
            .globals
            .iter()
            .all(|global| global.name != "bad_table"),
        "unsupported bad_table global must not be collected"
    );

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("referenced unexpanded global designated initializer must fail closed");
    assert!(
        error
            .reason
            .contains("index base bad_table is not declared"),
        "unexpected error: {error:?}"
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_readonly_mutable_restrict_noalias_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/restrict_pointer_params_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "copy_one_restrict")
        .expect("restrict-qualified pointer params should lower");
    let values_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "values")
        .expect("values param");
    let out_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "out")
        .expect("out param");
    assert!(values_param.ty.spelled.contains("restrict"));
    assert!(values_param.ty.canonical.contains("restrict"));
    assert!(out_param.ty.spelled.contains("restrict"));
    assert!(out_param.ty.canonical.contains("restrict"));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("restrict-qualified readonly input plus mutable output should emit");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(lowered.globals.is_empty());
    assert!(rust
        .contains("pub fn copy_one_restrict(i: i32, values: &[i32], mut out: &mut [i32]) -> i32"));
    assert!(rust.contains("out[i as usize] = values[i as usize];"));
    assert!(rust.contains("return 0i32;"));
    assert_rust_snippet_compiles("typed-ir-clang-ast-restrict-pointer-copy-one", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_multiple_restrict_mutable_out_pointers_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/restrict_pointer_params_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "store_pair_restrict")
            .expect("multiple restrict-qualified output pointer params should lower");
    let left_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "left")
        .expect("left param");
    let right_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "right")
        .expect("right param");
    assert!(left_param.ty.spelled.contains("restrict"));
    assert!(left_param.ty.canonical.contains("restrict"));
    assert!(right_param.ty.spelled.contains("restrict"));
    assert!(right_param.ty.canonical.contains("restrict"));

    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("restrict-qualified mutable outputs should emit");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(lowered.globals.is_empty());
    assert!(rust.contains(
        "pub fn store_pair_restrict(mut left: &mut [i32], mut right: &mut [i32], first: i32, second: i32)"
    ));
    assert!(rust.contains("left[0i32 as usize] = first;"));
    assert!(rust.contains("right[0i32 as usize] = second;"));
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-multiple-restrict-mutable-out-pointers",
        rust,
        r#"
    let mut left = [0i32];
    let mut right = [0i32];
    store_pair_restrict(&mut left, &mut right, 3, 5);
    assert_eq!(left[0], 3);
    assert_eq!(right[0], 5);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_readonly_mutable_without_noalias_fails_closed() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/readonly_mutable_noalias_missing_ast.json"
    ))
    .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "copy_one")
        .expect("plain readonly input plus mutable output should lower before alias gate");
    let values_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "values")
        .expect("values param");
    let out_param = lowered
        .function_ir
        .params
        .iter()
        .find(|param| param.name == "out")
        .expect("out param");
    assert!(!values_param.ty.spelled.contains("restrict"));
    assert!(!values_param.ty.canonical.contains("restrict"));
    assert!(!out_param.ty.spelled.contains("restrict"));
    assert!(!out_param.ty.canonical.contains("restrict"));

    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("plain readonly input plus mutable output needs noalias proof");

    assert_eq!(error.route.route, CandidateRoute::Unsupported);
    assert!(
        error
            .reason
            .contains("mutable pointer write with readonly pointer read requires noalias proof"),
        "unexpected reason: {}",
        error.reason
    );
}

#[cfg(feature = "typed-ir")]
fn ir_integer(spelled: &str, canonical: &str, signed: bool, width: u16) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Integer { signed, width },
        is_const: false,
        width_bits: Some(width),
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_const(mut ty: IrType) -> IrType {
    ty.is_const = true;
    ty
}

#[cfg(feature = "typed-ir")]
fn ir_pointer(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Pointer {
            pointee: Box::new(pointee),
        },
        is_const,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_u32() -> IrType {
    ir_integer("uint32_t", "unsigned int", false, 32)
}

#[cfg(feature = "typed-ir")]
fn ir_u8() -> IrType {
    ir_integer("uint8_t", "unsigned char", false, 8)
}

#[cfg(feature = "typed-ir")]
fn ir_usize() -> IrType {
    ir_integer("size_t", "unsigned long", false, 64)
}

#[cfg(feature = "typed-ir")]
fn ir_i32() -> IrType {
    ir_integer("int", "int", true, 32)
}

#[cfg(feature = "typed-ir")]
fn ir_void() -> IrType {
    IrType {
        spelled: "void".to_string(),
        canonical: "void".to_string(),
        kind: IrTypeKind::Void,
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_function_type(spelled: &str) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: spelled.to_string(),
        kind: IrTypeKind::Function,
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}
