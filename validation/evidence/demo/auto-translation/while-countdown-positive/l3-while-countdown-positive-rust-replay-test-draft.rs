// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_while_countdown_positive_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/while-countdown-positive-c-oracle.json";
    let _api = "while_countdown_positive";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value: i32,
        return_value: i32,
        status: &'static str,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "negative", value: -3i32, return_value: -3i32, status: "ok" },
        FixtureCase { id: "zero", value: 0i32, return_value: 0i32, status: "ok" },
        FixtureCase { id: "one", value: 1i32, return_value: 0i32, status: "ok" },
        FixtureCase { id: "three", value: 3i32, return_value: 0i32, status: "ok" },
        FixtureCase { id: "seven", value: 7i32, return_value: 0i32, status: "ok" },
    ];
    assert_eq!(fixture_cases.len(), 5usize, "fixture case count drifted");
    for case in fixture_cases {
        let actual = while_countdown_positive(case.value);
        assert_eq!(actual, case.return_value, "{} return_value drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
    }
}
