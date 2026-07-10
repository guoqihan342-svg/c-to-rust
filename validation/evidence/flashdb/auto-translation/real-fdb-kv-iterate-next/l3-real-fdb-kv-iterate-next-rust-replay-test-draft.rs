// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_next_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-next.json";
    let _api = "fdb_kv_iterate_next_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Fixture-only record stimulus; real external callee semantics are not verified.
    {
        let case_id = "failed-address";
        __c2r_scripted_external_set_return(4294967295u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_failed_address_db = Database { generation: 17u32 };
        let actual_failed_address_sector_seed = Sector { offset: 29u32 };
        let mut actual_failed_address_kv = Kv { addr: Address { start: 41u32 } };
        let actual_return = fdb_kv_iterate_next_probe(&mut actual_failed_address_db, actual_failed_address_sector_seed, &mut actual_failed_address_kv);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(actual_failed_address_kv.addr.start, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), [17u32, 29u32, 41u32], "{} external call arguments drifted", case_id);
    }
    {
        let case_id = "zero-address";
        __c2r_scripted_external_set_return(0u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_zero_address_db = Database { generation: 3u32 };
        let actual_zero_address_sector_seed = Sector { offset: 5u32 };
        let mut actual_zero_address_kv = Kv { addr: Address { start: 7u32 } };
        let actual_return = fdb_kv_iterate_next_probe(&mut actual_zero_address_db, actual_zero_address_sector_seed, &mut actual_zero_address_kv);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(actual_zero_address_kv.addr.start, 0u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), [3u32, 5u32, 7u32], "{} external call arguments drifted", case_id);
    }
    {
        let case_id = "next-address";
        __c2r_scripted_external_set_return(8192u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_next_address_db = Database { generation: 305419896u32 };
        let actual_next_address_sector_seed = Sector { offset: 2271560481u32 };
        let mut actual_next_address_kv = Kv { addr: Address { start: 4096u32 } };
        let actual_return = fdb_kv_iterate_next_probe(&mut actual_next_address_db, actual_next_address_sector_seed, &mut actual_next_address_kv);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(actual_next_address_kv.addr.start, 8192u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), [305419896u32, 2271560481u32, 4096u32], "{} external call arguments drifted", case_id);
    }
}
