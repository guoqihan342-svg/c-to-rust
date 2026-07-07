#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_nonvoid_pointer_field_write() {
    let u8_ty = ir_u8();
    let usize_ty = ir_usize();
    let const_u8_ptr_ty = ir_pointer("const uint8_t *", "uint8_t *", ir_const(u8_ty), false);
    let blob_ty = ir_record_with_fields(
        "blob",
        vec![
            ("buf", const_u8_ptr_ty.clone()),
            ("size", usize_ty.clone()),
        ],
    );
    let blob_ptr_ty = ir_pointer("struct blob *", "struct blob *", blob_ty, false);
    let ir = IrFunction {
        name: "set_blob_bytes".to_string(),
        return_type: blob_ptr_ty.clone(),
        params: vec![
            IrParam {
                name: "blob".to_string(),
                ty: blob_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "value".to_string(),
                ty: const_u8_ptr_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "len".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "buf".to_string(),
                    ty: const_u8_ptr_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("value", const_u8_ptr_ty),
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("blob", blob_ptr_ty.clone())),
                    field: "size".to_string(),
                    ty: usize_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: ir_var("len", usize_ty),
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("blob", blob_ptr_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("emit non-void pointer field write on mutable record pointer");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub buf: *const u8"), "{rust}");
    assert!(
        rust.contains("pub fn set_blob_bytes(mut blob: &mut Blob, value: *const u8, len: usize) -> &mut Blob"),
        "{rust}"
    );
    assert!(rust.contains("blob.buf = value;"), "{rust}");
    assert!(rust.contains("blob.size = len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-mutable-record-pointer-nonvoid-pointer-field", rust);
}
