    use super::*;
    use crate::typed_ir::{
        IrBinOp, IrExpr, IrFunction, IrIncDecOp, IrParam, IrStmt, IrType, IrTypeKind, SourceSpan,
    };

    fn test_profile() -> BuildProfile {
        BuildProfile {
            include_paths: Vec::new(),
            defines: Vec::new(),
            target: None,
            clang_ast_fixture: None,
            target_triple: None,
            abi: None,
            compiler_command_source: "unit-test".to_string(),
            clang_available: true,
        }
    }

    fn unsigned_ty(spelled: &str, canonical: &str, width: u16) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Integer {
                signed: false,
                width,
            },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn signed_ty(spelled: &str, canonical: &str, width: u16) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Integer {
                signed: true,
                width,
            },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn void_ty(is_const: bool) -> IrType {
        IrType {
            spelled: "void".to_string(),
            canonical: "void".to_string(),
            kind: IrTypeKind::Void,
            is_const,
            width_bits: None,
            source_span: None,
        }
    }

    fn pointer_ty(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
        IrType {
            spelled: spelled.to_string(),
            canonical: canonical.to_string(),
            kind: IrTypeKind::Pointer {
                pointee: Box::new(pointee),
            },
            is_const,
            width_bits: Some(64),
            source_span: None,
        }
    }

    fn record_ty(name: &str) -> IrType {
        IrType {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: IrTypeKind::Record {
                name: name.to_string(),
                fields: None,
            },
            is_const: false,
            width_bits: None,
            source_span: None,
        }
    }

    fn param(name: &str, ty: IrType) -> IrParam {
        IrParam {
            name: name.to_string(),
            ty,
            source_span: None,
        }
    }

    fn var(name: &str, ty: IrType) -> IrExpr {
        IrExpr::Var {
            name: name.to_string(),
            ty,
            source_span: None,
        }
    }

    fn call(callee: &str, args: Vec<IrExpr>, ty: IrType) -> IrExpr {
        IrExpr::Call {
            callee: callee.to_string(),
            args,
            ty,
            source_span: None,
        }
    }
    #[test]
    fn clang_lowered_ir_records_direct_call_expression_evidence() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "call_expression".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::Decl {
                    name: "first".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(call(
                        "helper",
                        vec![var("value", i32_ty.clone())],
                        i32_ty.clone(),
                    )),
                    source_span: None,
                },
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("first", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(call("helper", vec![var("value", i32_ty.clone())], i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "call-expression".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "call_expression".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 3);
        assert!(result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));
        assert_eq!(result.plan.call_expressions[0].callee, "helper");
        assert_eq!(result.plan.call_expressions[0].arguments, vec!["value"]);
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "helper(value)"
        );
        assert_eq!(
            result.plan.call_expressions[0].statement_context,
            "declaration_initializer"
        );
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "helper(first)"
        );
        assert_eq!(
            result.plan.call_expressions[1].statement_context,
            "assignment"
        );
        assert_eq!(result.plan.call_expressions[2].statement_context, "return");
    }

    #[test]
    fn clang_lowered_ir_parenthesizes_complex_member_source_text() {
        let i32_ty = signed_ty("int", "int", 32);
        let ptr_ty = pointer_ty(
            "struct point *",
            "struct point *",
            record_ty("point"),
            false,
        );
        let member = IrExpr::Member {
            base: Box::new(IrExpr::Deref {
                ptr: Box::new(var("p", ptr_ty)),
                ty: record_ty("point"),
                source_span: None,
            }),
            field: "x".to_string(),
            ty: i32_ty,
            is_arrow: false,
            source_span: None,
        };

        assert_eq!(ir_expr_source_text(&member), "(*p).x");
    }

    #[test]
    fn clang_lowered_ir_records_call_inside_member_base() {
        let i32_ty = signed_ty("int", "int", 32);
        let point_ty = record_ty("point");
        let function = IrFunction {
            name: "member_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![IrStmt::Return {
                value: Some(call(
                    "helper",
                    vec![IrExpr::Member {
                        base: Box::new(call("obj_factory", Vec::new(), point_ty)),
                        field: "x".to_string(),
                        ty: i32_ty.clone(),
                        is_arrow: false,
                        source_span: None,
                    }],
                    i32_ty,
                )),
                source_span: None,
            }],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "member-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "member_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 2);
        assert_eq!(result.plan.call_expressions[0].callee, "helper");
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "helper(obj_factory().x)"
        );
        assert_eq!(result.plan.call_expressions[1].callee, "obj_factory");
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "obj_factory()"
        );
    }

    #[test]
    fn clang_lowered_ir_preserves_repeated_direct_call_sites_in_same_context() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "repeat_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Assign {
                    target: var("value", i32_ty.clone()),
                    value: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "repeat-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "repeat_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert_eq!(result.plan.call_expressions.len(), 2);
        assert!(result
            .plan
            .call_expressions
            .iter()
            .all(|call| call.source_expression == "helper(value)"));
        assert!(result
            .plan
            .call_expressions
            .iter()
            .all(|call| call.statement_context == "assignment"));
    }

    #[test]
    fn clang_lowered_ir_does_not_record_condition_call_as_success_evidence() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "condition_call".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("value", i32_ty.clone())],
            body: vec![
                IrStmt::If {
                    condition: call("helper", vec![var("value", i32_ty.clone())], i32_ty.clone()),
                    then_body: vec![IrStmt::Return {
                        value: Some(var("value", i32_ty.clone())),
                        source_span: None,
                    }],
                    else_body: Vec::new(),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("value", i32_ty)),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "condition-call".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "condition_call".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        assert!(result.plan.call_expressions.is_empty());
        assert!(!result
            .plan
            .translation_rule_ids
            .contains(&"bounded-call-expression".to_string()));
    }

    #[test]
    fn clang_lowered_ir_records_for_statement_evidence_recursively() {
        let i32_ty = signed_ty("int", "int", 32);
        let function = IrFunction {
            name: "for_evidence".to_string(),
            return_type: i32_ty.clone(),
            params: vec![param("limit", i32_ty.clone())],
            body: vec![
                IrStmt::Decl {
                    name: "total".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(var("limit", i32_ty.clone())),
                    source_span: None,
                },
                IrStmt::For {
                    init: vec![IrStmt::Decl {
                        name: "i".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(var("limit", i32_ty.clone())),
                        source_span: None,
                    }],
                    condition: Some(IrExpr::Binary {
                        op: IrBinOp::Lt,
                        lhs: Box::new(var("i", i32_ty.clone())),
                        rhs: Box::new(var("limit", i32_ty.clone())),
                        ty: i32_ty.clone(),
                        source_span: None,
                    }),
                    step: Some(Box::new(IrStmt::Assign {
                        target: var("i", i32_ty.clone()),
                        value: call(
                            "step_helper",
                            vec![var("i", i32_ty.clone())],
                            i32_ty.clone(),
                        ),
                        source_span: None,
                    })),
                    body: vec![IrStmt::Decl {
                        name: "next".to_string(),
                        ty: i32_ty.clone(),
                        init: Some(call(
                            "body_helper",
                            vec![var("total", i32_ty.clone())],
                            i32_ty.clone(),
                        )),
                        source_span: None,
                    }],
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(var("total", i32_ty.clone())),
                    source_span: None,
                },
            ],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "for-evidence".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "for_evidence".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        let mut result = TranslationResult::default();

        record_clang_lowered_ir_evidence(&spec, &function, &mut result);

        let block = &result.cfg.functions[0].blocks[0];
        assert!(block.statement_kinds.contains(&"for".to_string()));
        assert!(block.edges.contains(&"entry->for-1".to_string()));
        assert!(result
            .type_map
            .mappings
            .iter()
            .any(|mapping| mapping.symbol == "i"));
        assert!(result
            .type_map
            .mappings
            .iter()
            .any(|mapping| mapping.symbol == "next"));
        assert_eq!(result.plan.call_expressions.len(), 2);
        assert_eq!(
            result.plan.call_expressions[0].source_expression,
            "body_helper(total)"
        );
        assert_eq!(
            result.plan.call_expressions[0].statement_context,
            "declaration_initializer"
        );
        assert_eq!(
            result.plan.call_expressions[1].source_expression,
            "step_helper(i)"
        );
        assert_eq!(
            result.plan.call_expressions[1].statement_context,
            "assignment"
        );
    }

    #[test]
    fn clang_lowered_pointer_graph_does_not_infer_byte_cursor_from_buf_name_only() {
        let u32_ty = unsigned_ty("uint32_t", "unsigned int", 32);
        let usize_ty = unsigned_ty("size_t", "unsigned long", 64);
        let const_void_ptr = pointer_ty("const void *", "const void *", void_ty(true), true);
        let function = IrFunction {
            name: "fdb_calc_crc32".to_string(),
            return_type: u32_ty.clone(),
            params: vec![
                param("crc", u32_ty.clone()),
                param("buf", const_void_ptr),
                param("size", usize_ty),
            ],
            body: vec![IrStmt::Return {
                value: Some(IrExpr::Var {
                    name: "crc".to_string(),
                    ty: u32_ty,
                    source_span: None::<SourceSpan>,
                }),
                source_span: None,
            }],
            source_span: None,
        };
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "real-fdb-calc-crc32".to_string(),
            source_commit: "93d1755".to_string(),
            function_name: "fdb_calc_crc32".to_string(),
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
        assert!(buf.read_effects.is_empty(), "{:?}", buf.read_effects);
        assert!(
            !buf.boundary_decisions
                .contains(&"byte_cursor_post_increment_read".to_string()),
            "{:?}",
            buf.boundary_decisions
        );
    }
