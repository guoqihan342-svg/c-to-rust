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

#[cfg(feature = "typed-ir")]
fn ir_record(name: &str) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: None,
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_record_with_fields(name: &str, fields: Vec<(&str, IrType)>) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: Some(
                fields
                    .into_iter()
                    .map(|(name, ty)| IrRecordField {
                        name: name.to_string(),
                        ty,
                    })
                    .collect(),
            ),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_var(name: &str, ty: IrType) -> IrExpr {
    IrExpr::Var {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_null_ptr(ty: IrType) -> IrExpr {
    IrExpr::NullPtr {
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_lit(value: u64, spelling: &str, ty: IrType) -> IrExpr {
    IrExpr::LitInt {
        value,
        spelling: spelling.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_array(element: IrType, len: usize) -> IrType {
    IrType {
        spelled: format!("{}[{len}]", element.spelled),
        canonical: format!("{}[{len}]", element.canonical),
        kind: IrTypeKind::Array {
            element: Box::new(element),
            len: Some(len),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn without_implicit_cast(expr: &IrExpr) -> &IrExpr {
    match expr {
        IrExpr::Cast {
            expr,
            implicit: true,
            ..
        } => without_implicit_cast(expr),
        _ => expr,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Binary {
        op,
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_conditional(condition: IrExpr, then_expr: IrExpr, else_expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Conditional {
        condition: Box::new(condition),
        then_expr: Box::new(then_expr),
        else_expr: Box::new(else_expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_deref(ptr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Deref {
        ptr: Box::new(ptr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_bitnot(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_neg(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Neg,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_not(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Not,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_control_flow_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/control_flow_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason, expected_range) in [
        (
            "label_refusal",
            "unsupported control-flow LabelStmt",
            "source_range=2:3-2:15",
        ),
        (
            "goto_refusal",
            "unsupported control-flow GotoStmt",
            "source_range=5:3-5:12",
        ),
        (
            "switch_refusal",
            "unsupported control-flow SwitchStmt",
            "source_range=8:3-8:48",
        ),
        (
            "case_refusal",
            "unsupported control-flow CaseStmt",
            "source_range=11:3-11:18",
        ),
        (
            "default_refusal",
            "unsupported control-flow DefaultStmt",
            "source_range=14:3-14:18",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("control-flow fixture must fail closed during clang AST lowering");
        assert_eq!(error.kind, "unsupported_clang_stmt");
        assert!(
            error.message.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.message
        );
        assert!(
            error
                .message
                .contains("requires structured CFG/relooper support"),
            "expected {function_name} refusal to mention CFG/relooper support, got {:?}",
            error.message
        );
        assert!(
            error.message.contains(expected_range),
            "expected {function_name} refusal to contain {expected_range:?}, got {:?}",
            error.message
        );
    }
}
