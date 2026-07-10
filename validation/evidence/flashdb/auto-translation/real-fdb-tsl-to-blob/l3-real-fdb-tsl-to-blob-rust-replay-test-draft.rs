// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_tsl_to_blob_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-tsl-to-blob.json";
    let _api = "fdb_tsl_to_blob";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        input_0: u32,
        input_1: u32,
        input_2: u32,
        output_initial_0: u32,
        output_initial_1: u32,
        output_initial_2: u32,
        output_expected_0: u32,
        output_expected_1: u32,
        output_expected_2: u32,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "all-zero", input_0: 0u32, input_1: 0u32, input_2: 0u32, output_initial_0: 88u32, output_initial_1: 99u32, output_initial_2: 77u32, output_expected_0: 0u32, output_expected_1: 0u32, output_expected_2: 0u32 },
        FixtureCase { id: "nominal-tsl", input_0: 4352u32, input_1: 4096u32, input_2: 128u32, output_initial_0: 2u32, output_initial_1: 1u32, output_initial_2: 3u32, output_expected_0: 4352u32, output_expected_1: 4096u32, output_expected_2: 128u32 },
        FixtureCase { id: "u32-max", input_0: 4294967295u32, input_1: 4294967295u32, input_2: 4294967295u32, output_initial_0: 20u32, output_initial_1: 10u32, output_initial_2: 30u32, output_expected_0: 4294967295u32, output_expected_1: 4294967295u32, output_expected_2: 4294967295u32 },
    ];
    assert_eq!(fixture_cases.len(), 3usize, "fixture case count drifted");
    for case in fixture_cases {
        let tsl = FdbTsl { addr: FdbTslAddr { log: case.input_0, index: case.input_1 }, log_len: case.input_2 };
        let mut blob = FdbBlob { saved: FdbBlobSaved { addr: case.output_initial_0, meta_addr: case.output_initial_1, len: usize::try_from(case.output_initial_2).expect("record replay u32_to_usize contract") }, buf: core::ptr::null_mut(), size: 0usize };
        let blob_ptr = &mut blob as *mut FdbBlob;
        let returned_ptr = {
            let returned = fdb_tsl_to_blob(&tsl, &mut blob);
            returned as *mut FdbBlob
        };
        assert_eq!(returned_ptr, blob_ptr, "{} return_same_blob drifted", case.id);
        assert_eq!(blob.saved.addr, case.output_expected_0, "{} blob.saved.addr drifted", case.id);
        assert_eq!(blob.saved.meta_addr, case.output_expected_1, "{} blob.saved.meta_addr drifted", case.id);
        assert_eq!(blob.saved.len, usize::try_from(case.output_expected_2).expect("record replay u32_to_usize contract"), "{} blob.saved.len drifted", case.id);
    }
}
