// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_is_str_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-is-str.json";
    let _api = "fdb_is_str";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value: &'static [u8],
        len: usize,
        return_value: bool,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "empty", value: &[], len: 0usize, return_value: true },
        FixtureCase { id: "all-printable", value: &[70u8, 108u8, 97u8, 115u8, 104u8, 68u8, 66u8, 32u8, 49u8, 46u8, 48u8, 33u8], len: 12usize, return_value: true },
        FixtureCase { id: "printable-boundaries", value: &[32u8, 126u8], len: 2usize, return_value: true },
        FixtureCase { id: "below-printable-range", value: &[31u8], len: 1usize, return_value: false },
        FixtureCase { id: "upper-exclusive-boundary", value: &[127u8], len: 1usize, return_value: false },
        FixtureCase { id: "u8-max", value: &[255u8], len: 1usize, return_value: false },
        FixtureCase { id: "internal-nul", value: &[65u8, 66u8, 0u8, 67u8, 68u8], len: 5usize, return_value: false },
        FixtureCase { id: "prefix-length", value: &[65u8, 66u8, 127u8, 0u8, 255u8], len: 2usize, return_value: true },
    ];
    assert_eq!(fixture_cases.len(), 8usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = fdb_is_str(case.value, case.len);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
    }
}
