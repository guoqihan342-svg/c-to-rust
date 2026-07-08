// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_add_one_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/add-one-c-oracle.json";
    let _api = "add_one";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value: i32,
        return_value: i32,
        status: &'static str,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "int-min", value: -2147483648i32, return_value: -2147483647i32, status: "ok" },
        FixtureCase { id: "zero", value: 0i32, return_value: 1i32, status: "ok" },
        FixtureCase { id: "int-max-minus-one", value: 2147483646i32, return_value: 2147483647i32, status: "ok" },
    ];
    assert_eq!(fixture_cases.len(), 3usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = add_one(case.value);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
    }
}
