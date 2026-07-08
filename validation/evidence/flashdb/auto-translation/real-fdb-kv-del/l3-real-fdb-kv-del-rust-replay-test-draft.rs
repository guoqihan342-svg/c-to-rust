// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_del_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-del.json";
    let _api = "fdb_kv_del";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        key: &'static [u8],
        return_code: i32,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "uninit-delete", key: &[98u8, 111u8, 111u8, 116u8, 95u8, 99u8, 111u8, 117u8, 110u8, 116u8, 0u8], return_code: 7i32 },
    ];
    assert_eq!(fixture_cases.len(), 1usize, "fixture case count drifted");
    for case in fixture_cases {
        let mut db_marker = 0u8;
        let db = (&mut db_marker as *mut u8).cast::<core::ffi::c_void>();
        let actual = fdb_kv_del(db, case.key.as_ptr().cast::<core::ffi::c_void>());
        assert_eq!(actual, case.return_code, "{} return_code drifted", case.id);
    }
}
