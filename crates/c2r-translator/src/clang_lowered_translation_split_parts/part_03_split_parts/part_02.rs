    #[test]
    fn clang_lowered_type_map_records_unused_readonly_8_bit_pointer_as_raw_candidate() {
        let i32_ty = signed_ty("int", "int", 32);
        let mut const_char_ty = signed_ty("char", "char", 8);
        const_char_ty.is_const = true;
        let const_char_ptr = pointer_ty("const char *", "const char *", const_char_ty, false);
        let sockaddr_ptr = pointer_ty(
            "struct sockaddr_in *",
            "struct sockaddr_in *",
            record_ty("sockaddr_in"),
            false,
        );
        let function = IrFunction {
            name: "uv_ip4_addr".to_string(),
            return_type: i32_ty.clone(),
            params: vec![
                param("ip", const_char_ptr),
                param("port", i32_ty.clone()),
                param("addr", sockaddr_ptr.clone()),
            ],
            body: vec![
                IrStmt::Assign {
                    target: IrExpr::Member {
                        base: Box::new(var("addr", sockaddr_ptr)),
                        field: "sin_family".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: true,
                        source_span: None,
                    },
                    value: IrExpr::LitInt {
                        value: 2,
                        spelling: "2".to_string(),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(IrExpr::LitInt {
                        value: 0,
                        spelling: "0".to_string(),
                        ty: i32_ty,
                        source_span: None,
                    }),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "libuv".to_string(),
            slice_id: "ip4-addr".to_string(),
            source_commit: "5e7d51a".to_string(),
            function_name: "uv_ip4_addr".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let ip_mapping = result
            .type_map
            .mappings
            .iter()
            .find(|mapping| mapping.symbol == "ip")
            .expect("ip type mapping");
        assert_eq!(ip_mapping.rust_type, "*const core::ffi::c_void");
        let ip_pointer = result
            .pointer_graph
            .nodes
            .iter()
            .find(|node| node.id == "ip")
            .expect("ip pointer node");
        assert_eq!(ip_pointer.rust_boundary, "*const core::ffi::c_void");
        assert!(ip_pointer.read_effects.is_empty());
        assert!(ip_pointer
            .boundary_decisions
            .contains(&"unused_readonly_8_bit_pointer_raw_candidate".to_string()));
    }
