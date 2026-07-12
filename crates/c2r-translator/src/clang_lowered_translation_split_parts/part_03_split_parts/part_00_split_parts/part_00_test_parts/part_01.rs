
    #[test]
    fn slice_source_translation_unit_binds_record_pointer_typedef_alias_when_struct_is_known() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "record-constructor".to_string(),
            function_name: "set_blob".to_string(),
            c_source: "int set_blob(struct fdb_blob *slot, const char *value) { struct fdb_blob blob; return consume_blob(fdb_blob_make(&blob, value, strlen(value))); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "set_blob".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "slot".to_string(),
                                c_type: "struct fdb_blob *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "fdb_blob_make".to_string(),
                        return_type: "fdb_blob_t".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "blob".to_string(),
                                c_type: "fdb_blob_t".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const void *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "len".to_string(),
                                c_type: "size_t".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                ],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(source.contains("struct fdb_blob { unsigned char _c2r_opaque; };"), "{source}");
        assert!(source.contains("typedef struct fdb_blob *fdb_blob_t;"), "{source}");
        assert!(!source.contains("typedef void *fdb_blob_t;"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_enriches_record_fields_from_accepted_named_slice_evidence() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "record-constructor".to_string(),
            function_name: "set_blob".to_string(),
            c_source: "int set_blob(struct fdb_blob *slot, const char *value) { struct fdb_blob blob; return consume_blob(fdb_blob_make(&blob, value, strlen(value))); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "set_blob".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "slot".to_string(),
                                c_type: "struct fdb_blob *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const char *".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "fdb_blob_make".to_string(),
                        return_type: "fdb_blob_t".to_string(),
                        parameters: vec![
                            CParameter {
                                name: "blob".to_string(),
                                c_type: "fdb_blob_t".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "value".to_string(),
                                c_type: "const void *".to_string(),
                                ..CParameter::default()
                            },
                            CParameter {
                                name: "len".to_string(),
                                c_type: "size_t".to_string(),
                                ..CParameter::default()
                            },
                        ],
                        ..CSignature::default()
                    },
                ],
                external_direct_callees: vec![ExternalDirectCallee {
                    name: "fdb_blob_make".to_string(),
                    accepted_named_slice_evidence: Some(AcceptedNamedSliceEvidence {
                        target_id: "flashdb".to_string(),
                        slice_id: "real-fdb-blob-make".to_string(),
                        final_verification: "validation/evidence/flashdb/auto-translation/real-fdb-blob-make/l3-real-fdb-blob-make-final-verification.json".to_string(),
                        ..AcceptedNamedSliceEvidence::default()
                    }),
                    ..ExternalDirectCallee::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(
            source.contains("struct fdb_blob {\n    void * buf;\n    size_t size;\n};"),
            "{source}"
        );
        assert!(!source.contains("struct fdb_blob { unsigned char _c2r_opaque; };"), "{source}");
        assert!(source.contains("typedef struct fdb_blob *fdb_blob_t;"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_ignores_unaccepted_named_slice_record_fields() {
        let spec = SliceSpec {
            target_id: "flashdb".to_string(),
            slice_id: "record-constructor".to_string(),
            function_name: "set_blob".to_string(),
            c_source: "int set_blob(struct fdb_blob *slot, const char *value) { struct fdb_blob blob; return consume_blob(fdb_blob_make(&blob, value, strlen(value))); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "set_blob".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![CParameter {
                            name: "slot".to_string(),
                            c_type: "struct fdb_blob *".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "fdb_blob_make".to_string(),
                        return_type: "fdb_blob_t".to_string(),
                        parameters: vec![CParameter {
                            name: "blob".to_string(),
                            c_type: "fdb_blob_t".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                ],
                external_direct_callees: vec![ExternalDirectCallee {
                    name: "fdb_blob_make".to_string(),
                    accepted_named_slice_evidence: Some(AcceptedNamedSliceEvidence {
                        target_id: "flashdb".to_string(),
                        slice_id: "real-fdb-kv-set".to_string(),
                        final_verification: "validation/evidence/flashdb/auto-translation/real-fdb-kv-set/l3-real-fdb-kv-set-route-decision.json".to_string(),
                        ..AcceptedNamedSliceEvidence::default()
                    }),
                    ..ExternalDirectCallee::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(
            source.contains("struct fdb_blob { unsigned char _c2r_opaque; };"),
            "{source}"
        );
        assert!(!source.contains("void * buf"), "{source}");
        assert!(!source.contains("size_t size"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_declares_signature_pointer_member_fields() {
        let spec = SliceSpec {
            target_id: "libuv".to_string(),
            slice_id: "ip4-addr".to_string(),
            function_name: "uv_ip4_addr".to_string(),
            c_source: "int uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr) { addr->sin_family = AF_INET; return 0; }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![CSignature {
                    function: "uv_ip4_addr".to_string(),
                    return_type: "int".to_string(),
                    parameters: vec![
                        CParameter {
                            name: "ip".to_string(),
                            c_type: "const char*".to_string(),
                            ..CParameter::default()
                        },
                        CParameter {
                            name: "port".to_string(),
                            c_type: "int".to_string(),
                            ..CParameter::default()
                        },
                        CParameter {
                            name: "addr".to_string(),
                            c_type: "struct sockaddr_in*".to_string(),
                            ..CParameter::default()
                        },
                    ],
                    ..CSignature::default()
                }],
                direct_dependencies: vec![CDirectDependency {
                    kind: "constant".to_string(),
                    name: "AF_INET".to_string(),
                    value: Some(serde_json::json!(2)),
                    ..CDirectDependency::default()
                }],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(
            source.contains("struct sockaddr_in {\n    int sin_family;\n    unsigned char _c2r_opaque;\n};"),
            "{source}"
        );
        assert!(source.contains("enum { AF_INET = 2 };"), "{source}");
    }

    #[test]
    fn slice_source_translation_unit_preserves_complete_source_record_layouts() {
        let spec = SliceSpec {
            target_id: "generic".to_string(),
            slice_id: "nested-record-call".to_string(),
            function_name: "assign_nested".to_string(),
            c_source: "struct Inner { int value; }; struct Outer { struct Inner inner; }; int read_next(struct Outer *slot); int assign_nested(struct Outer *slot) { return (slot->inner.value = read_next(slot)); }".to_string(),
            c_boundary: CBoundary {
                signatures: vec![
                    CSignature {
                        function: "assign_nested".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![CParameter {
                            name: "slot".to_string(),
                            c_type: "struct Outer *".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                    CSignature {
                        role: "external_direct_callee".to_string(),
                        function: "read_next".to_string(),
                        return_type: "int".to_string(),
                        parameters: vec![CParameter {
                            name: "slot".to_string(),
                            c_type: "struct Outer *".to_string(),
                            ..CParameter::default()
                        }],
                        ..CSignature::default()
                    },
                ],
                ..CBoundary::default()
            },
            ..SliceSpec::default()
        };

        let source = slice_source_translation_unit(&spec);

        assert!(source.contains("struct Inner;\nstruct Outer;\n"), "{source}");
        assert_eq!(source.matches("struct Inner {").count(), 1, "{source}");
        assert_eq!(source.matches("struct Outer {").count(), 1, "{source}");
        assert!(!source.contains("int inner;"), "{source}");
        assert!(source.contains("int read_next(struct Outer * slot);"), "{source}");
    }
