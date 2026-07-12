
    #[test]
    fn slice_source_translation_unit_does_not_redeclare_build_profile_defines() {
        let spec = SliceSpec {
            target_id: "libuv".to_string(),
            slice_id: "ip4-addr".to_string(),
            function_name: "uv_ip4_addr".to_string(),
            c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![CSignature {
                    function: "uv_ip4_addr".to_string(),
                    return_type: "int".to_string(),
                    parameters: vec![CParameter {
                        name: "addr".to_string(),
                        c_type: "struct sockaddr_in*".to_string(),
                        ..CParameter::default()
                    }],
                    ..CSignature::default()
                }],
                ..CBoundary::default()
            },
            build_profile: BuildProfile {
                defines: vec!["AF_INET=2".to_string()],
                ..test_profile()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(!source.contains("enum { AF_INET"), "{source}");
        assert!(source.contains("addr->sin_family = AF_INET"), "{source}");
    }

    #[test]
    fn slice_source_constant_scan_ignores_null_strings_and_comments() {
        let names = collect_object_like_uppercase_identifiers(
            "int sample(void) { /* SKIP_COMMENT */ const char *msg = \"KV OK\"; return VALUE + (NULL == 0); }",
        );

        assert!(names.contains("VALUE"));
        assert!(!names.contains("NULL"));
        assert!(!names.contains("KV"));
        assert!(!names.contains("OK"));
        assert!(!names.contains("SKIP_COMMENT"));
    }

    #[test]
    fn slice_source_translation_unit_does_not_redeclare_source_enum_constants() {
        let mut spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "guarded-enum".to_string(),
            function_name: "probe".to_string(),
            c_source: "enum state { CELL_EMPTY, CELL_READY = 7 }; int probe(void) { return CELL_READY; }"
                .to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        spec.c_boundary.direct_dependencies.push(CDirectDependency {
            kind: "constant".to_string(),
            name: "CELL_READY".to_string(),
            value: Some(serde_json::json!(7)),
            ..CDirectDependency::default()
        });

        let source = slice_source_translation_unit(&spec);

        assert!(!source.contains("enum { CELL_READY = 7 };"), "{source}");
        assert_eq!(source.matches("CELL_READY").count(), 2, "{source}");
    }

    #[test]
    fn slice_source_translation_unit_does_not_redeclare_source_object_macros() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "object-macro".to_string(),
            function_name: "probe".to_string(),
            c_source: "#define CELL_READY 7\nint probe(void) { return CELL_READY; }".to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(!source.contains("enum { CELL_READY = 0 };"), "{source}");
        assert_eq!(source.matches("CELL_READY").count(), 2, "{source}");
    }

    #[test]
    fn slice_source_constant_scan_handles_source_definition_boundaries_fail_closed() {
        let mut spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "constant-definition-boundaries".to_string(),
            function_name: "probe".to_string(),
            c_source: r#"
#define SOURCE_OBJECT 7
#define SOURCE_FUNCTION(value) ((value) + 1)
enum state { ENUM_EXPLICIT = 11, ENUM_IMPLICIT };
/* COMMENT_ONLY */
int probe(void) {
    const char *message = "STRING_ONLY";
    return SOURCE_OBJECT + SOURCE_FUNCTION(ENUM_EXPLICIT) + ENUM_IMPLICIT;
}
"#
            .to_string(),
            build_profile: test_profile(),
            ..SliceSpec::default()
        };
        for (name, value) in [
            ("SOURCE_OBJECT", 7),
            ("SOURCE_FUNCTION", 3),
            ("ENUM_EXPLICIT", 11),
            ("ENUM_IMPLICIT", 12),
            ("COMMENT_ONLY", 13),
            ("STRING_ONLY", 14),
        ] {
            spec.c_boundary.direct_dependencies.push(CDirectDependency {
                kind: "constant".to_string(),
                name: name.to_string(),
                value: Some(serde_json::json!(value)),
                ..CDirectDependency::default()
            });
        }

        let source = slice_source_translation_unit(&spec);

        for name in ["SOURCE_OBJECT", "ENUM_EXPLICIT", "ENUM_IMPLICIT"] {
            assert!(!source.contains(&format!("enum {{ {name} =")), "{source}");
        }
        for (name, value) in [
            ("SOURCE_FUNCTION", 3),
            ("COMMENT_ONLY", 13),
            ("STRING_ONLY", 14),
        ] {
            assert!(
                source.contains(&format!("enum {{ {name} = {value} }};")),
                "{source}"
            );
        }
    }

    #[test]
    fn enum_constant_scan_does_not_treat_a_forward_declaration_as_a_definition() {
        let definitions = collect_enum_constant_definitions(
            "enum forward; int probe(void) { BODY_LABEL: return 0; }",
        );

        assert!(definitions.is_empty(), "{definitions:?}");
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
