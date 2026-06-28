// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_calc_crc32_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-calc-crc32.json";
    let _api = "fdb_calc_crc32";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        crc: u32,
        buf: &'static [u8],
        size: usize,
        return_code: u32,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "empty-crc-zero", crc: 0u32, buf: &[], size: 0usize, return_code: 0u32 },
        FixtureCase { id: "ascii-123456789-crc-zero", crc: 0u32, buf: &[49u8, 50u8, 51u8, 52u8, 53u8, 54u8, 55u8, 56u8, 57u8], size: 9usize, return_code: 3421780262u32 },
    ];
    assert_eq!(fixture_cases.len(), 2usize, "fixture case count drifted");
    for case in fixture_cases {
        assert_eq!(case.buf.len(), case.size, "{} fixture size must match byte buffer length", case.id);
        let actual = fdb_calc_crc32(case.crc, case.buf, case.size);
        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);
    }
}
