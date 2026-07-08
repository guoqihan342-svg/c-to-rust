// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_sparse_designated_array_lookup_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/sparse-designated-array-lookup-c-oracle.json";
    let _api = "sparse_designated_array_lookup";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        index: i32,
        return_value: i32,
        status: &'static str,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "index-zero", index: 0i32, return_value: 0i32, status: "ok" },
        FixtureCase { id: "index-one", index: 1i32, return_value: 0i32, status: "ok" },
        FixtureCase { id: "index-two", index: 2i32, return_value: 7i32, status: "ok" },
        FixtureCase { id: "index-three", index: 3i32, return_value: 0i32, status: "ok" },
    ];
    assert_eq!(fixture_cases.len(), 4usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = sparse_designated_array_lookup(case.index);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
    }
}
