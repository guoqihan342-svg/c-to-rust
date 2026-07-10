// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_sector_tail_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-tail.json";
    let _api = "fdb_kv_iterate_sector_tail_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Finite fixture sequence; real external callee semantics are not verified.
    {
        let case_id = "failed-address-first";
        __c2r_scripted_external_set_sequence(&[4294967295u32]);
        __c2r_scripted_external_reset_calls();
        let mut actual_failed_address_first_db = Database { generation: 17u32 };
        let actual_failed_address_first_sector_seed = Sector { offset: 29u32 };
        let mut actual_failed_address_first_itr = FdbKvIterator { sector_addr: 0u32, traversed_len: 41u32 };
        let actual_return = fdb_kv_iterate_sector_tail_probe(&mut actual_failed_address_first_db, actual_failed_address_first_sector_seed, &mut actual_failed_address_first_itr);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(actual_failed_address_first_itr.sector_addr, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), vec![[17u32, 29u32, 41u32]], "{} external call arguments drifted", case_id);
    }
    {
        let case_id = "one-sector-then-failed";
        __c2r_scripted_external_set_sequence(&[4096u32, 4294967295u32]);
        __c2r_scripted_external_reset_calls();
        let mut actual_one_sector_then_failed_db = Database { generation: 3u32 };
        let actual_one_sector_then_failed_sector_seed = Sector { offset: 5u32 };
        let mut actual_one_sector_then_failed_itr = FdbKvIterator { sector_addr: 99u32, traversed_len: 7u32 };
        let actual_return = fdb_kv_iterate_sector_tail_probe(&mut actual_one_sector_then_failed_db, actual_one_sector_then_failed_sector_seed, &mut actual_one_sector_then_failed_itr);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(actual_one_sector_then_failed_itr.sector_addr, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 2usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), vec![[3u32, 5u32, 7u32], [3u32, 5u32, 7u32]], "{} external call arguments drifted", case_id);
    }
    {
        let case_id = "two-sectors-then-failed";
        __c2r_scripted_external_set_sequence(&[12288u32, 16384u32, 4294967295u32]);
        __c2r_scripted_external_reset_calls();
        let mut actual_two_sectors_then_failed_db = Database { generation: 305419896u32 };
        let actual_two_sectors_then_failed_sector_seed = Sector { offset: 2271560481u32 };
        let mut actual_two_sectors_then_failed_itr = FdbKvIterator { sector_addr: 17u32, traversed_len: 8192u32 };
        let actual_return = fdb_kv_iterate_sector_tail_probe(&mut actual_two_sectors_then_failed_db, actual_two_sectors_then_failed_sector_seed, &mut actual_two_sectors_then_failed_itr);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(actual_two_sectors_then_failed_itr.sector_addr, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 3usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), vec![[305419896u32, 2271560481u32, 8192u32], [305419896u32, 2271560481u32, 8192u32], [305419896u32, 2271560481u32, 8192u32]], "{} external call arguments drifted", case_id);
    }
}
