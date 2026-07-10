// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_new_kv_alloc_compare_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-new-kv-alloc-compare.json";
    let _api = "fdb_alloc_compare_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Fixture-only external stimulus; real external callee semantics are not verified.
    struct FixtureCase {
        id: &'static str,
        arg0: u32,
        arg1: u32,
        arg2: usize,
        scripted_return: u32,
        expected_return: bool,
        expected_out: u32,
        expected_call_count: usize,
        expected_call_args: (u32, u32, usize),
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "failed-address", arg0: 17u32, arg1: 29u32, arg2: 64usize, scripted_return: 4294967295u32, expected_return: true, expected_out: 4294967295u32, expected_call_count: 1usize, expected_call_args: (17u32, 29u32, 64usize) },
        FixtureCase { id: "zero-address", arg0: 3u32, arg1: 5u32, arg2: 0usize, scripted_return: 0u32, expected_return: false, expected_out: 0u32, expected_call_count: 1usize, expected_call_args: (3u32, 5u32, 0usize) },
        FixtureCase { id: "allocated-address", arg0: 305419896u32, arg1: 2271560481u32, arg2: 4096usize, scripted_return: 8192u32, expected_return: false, expected_out: 8192u32, expected_call_count: 1usize, expected_call_args: (305419896u32, 2271560481u32, 4096usize) },
    ];
    assert_eq!(fixture_cases.len(), 3usize, "fixture case count drifted");
    for case in fixture_cases {
        __c2r_scripted_external_set_return(case.scripted_return);
        __c2r_scripted_external_reset_calls();
        let mut actual_out = [0u32; 1];
        let actual_return = fdb_alloc_compare_probe(case.arg0, case.arg1, case.arg2, &mut actual_out);
        assert_eq!(actual_return, case.expected_return, "{} return drifted", case.id);
        assert_eq!(actual_out[0], case.expected_out, "{} u32 out drifted", case.id);
        assert_eq!(
            __c2r_scripted_external_call_count(),
            case.expected_call_count,
            "{} external call count drifted",
            case.id,
        );
        assert_eq!(
            __c2r_scripted_external_call_args(),
            case.expected_call_args,
            "{} external call arguments drifted",
            case.id,
        );
    }
}
