// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_sum_i32_ptr_arith_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/sum-i32-ptr-arith-c-oracle.json";
    let _api = "sum_i32_ptr_arith";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        values: &'static [i32],
        len: i32,
        return_code: i32,
        status: &'static str,
        sum: i32,
        source_reads: &'static str,
        canonical_reads: &'static str,
        source_write: &'static str,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "empty", values: &[], len: 0i32, return_code: 0i32, status: "ok", sum: 0i32, source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_write: "out[0]" },
        FixtureCase { id: "single-positive", values: &[7i32], len: 1i32, return_code: 0i32, status: "ok", sum: 7i32, source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_write: "out[0]" },
        FixtureCase { id: "mixed-negative", values: &[-5i32, 2i32, -3i32, 6i32], len: 4i32, return_code: 0i32, status: "ok", sum: 0i32, source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_write: "out[0]" },
        FixtureCase { id: "boundary-safe", values: &[1073741823i32, 1073741823i32, -1i32], len: 3i32, return_code: 0i32, status: "ok", sum: 2147483645i32, source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_write: "out[0]" },
    ];
    assert_eq!(fixture_cases.len(), 4usize, "fixture case count drifted");
    for case in fixture_cases {
        assert_eq!(case.values.len(), case.len as usize, "{} input length drifted", case.id);
        let mut out = [0i32; 1];
        let actual = sum_i32_ptr_arith(case.values, case.len, &mut out);
        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
        assert_eq!(out[0], case.sum, "{} sum drifted", case.id);
        assert_eq!(case.source_reads, "*(values + i) under i < len", "{} source_reads drifted", case.id);
        assert_eq!(case.canonical_reads, "values[i]", "{} canonical_reads drifted", case.id);
        assert_eq!(case.source_write, "out[0]", "{} source_write drifted", case.id);
    }
}
