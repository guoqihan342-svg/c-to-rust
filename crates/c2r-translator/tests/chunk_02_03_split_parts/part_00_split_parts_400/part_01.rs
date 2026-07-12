#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_nested_record_pointer_scalar_field_copy() {
    let ir = nested_record_pointer_scalar_field_copy_ir();
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "kv".to_string(),
            mutable_param: "blob".to_string(),
        }],
        ..Default::default()
    };
    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("emit nested record pointer scalar field copy with noalias evidence");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Blob"), "{rust}");
    assert!(rust.contains("pub struct BlobSaved"), "{rust}");
    assert!(rust.contains("pub struct Kv"), "{rust}");
    assert!(rust.contains("pub struct KvAddr"), "{rust}");
    assert!(
        rust.contains(
            "pub fn copy_nested_blob_saved<'a>(kv: &Kv, blob: &'a mut Blob) -> &'a mut Blob"
        ),
        "{rust}"
    );
    assert!(rust.contains("blob.saved.meta_addr = kv.addr.start;"), "{rust}");
    assert!(rust.contains("blob.saved.len = kv.value_len;"), "{rust}");
    assert!(rust.contains("return blob;"), "{rust}");
    assert_rust_snippet_compiles("typed-ir-nested-record-pointer-scalar-field-copy", rust);
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_emits_mutable_record_pointer_readonly_nested_input_with_noalias() {
    let u32_ty = ir_u32();
    let source_addr_ty = ir_record_with_fields("source_addr", vec![("start", u32_ty.clone())]);
    let source_ty = ir_record_with_fields(
        "source",
        vec![("addr", source_addr_ty.clone()), ("len", u32_ty.clone())],
    );
    let source_param_ty = ir_pointer("source_t", "struct source *", source_ty.clone(), false);
    let source_ptr_ty = ir_pointer("struct source *", "struct source *", source_ty, false);
    let dest_ty = ir_record_with_fields(
        "dest",
        vec![("start", u32_ty.clone()), ("len", u32_ty.clone())],
    );
    let dest_param_ty = ir_pointer("dest_t", "struct dest *", dest_ty.clone(), false);
    let dest_ptr_ty = ir_pointer("struct dest *", "struct dest *", dest_ty, false);
    let ir = IrFunction {
        name: "copy_from_mutable_source_record".to_string(),
        return_type: dest_param_ty.clone(),
        params: vec![
            IrParam {
                name: "source".to_string(),
                ty: source_param_ty,
                source_span: None,
            },
            IrParam {
                name: "dest".to_string(),
                ty: dest_param_ty,
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("dest", dest_ptr_ty.clone())),
                    field: "start".to_string(),
                    ty: u32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: IrExpr::Member {
                    base: Box::new(IrExpr::Member {
                        base: Box::new(ir_var("source", source_ptr_ty.clone())),
                        field: "addr".to_string(),
                        ty: source_addr_ty,
                        is_arrow: true,
                        source_span: None,
                    }),
                    field: "start".to_string(),
                    ty: u32_ty.clone(),
                    is_arrow: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: IrExpr::Member {
                    base: Box::new(ir_var("dest", dest_ptr_ty.clone())),
                    field: "len".to_string(),
                    ty: u32_ty.clone(),
                    is_arrow: true,
                    source_span: None,
                },
                value: IrExpr::Member {
                    base: Box::new(ir_var("source", source_ptr_ty.clone())),
                    field: "len".to_string(),
                    ty: u32_ty,
                    is_arrow: true,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(ir_var("dest", dest_ptr_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    };
    let policy = EmitPolicy {
        noalias_param_pairs: vec![NoAliasParamPair {
            readonly_param: "source".to_string(),
            mutable_param: "dest".to_string(),
        }],
        ..Default::default()
    };

    let emitted = emit_rust_from_ir_with_globals_and_policy(&ir, &[], policy)
        .expect("emit mutable record pointer readonly nested input with noalias evidence");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(
        rust.contains(
            "pub fn copy_from_mutable_source_record<'a>(source: &Source, mut dest: &'a mut Dest) -> &'a mut Dest"
        ),
        "{rust}"
    );
    assert!(rust.contains("dest.start = source.addr.start;"), "{rust}");
    assert!(rust.contains("dest.len = source.len;"), "{rust}");
    assert!(rust.contains("return dest;"), "{rust}");
    assert_rust_snippet_compiles(
        "typed-ir-mutable-record-pointer-readonly-nested-input",
        rust,
    );
}
