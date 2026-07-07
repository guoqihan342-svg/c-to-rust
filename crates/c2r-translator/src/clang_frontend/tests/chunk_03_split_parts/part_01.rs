    #[test]
    fn function_return_type_from_type_object_allows_function_pointer_parameter() {
        let type_object = serde_json::json!({
            "qualType": "int (int (*)(int), int)"
        });

        let ty = function_return_type_from_type_object(&type_object).expect(
            "function pointer parameter should not be mistaken for function pointer return",
        );

        assert_eq!(ty.spelled, "int");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
    }

    #[test]
    fn function_return_type_from_type_object_rejects_function_pointer_return() {
        let type_object = serde_json::json!({
            "qualType": "int (*(void))(int)"
        });

        let err = function_return_type_from_type_object(&type_object)
            .expect_err("function pointer return must fail closed");

        assert_eq!(err.kind, "unsupported_function_type");
        assert!(err.message.contains("function pointer return"));
        assert!(err.message.contains("explicit"));
    }

    #[test]
    fn type_from_qual_type_maps_signed_char_scalar() {
        let ty = type_from_qual_type("signed char").expect("signed char type");

        assert_eq!(ty.spelled, "signed char");
        assert_eq!(ty.canonical, "signed char");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 8
            }
        ));
    }

    #[test]
    fn type_from_qual_type_keeps_target_dependent_integer_spellings_unsupported() {
        for spelling in [
            "char",
            "short",
            "unsigned short",
            "long",
            "unsigned long",
            "long long",
            "unsigned long long",
            "size_t",
        ] {
            let ty = type_from_qual_type(spelling).expect("type skeleton");

            assert!(matches!(
                ty.kind,
                ClangTypeKind::Unsupported { ref reason }
                    if reason.contains("requires target ABI width provenance")
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_lp64_integer_widths() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        for (spelling, expected_signed, expected_width) in [
            ("char", true, 8),
            ("short", true, 16),
            ("unsigned short", false, 16),
            ("long", true, 64),
            ("unsigned long", false, 64),
            ("long long", true, 64),
            ("unsigned long long", false, 64),
            ("size_t", false, 64),
        ] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert_eq!(ty.spelled, spelling);
            assert!(matches!(
                ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if signed == expected_signed && width == expected_width
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_int_width() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        for (spelling, expected_signed) in [("int", true), ("unsigned int", false)] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert_eq!(ty.spelled, spelling);
            assert!(matches!(
                ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if signed == expected_signed && width == 16
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_pointer_width() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        let ty = type_from_qual_type_with_target_abi("const int *", Some(&abi))
            .expect("pointer type skeleton");

        assert_eq!(ty.spelled, "const int *");
        let ClangTypeKind::Pointer { pointee, width } = ty.kind else {
            panic!("expected pointer type, got {:?}", ty.kind);
        };
        assert_eq!(width, Some(64));
        assert_eq!(pointee.canonical, "int");
    }

    #[test]
    fn type_from_qual_type_maps_function_pointer_with_function_pointer_param() {
        let ty = type_from_qual_type("int (*)(int (*)(int), int)")
            .expect("function pointer type skeleton");

        let ClangTypeKind::Pointer { pointee, .. } = ty.kind else {
            panic!("expected function pointer type, got {:?}", ty.kind);
        };
        assert_eq!(ty.spelled, "int (*)(int (*)(int), int)");
        assert_eq!(pointee.spelled, "int (int (*)(int), int)");
        assert!(matches!(pointee.kind, ClangTypeKind::Function));
    }

    #[test]
    fn type_from_qual_type_with_target_abi_keeps_unproven_integer_widths_unsupported() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 0,
            plain_char_signed: None,
            short_width: 0,
            long_width: 64,
            long_long_width: 0,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        for spelling in [
            "char",
            "short",
            "unsigned short",
            "long long",
            "unsigned long long",
        ] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert!(matches!(
                ty.kind,
                ClangTypeKind::Unsupported { ref reason }
                    if reason.contains("requires an explicit target ABI width field")
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_unrecognized_target_abi_stays_fail_closed() {
        let ty = type_from_qual_type_with_target_abi("size_t", None).expect("type skeleton");

        assert!(matches!(
            ty.kind,
            ClangTypeKind::Unsupported { ref reason }
                if reason.contains("requires target ABI width provenance")
        ));
    }
