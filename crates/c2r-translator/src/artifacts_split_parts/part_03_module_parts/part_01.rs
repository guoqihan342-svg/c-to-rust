    #[test]
    fn sanitize_host_path_text_replaces_absolute_paths_with_stable_placeholders() {
        assert_eq!(
            sanitize_host_path_text("C:\\Program Files\\LLVM\\bin\\clang.exe").as_deref(),
            Some("<host>/clang.exe")
        );
        assert_eq!(
            sanitize_host_path_text("-IC:/src/FlashDB/inc").as_deref(),
            Some("-I<host>/inc")
        );
        assert_eq!(
            sanitize_host_path_text("/usr/bin/clang").as_deref(),
            Some("<host>/clang")
        );
        assert_eq!(
            sanitize_host_path_text("-I/usr/include").as_deref(),
            Some("-I<host>/include")
        );
        assert_eq!(sanitize_host_path_text("src/fdb_utils.c"), None);
        assert_eq!(sanitize_host_path_text("-Xclang"), None);
        assert_eq!(
            sanitize_host_path_text("https://json-schema.org/draft-07/schema#"),
            None
        );
    }

    #[test]
    fn typed_ir_candidate_evidence_records_signed_left_shift_and_negation_preconditions() {
        let i32_ty = int_type("int", true, 32);
        let function = IrFunction {
            name: "signed_shift_negation".to_string(),
            return_type: i32_ty.clone(),
            params: vec![
                IrParam {
                    name: "value".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "count".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
            ],
            body: vec![IrStmt::Return {
                value: Some(binary(
                    IrBinOp::Add,
                    binary(
                        IrBinOp::Shl,
                        var("value", &i32_ty),
                        var("count", &i32_ty),
                        &i32_ty,
                    ),
                    IrExpr::Unary {
                        op: IrUnOp::Neg,
                        operand: Box::new(var("value", &i32_ty)),
                        ty: i32_ty.clone(),
                        source_span: None,
                    },
                    &i32_ty,
                )),
                source_span: None,
            }],
            source_span: None,
        };

        let evidence = typed_ir_candidate_evidence(Some(&function), &[], EmitPolicy::default());
        let codes = evidence["runtime_preconditions"]
            .as_array()
            .expect("runtime precondition evidence")
            .iter()
            .map(|item| item["code"].as_str().unwrap())
            .collect::<Vec<_>>();

        assert_eq!(evidence["status"], "generated");
        assert!(codes.contains(&"shift_count_in_range"));
        assert!(codes.contains(&"signed_left_shift_no_overflow"));
        assert!(codes.contains(&"signed_negation_no_overflow"));
    }

    #[test]
    fn clang_lowering_report_artifact_records_parse_spec_errors() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "add-one".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("clang-lowering-report-error");
        fs::create_dir_all(&out_dir).unwrap();

        let path =
            write_clang_lowering_report_artifact(&spec, &out_dir, "l3-add-one", None).unwrap();
        let value: Value = serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap();

        assert_eq!(value["schema_version"], 1);
        assert_eq!(value["artifact_kind"], "clang-lowering-report");
        assert_eq!(value["frontend"], "clang");
        assert_eq!(value["status"], "blocked");
        assert_eq!(value["claim_boundary"]["role"], "diagnostic_only");
        assert_eq!(value["claim_boundary"]["affects_manifest_status"], false);
        assert_eq!(value["claim_boundary"]["affects_semantic_pass"], false);
        assert_eq!(value["typed_ir_candidate"]["status"], "not_available");
        assert_eq!(
            value["typed_ir_candidate"]["runtime_preconditions"]
                .as_array()
                .unwrap()
                .len(),
            0
        );
        assert_eq!(
            value["typed_ir_candidate"]["reason"],
            "clang_parse_spec_error"
        );
        assert_eq!(value["lowering_report"], Value::Null);
        assert_eq!(value["errors"][0]["kind"], "missing_source_root");
        assert!(value.get("translation_carrier").is_none());
    }

    #[test]
    fn translation_carrier_is_bound_verbatim_to_plan_and_lowering_report() {
        let carrier = serde_json::json!({
            "kind": "exact_source_fragment_wrapper",
            "carrier_function": "carrier_probe",
            "real_source": {
                "source_file": "src/source.c",
                "containing_function": "source_fn",
                "line_start": 12,
                "line_end": 12,
                "sha256": "statement-sha"
            },
            "embedding": {
                "mode": "verbatim_once"
            }
        });
        let spec_json = serde_json::json!({
            "target_id": "demo",
            "slice_id": "carrier-binding",
            "source_commit": "1234567",
            "function_name": "carrier_probe",
            "c_source": "int carrier_probe(void) { return 0; }",
            "fixture_hash": "fixture-sha",
            "translation_carrier": carrier,
            "build_profile": profile()
        });
        let spec: SliceSpec = serde_json::from_value(spec_json).unwrap();
        assert_eq!(spec.translation_carrier.as_ref(), Some(&carrier));

        let out_dir = unique_out_dir("translation-carrier-binding");
        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();
        assert_eq!(manifest.status, "blocked");

        let plan: Value = serde_json::from_str(
            &fs::read_to_string(
                out_dir.join("l3-carrier-binding-auto-translation-plan.json"),
            )
            .unwrap(),
        )
        .unwrap();
        let report: Value = serde_json::from_str(
            &fs::read_to_string(
                out_dir.join("l3-carrier-binding-clang-lowering-report.json"),
            )
            .unwrap(),
        )
        .unwrap();

        assert_eq!(plan["translation_carrier"], carrier);
        assert_eq!(report["translation_carrier"], carrier);
        assert_eq!(plan["translation_carrier"], report["translation_carrier"]);

        fs::remove_dir_all(out_dir).unwrap();
    }

    #[test]
    fn clang_lowering_fallback_to_legacy_is_diagnostic_not_generated() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "fallback-identity".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "identity".to_string(),
            c_source: "int identity(int value) { return value; }".to_string(),
            fixture_hash: "fixture-sha".to_string(),
            build_profile: profile(),
            ..SliceSpec::default()
        };
        let out_dir = unique_out_dir("clang-lowering-fallback");

        let manifest = write_translation_artifacts(&spec, &out_dir).unwrap();

        assert_eq!(manifest.status, "blocked");
        let plan: Value = serde_json::from_str(
            &fs::read_to_string(out_dir.join("l3-fallback-identity-auto-translation-plan.json"))
                .unwrap(),
        )
        .unwrap();
        assert_eq!(plan["status"], "blocked");
        assert_eq!(
            plan["translation_source"]["selected"],
            "legacy-string-translator"
        );
        assert_eq!(
            plan["translation_source"]["fallback_from"],
            "clang-lowered-typed-ir"
        );
        assert_eq!(
            plan["translation_source"]["fallback_reason"],
            "clang_lowered_typed_ir_unavailable"
        );
        assert_eq!(plan["errors"][0]["kind"], "legacy_fallback_retired");
        assert!(plan.get("translation_carrier").is_none());

        let events =
            fs::read_to_string(out_dir.join("l3-fallback-identity-auto-translation-events.jsonl"))
                .unwrap();
        assert!(events.contains("\"event\":\"translation_fallback\""));
        assert!(events.contains("\"selected\":\"legacy-string-translator\""));
        assert!(events.contains("\"fallback_from\":\"clang-lowered-typed-ir\""));
        assert!(!events.contains("\"event\":\"translation_generated\""));
    }
