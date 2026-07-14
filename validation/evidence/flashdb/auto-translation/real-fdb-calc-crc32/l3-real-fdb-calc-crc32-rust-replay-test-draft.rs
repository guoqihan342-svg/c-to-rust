// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

// ReplayCallPlan-SHA256: 38096b4beab43f510e8a2cbdba15548b1fe72655ae9d261bf96783fb0cc859fe
#[test]
fn replay_real_fdb_calc_crc32_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-calc-crc32.json";
    let _api = "fdb_calc_crc32";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    let actual_empty_crc_zero_0: u32 = fdb_calc_crc32(0u32, &[], 0usize);
    let observed_empty_crc_zero_0_0: u32 = actual_empty_crc_zero_0;
    if observed_empty_crc_zero_0_0 != 0u32 { panic!("C2R_REPLAY_ASSERT:fe412cf58bb6267a748c9e8667cd409f204c46ab0a15c60189d87048029f61aa"); }
    let actual_ascii_123456789_crc_zero_1: u32 = fdb_calc_crc32(0u32, &[49u8, 50u8, 51u8, 52u8, 53u8, 54u8, 55u8, 56u8, 57u8], 9usize);
    let observed_ascii_123456789_crc_zero_1_0: u32 = actual_ascii_123456789_crc_zero_1;
    if observed_ascii_123456789_crc_zero_1_0 != 3421780262u32 { panic!("C2R_REPLAY_ASSERT:d794d3bf6dbbac7e92640edb03d3ec08e85c0f2eb6b57e5dccba32bcb1cc197b"); }
}
