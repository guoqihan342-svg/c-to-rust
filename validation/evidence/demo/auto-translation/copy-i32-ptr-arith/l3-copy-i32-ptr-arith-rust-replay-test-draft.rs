// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_copy_i32_ptr_arith_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/copy-i32-ptr-arith-c-oracle.json";
    let _api = "copy_i32_ptr_arith";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        values: &'static [i32],
        len: i32,
        return_code: i32,
        status: &'static str,
        out_values: &'static [i32],
        source_reads: &'static str,
        canonical_reads: &'static str,
        source_writes: &'static str,
        canonical_writes: &'static str,
        write_count: usize,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "empty", values: &[], len: 0i32, return_code: 0i32, status: "ok", out_values: &[], source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_writes: "*(out + i) under i < len", canonical_writes: "out[i]", write_count: 0usize },
        FixtureCase { id: "single-positive", values: &[7i32], len: 1i32, return_code: 0i32, status: "ok", out_values: &[7i32], source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_writes: "*(out + i) under i < len", canonical_writes: "out[i]", write_count: 1usize },
        FixtureCase { id: "mixed-negative", values: &[-5i32, 2i32, -3i32, 6i32], len: 4i32, return_code: 0i32, status: "ok", out_values: &[-5i32, 2i32, -3i32, 6i32], source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_writes: "*(out + i) under i < len", canonical_writes: "out[i]", write_count: 4usize },
        FixtureCase { id: "boundary-safe", values: &[1073741823i32, -1073741824i32, -1i32], len: 3i32, return_code: 0i32, status: "ok", out_values: &[1073741823i32, -1073741824i32, -1i32], source_reads: "*(values + i) under i < len", canonical_reads: "values[i]", source_writes: "*(out + i) under i < len", canonical_writes: "out[i]", write_count: 3usize },
    ];
    assert_eq!(fixture_cases.len(), 4usize, "fixture case count drifted");
    for case in fixture_cases {
        assert_eq!(case.values.len(), case.len as usize, "{} input length drifted", case.id);
        assert_eq!(case.out_values.len(), case.len as usize, "{} output length drifted", case.id);
        assert_eq!(case.write_count, case.len as usize, "{} write_count drifted", case.id);
        let mut out = vec![0i32; case.out_values.len()];
        let actual = copy_i32_ptr_arith(case.values, case.len, &mut out);
        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);
        assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);
        assert_eq!(out.as_slice(), case.out_values, "{} out_values drifted", case.id);
        assert_eq!(case.source_reads, "*(values + i) under i < len", "{} source_reads drifted", case.id);
        assert_eq!(case.canonical_reads, "values[i]", "{} canonical_reads drifted", case.id);
        assert_eq!(case.source_writes, "*(out + i) under i < len", "{} source_writes drifted", case.id);
        assert_eq!(case.canonical_writes, "out[i]", "{} canonical_writes drifted", case.id);
    }
}
