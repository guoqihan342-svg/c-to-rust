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
