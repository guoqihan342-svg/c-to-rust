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
