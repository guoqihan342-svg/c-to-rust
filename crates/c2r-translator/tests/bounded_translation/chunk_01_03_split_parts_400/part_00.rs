#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_value_field_assignment() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "set_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record field assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn set_point_x(mut p: Point, value: i32) -> i32"));
    assert!(rust.contains("p.x = value;"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-record-value-field-assignment", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_value_field_compound_assignment_shape() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let field_target = IrExpr::Member {
        base: Box::new(ir_var("p", point_ty.clone())),
        field: "x".to_string(),
        ty: i32_ty.clone(),
        is_arrow: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "add_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: field_target.clone(),
                value: IrExpr::Binary {
                    op: IrBinOp::Add,
                    lhs: Box::new(field_target),
                    rhs: Box::new(ir_var("value", i32_ty.clone())),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("p", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record field compound shape");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn add_point_x(mut p: Point, value: i32) -> i32"));
    assert!(rust.contains("p.x = p.x.checked_add(value).expect(\"signed addition overflow\");"));
    assert!(rust.contains("return p.x;"));
    assert_rust_snippet_compiles("typed-ir-record-value-field-compound-shape", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_copy_field_read() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "local_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: point_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", point_ty.clone())),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record local copy field read");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub x: i32"));
    assert!(rust.contains("pub fn local_point_x(p: Point) -> i32"));
    assert!(rust.contains("let q: Point = p;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-copy-field-read", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_copy_with_equivalent_record_spelling() {
    let point_ty = ir_record("point");
    let mut const_point_ty = point_ty.clone();
    const_point_ty.spelled = "const struct point".to_string();
    const_point_ty.canonical = "struct point".to_string();
    const_point_ty.is_const = true;
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "local_const_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "p".to_string(),
            ty: const_point_ty.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", const_point_ty)),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit record local copy despite non-semantic spelling differences");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub fn local_const_point_x(p: Point) -> i32"));
    assert!(rust.contains("let q: Point = p;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-copy-equivalent-spelling", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_record_local_copy_field_assignment() {
    let point_ty = ir_record("point");
    let i32_ty = ir_i32();
    let ir = IrFunction {
        name: "set_local_point_x".to_string(),
        return_type: i32_ty.clone(),
        params: vec![
            IrParam {
                name: "p".to_string(),
                ty: point_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: i32_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "q".to_string(),
                ty: point_ty.clone(),
                init: Some(ir_var("p", point_ty.clone())),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty.clone())),
                    field: "x".to_string(),
                    ty: i32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                value: ir_var("value", i32_ty.clone()),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::Member {
                    base: Box::new(ir_var("q", point_ty)),
                    field: "x".to_string(),
                    ty: i32_ty,
                    is_arrow: false,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir).expect("emit by-value record local copy field assignment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Point"));
    assert!(rust.contains("pub fn set_local_point_x(p: Point, value: i32) -> i32"));
    assert!(rust.contains("let mut q: Point = p;"));
    assert!(rust.contains("q.x = value;"));
    assert!(rust.contains("return q.x;"));
    assert_rust_snippet_compiles("typed-ir-record-local-copy-field-assignment", rust);
}
