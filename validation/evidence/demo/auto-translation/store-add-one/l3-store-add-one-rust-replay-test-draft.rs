// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_store_add_one_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/store-add-one-c-oracle.json";
    let _api = "store_add_one";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value: i32,
        return_code: i32,
        status: &'static str,
        out0: i32,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "int-min", value: -2147483648i32, return_code: 0i32, status: "ok", out0: -2147483647i32 },
        FixtureCase { id: "zero", value: 0i32, return_code: 0i32, status: "ok", out0: 1i32 },
        FixtureCase { id: "int-max-minus-one", value: 2147483646i32, return_code: 0i32, status: "ok", out0: 2147483647i32 },
    ];
    assert_eq!(fixture_cases.len(), 3usize, "fixture case count drifted");
    for case in fixture_cases {
        let mut out = [0i32; 1];
        let actual = store_add_one(case.value, &mut out);
        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
        assert_eq!(out[0], case.out0, "{} out0 drifted", case.id);
    }
}
