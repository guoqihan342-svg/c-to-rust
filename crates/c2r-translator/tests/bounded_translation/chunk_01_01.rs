#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_fail_closed_refusal_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/scalar_runtime_preconditions_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "literal_divide_by_zero")
            .expect("lower committed clang AST scalar refusal fixture");
    let error = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect_err("literal division by zero from fixture must fail closed");

    assert!(error.reason.contains("division by zero literal"));
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_scalar_ub_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/scalar_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason) in [
        ("literal_modulo_by_zero", "modulo by zero literal"),
        ("shift_count_out_of_range", "shift count literal 32"),
        ("signed_right_shift_without_contract", "signed right shift"),
    ] {
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .unwrap_or_else(|error| {
                panic!("lower committed clang AST fixture {function_name}: {error}")
            });
        let error = match emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals) {
            Ok(emitted) => panic!(
                "fixture {function_name} must fail closed, emitted {}",
                emitted.rust
            ),
            Err(error) => error,
        };

        assert!(
            error.reason.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.reason
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_deref_of_local_fixed_array_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/array_decay_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "first_local_table")
        .expect("array decay through unary deref of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay through unary deref of local fixed array should emit");
    let rust = &emitted.rust;

    assert!(rust.contains("pub fn first_local_table() -> i32"), "{rust}");
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[0i32 as usize];"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-array-decay-deref-local-fixed-array",
        rust,
        r#"
    assert_eq!(first_local_table(), 1);
"#,
    );
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_allows_array_decay_inside_subscript_without_clang() {
    let ast: Value =
        serde_json::from_str(include_str!("../../fixtures/clang_ast/array_decay_ast.json"))
            .expect("fixture JSON");

    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table")
        .expect("array decay in array subscript base should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array subscript base decay should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_local_table(i: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[i as usize];"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-clang-ast-array-decay-subscript", rust);
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_lowers_array_decay_pointer_add_deref_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/array_decay_pointer_add_ast.json"
    ))
    .expect("fixture JSON");

    let lowered =
        lower_function_and_globals_from_clang_ast_json_value(&ast, "lookup_local_table_add")
            .expect("array decay through pointer-add deref of local fixed array should lower");
    let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
        .expect("array decay through pointer-add deref should emit");
    let rust = &emitted.rust;

    assert!(
        rust.contains("pub fn lookup_local_table_add(i: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("let table: [i32; 3] = [1i32, 2i32, 3i32];"),
        "{rust}"
    );
    assert!(rust.contains("return table[i as usize];"), "{rust}");
    assert!(
        !rust.contains("return table[0i32 as usize];"),
        "pointer-add deref must not collapse to *table: {rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-array-decay-pointer-add-deref",
        rust,
        r#"
    assert_eq!(lookup_local_table_add(2), 3);
"#,
    );
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_array_to_pointer_decay_without_lowering_evidence() {
    let i32_ty = ir_i32();
    let array_ty = ir_array(i32_ty.clone(), 4);
    let pointer_ty = ir_pointer("int *", "int *", i32_ty.clone(), false);
    let decay_expr: IrExpr = serde_json::from_value(serde_json::json!({
        "ArrayToPointerDecay": {
            "target": serde_json::to_value(&pointer_ty).unwrap(),
            "expr": serde_json::to_value(ir_var("table", array_ty.clone())).unwrap(),
            "source_span": null
        }
    }))
    .expect("deserialize explicit array-to-pointer decay IR node");
    let ir = IrFunction {
        name: "bad_array_decay_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![],
        body: vec![
            IrStmt::Decl {
                name: "table".to_string(),
                ty: array_ty.clone(),
                init: Some(IrExpr::ArrayLiteral {
                    elements: vec![
                        ir_lit(1, "1", i32_ty.clone()),
                        ir_lit(2, "2", i32_ty.clone()),
                        ir_lit(3, "3", i32_ty.clone()),
                        ir_lit(4, "4", i32_ty.clone()),
                    ],
                    ty: array_ty,
                    source_span: None,
                }),
                source_span: None,
            },
            IrStmt::Expr {
                expr: decay_expr,
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_lit(0, "0", i32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error = emit_rust_from_ir(&ir).expect_err("array-to-pointer decay must stay fail closed");
    assert!(error.reason.contains("array-to-pointer decay"));
    assert!(error.reason.contains("explicit lowering evidence"));
}

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
