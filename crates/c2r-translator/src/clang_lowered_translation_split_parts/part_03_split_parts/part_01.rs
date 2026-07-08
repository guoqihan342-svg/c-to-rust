    #[test]
    fn clang_lowered_pointer_graph_records_post_increment_deref_inside_member_base() {
        let u32_ty = unsigned_ty("uint32_t", "unsigned int", 32);
        let u8_ty = unsigned_ty("uint8_t", "unsigned char", 8);
        let const_u8_ptr = pointer_ty(
            "const uint8_t *",
            "const unsigned char *",
            u8_ty.clone(),
            true,
        );
        let const_void_ptr = pointer_ty("const void *", "const void *", void_ty(true), true);
        let function = IrFunction {
            name: "member_cursor".to_string(),
            return_type: u32_ty.clone(),
            params: vec![param("buf", const_void_ptr.clone())],
            body: vec![
                IrStmt::Assign {
                    target: var("cursor", const_u8_ptr.clone()),
                    value: IrExpr::Cast {
                        target: const_u8_ptr.clone(),
                        expr: Box::new(var("buf", const_void_ptr)),
                        implicit: false,
                        source_span: None,
                    },
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(IrExpr::Member {
                        base: Box::new(IrExpr::Deref {
                            ptr: Box::new(IrExpr::IncDec {
                                target: Box::new(var("cursor", const_u8_ptr.clone())),
                                op: IrIncDecOp::Inc,
                                prefix: false,
                                ty: const_u8_ptr,
                                source_span: None,
                            }),
                            ty: record_ty("byte_record"),
                            source_span: None,
                        }),
                        field: "value".to_string(),
                        ty: u32_ty,
                        is_arrow: false,
                        source_span: None,
                    }),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "member-cursor".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "member_cursor".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let buf = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "buf")
            .expect("buf pointer node");
        assert_eq!(buf.read_effects, vec!["*p++"]);
        assert!(
            buf.boundary_decisions
                .contains(&"byte_cursor_post_increment_read".to_string()),
            "{:?}",
            buf.boundary_decisions
        );
        let buf_mapping = result
            .type_map
            .mappings
            .iter()
            .find(|mapping| mapping.symbol == "buf")
            .expect("buf type mapping");
        assert_eq!(buf_mapping.rust_type, "&[u8]");
    }
