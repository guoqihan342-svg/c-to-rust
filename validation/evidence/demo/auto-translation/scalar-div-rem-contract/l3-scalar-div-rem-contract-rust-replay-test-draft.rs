// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_scalar_div_rem_contract_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/scalar-div-rem-contract-c-oracle.json";
    let _api = "scalar_div_rem_contract";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value: i32,
        return_value: i32,
        status: &'static str,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "int-min", value: -2147483648i32, return_value: -715827885i32, status: "ok" },
        FixtureCase { id: "negative", value: -17i32, return_value: -7i32, status: "ok" },
        FixtureCase { id: "zero", value: 0i32, return_value: 0i32, status: "ok" },
        FixtureCase { id: "int-max", value: 2147483647i32, return_value: 715827884i32, status: "ok" },
    ];
    assert_eq!(fixture_cases.len(), 4usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = scalar_div_rem_contract(case.value);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
    }
}
