// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_signed_rshift_contract_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/signed-rshift-contract-c-oracle.json";
    let _api = "signed_rshift_contract";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value: i32,
        count: i32,
        return_value: i32,
        status: &'static str,
        contract: &'static str,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "positive-count-zero", value: 7i32, count: 0i32, return_value: 7i32, status: "ok", contract: "implementation_defined_arithmetic_shift" },
        FixtureCase { id: "negative-half", value: -8i32, count: 1i32, return_value: -4i32, status: "ok", contract: "implementation_defined_arithmetic_shift" },
        FixtureCase { id: "minus-one-stays-minus-one", value: -1i32, count: 1i32, return_value: -1i32, status: "ok", contract: "implementation_defined_arithmetic_shift" },
        FixtureCase { id: "int-min-high-count", value: -2147483648i32, count: 30i32, return_value: -2i32, status: "ok", contract: "implementation_defined_arithmetic_shift" },
    ];
    assert_eq!(fixture_cases.len(), 4usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = signed_rshift_contract(case.value, case.count);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
        assert_eq!(case.contract, "implementation_defined_arithmetic_shift", "{} fixture contract drifted", case.id);
    }
}
