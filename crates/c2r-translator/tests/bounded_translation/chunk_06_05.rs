#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_scoped_loop_with_decl_init_and_step_assignment() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sum_to_limit".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "limit".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "total".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Assign {
                    target: ir_var("total", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("total", i32_ty.clone()),
                        ir_var("i", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("total", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scoped for loop");

    assert!(rust.contains("pub fn sum_to_limit(limit: i32) -> i32"));
    assert!(rust.contains("let mut total: i32 = 0i32;"));
    assert!(rust.contains("{\n        let mut i: i32 = 0i32;\n        while (i < limit) {"));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return total;"));
    assert_rust_snippet_compiles("typed-ir-for-scoped-loop", &rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_record_field_inc_dec_step_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields(
        "point",
        vec![("x", i32_ty.clone()), ("y", i32_ty.clone())],
    );
    let point_x = || IrExpr::Member {
        base: Box::new(ir_var("p", point_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bump_point_x_for_step".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "limit".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: point_x(),
                    value: ir_binary(
                        IrBinOp::Add,
                        point_x(),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(point_x()),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit record field inc/dec for step assignment");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(
        rust.contains("pub fn bump_point_x_for_step(mut p: Point, limit: i32) -> i32"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-for-record-field-step-assignment",
        rust,
        "let p = Point { x: 2i32 };\nassert_eq!(bump_point_x_for_step(p, 3i32), 5i32);",
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_mutable_record_pointer_field_inc_dec_step_assignment() {
    let i32_ty = ir_i32();
    let point_ty = ir_record_with_fields(
        "point",
        vec![("x", i32_ty.clone()), ("y", i32_ty.clone())],
    );
    let point_ptr_ty = ir_pointer("struct point *", "struct point *", point_ty, false);
    let point_x = || IrExpr::Member {
        base: Box::new(ir_var("p", point_ptr_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: true,
        source_span: None,
    };
    let ir = IrFunction {
        name: "bump_point_ptr_x_for_step".to_string(),
        return_type: ir_void(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "limit".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::For {
                init: vec![IrStmt::Decl {
                    name: "i".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(ir_lit(0, "0", i32_ty.clone())),
                    source_span: None,
                }],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: point_x(),
                    value: ir_binary(
                        IrBinOp::Add,
                        point_x(),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted =
        emit_rust_from_ir(&ir).expect("emit mutable record pointer field inc/dec for step");
    let rust = &emitted.rust;

    assert!(rust.contains("pub struct Point"), "{rust}");
    assert!(
        rust.contains("pub fn bump_point_ptr_x_for_step(mut p: &mut Point, limit: i32)"),
        "{rust}"
    );
    assert!(
        rust.contains("p.x = p.x.checked_add(1i32).expect(\"signed addition overflow\");"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-for-record-pointer-field-step-assignment",
        rust,
        "let mut p = Point { x: 2i32, y: 0i32 };\nbump_point_ptr_x_for_step(&mut p, 3i32);\nassert_eq!(p.x, 5i32);",
    );
}
#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_for_emits_scoped_loop_with_multi_decl_init() {
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "sum_pair_loop".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "limit".to_string(),
            ty: i32_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "total".to_string(),
                ty: i32_ty.clone(),
                init: Some(ir_lit(0, "0", i32_ty.clone())),
                source_span: None,
            },
            IrStmt::For {
                init: vec![
                    IrStmt::Decl {
                        name: "i".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(ir_lit(0, "0", i32_ty.clone())),
                        source_span: None,
                    },
                    IrStmt::Decl {
                        name: "j".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(ir_lit(1, "1", i32_ty.clone())),
                        source_span: None,
                    },
                ],
                condition: Some(ir_binary(
                    IrBinOp::Lt,
                    ir_var("i", i32_ty.clone()),
                    ir_var("limit", i32_ty.clone()),
                    i32_ty.clone(),
                )),
                step: Some(Box::new(IrStmt::Assign {
                    target: ir_var("i", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_var("i", i32_ty.clone()),
                        ir_lit(1, "1", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                })),
                body: vec![IrStmt::Assign {
                    target: ir_var("total", i32_ty.clone()),
                    value: ir_binary(
                        IrBinOp::Add,
                        ir_binary(
                            IrBinOp::Add,
                            ir_var("total", i32_ty.clone()),
                            ir_var("i", i32_ty.clone()),
                            i32_ty.clone(),
                        ),
                        ir_var("j", i32_ty.clone()),
                        i32_ty.clone(),
                    ),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("total", i32_ty.clone())),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let rust = emit_rust_from_ir(&ir).expect("emit scoped for loop with multi decl init");

    assert!(rust.contains("pub fn sum_pair_loop(limit: i32) -> i32"));
    assert!(rust.contains(
        "{\n        let mut i: i32 = 0i32;\n        let mut j: i32 = 1i32;\n        while (i < limit) {"
    ));
    assert!(rust.contains("total = total.checked_add(i).expect(\"signed addition overflow\").checked_add(j).expect(\"signed addition overflow\");"));
    assert!(rust.contains("i = i.checked_add(1i32).expect(\"signed addition overflow\");"));
    assert_rust_snippet_compiles("typed-ir-for-multi-decl-init", &rust);
}
