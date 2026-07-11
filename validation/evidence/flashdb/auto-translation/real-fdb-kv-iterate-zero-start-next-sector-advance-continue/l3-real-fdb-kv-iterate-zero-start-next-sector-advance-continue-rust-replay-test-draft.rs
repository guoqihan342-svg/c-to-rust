// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_zero_start_next_sector_advance_continue_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-zero-start-next-sector-advance-continue.json";
    let _api = "fdb_kv_iterate_zero_start_next_sector_advance_continue_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Fixture-only external stimulus; real callee semantics are not verified.
    {
        let case_id = "zero-start-ordinary";
        __c2r_scripted_external_set_return(4294967295u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_zero_start_ordinary_db = Database { observed: 11u32, sec_size: 7u32 };
        let actual_zero_start_ordinary_sector_seed = Sector { seed: 13u32, addr: 100u32 };
        let actual_zero_start_ordinary_SECTOR_HDR_DATA_SIZE = 24u32;
        let mut actual_zero_start_ordinary_itr = Owner { curr: Kv { addr: Address { start: 0u32 } }, traversed_len: 19u32 };
        let actual_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&mut actual_zero_start_ordinary_db, actual_zero_start_ordinary_sector_seed, actual_zero_start_ordinary_SECTOR_HDR_DATA_SIZE, &mut actual_zero_start_ordinary_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 0usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (0u32, 0u32, 0u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_zero_start_ordinary_itr.curr.addr.start, 124u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_zero_start_ordinary_itr.traversed_len, 19u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "zero-start-u32-wrap";
        __c2r_scripted_external_set_return(0u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_zero_start_u32_wrap_db = Database { observed: 21u32, sec_size: 9u32 };
        let actual_zero_start_u32_wrap_sector_seed = Sector { seed: 23u32, addr: 4294967288u32 };
        let actual_zero_start_u32_wrap_SECTOR_HDR_DATA_SIZE = 16u32;
        let mut actual_zero_start_u32_wrap_itr = Owner { curr: Kv { addr: Address { start: 0u32 } }, traversed_len: 29u32 };
        let actual_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&mut actual_zero_start_u32_wrap_db, actual_zero_start_u32_wrap_sector_seed, actual_zero_start_u32_wrap_SECTOR_HDR_DATA_SIZE, &mut actual_zero_start_u32_wrap_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 0usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (0u32, 0u32, 0u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_zero_start_u32_wrap_itr.curr.addr.start, 8u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_zero_start_u32_wrap_itr.traversed_len, 29u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "sentinel-hit";
        __c2r_scripted_external_set_return(4294967295u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_sentinel_hit_db = Database { observed: 31u32, sec_size: 9u32 };
        let actual_sentinel_hit_sector_seed = Sector { seed: 33u32, addr: 34u32 };
        let actual_sentinel_hit_SECTOR_HDR_DATA_SIZE = 35u32;
        let mut actual_sentinel_hit_itr = Owner { curr: Kv { addr: Address { start: 36u32 } }, traversed_len: 4294967292u32 };
        let actual_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&mut actual_sentinel_hit_db, actual_sentinel_hit_sector_seed, actual_sentinel_hit_SECTOR_HDR_DATA_SIZE, &mut actual_sentinel_hit_itr);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (31u32, 33u32, 36u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_sentinel_hit_itr.curr.addr.start, 0u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_sentinel_hit_itr.traversed_len, 5u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "zero-miss";
        __c2r_scripted_external_set_return(0u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_zero_miss_db = Database { observed: 41u32, sec_size: 42u32 };
        let actual_zero_miss_sector_seed = Sector { seed: 43u32, addr: 44u32 };
        let actual_zero_miss_SECTOR_HDR_DATA_SIZE = 45u32;
        let mut actual_zero_miss_itr = Owner { curr: Kv { addr: Address { start: 46u32 } }, traversed_len: 47u32 };
        let actual_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&mut actual_zero_miss_db, actual_zero_miss_sector_seed, actual_zero_miss_SECTOR_HDR_DATA_SIZE, &mut actual_zero_miss_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (41u32, 43u32, 46u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_zero_miss_itr.curr.addr.start, 0u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_zero_miss_itr.traversed_len, 47u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "ordinary-miss";
        __c2r_scripted_external_set_return(7u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_ordinary_miss_db = Database { observed: 51u32, sec_size: 52u32 };
        let actual_ordinary_miss_sector_seed = Sector { seed: 53u32, addr: 54u32 };
        let actual_ordinary_miss_SECTOR_HDR_DATA_SIZE = 55u32;
        let mut actual_ordinary_miss_itr = Owner { curr: Kv { addr: Address { start: 56u32 } }, traversed_len: 57u32 };
        let actual_return = fdb_kv_iterate_zero_start_next_sector_advance_continue_probe(&mut actual_ordinary_miss_db, actual_ordinary_miss_sector_seed, actual_ordinary_miss_SECTOR_HDR_DATA_SIZE, &mut actual_ordinary_miss_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (51u32, 53u32, 56u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_ordinary_miss_itr.curr.addr.start, 7u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_ordinary_miss_itr.traversed_len, 57u32, "{} add state drifted", case_id);
    }
}
