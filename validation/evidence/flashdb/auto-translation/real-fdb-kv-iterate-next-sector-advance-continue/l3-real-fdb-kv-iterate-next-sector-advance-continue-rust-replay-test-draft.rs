// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_next_sector_advance_continue_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-next-sector-advance-continue.json";
    let _api = "fdb_kv_iterate_next_sector_advance_continue_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Fixture-only external stimulus; real callee semantics are not verified.
    {
        let case_id = "sentinel-hit-ordinary";
        __c2r_scripted_external_set_return(4294967295u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_sentinel_hit_ordinary_db = Database { observed: 41u32, sec_size: 7u32 };
        let actual_sentinel_hit_ordinary_sector_seed = Sector { seed: 23u32 };
        let mut actual_sentinel_hit_ordinary_itr = Owner { curr: Kv { addr: Address { start: 99u32 } }, traversed_len: 10u32 };
        let actual_return = fdb_kv_iterate_next_sector_advance_continue_probe(&mut actual_sentinel_hit_ordinary_db, actual_sentinel_hit_ordinary_sector_seed, &mut actual_sentinel_hit_ordinary_itr);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (41u32, 23u32, 99u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_sentinel_hit_ordinary_itr.curr.addr.start, 0u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_sentinel_hit_ordinary_itr.traversed_len, 17u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "sentinel-hit-u32-wrap";
        __c2r_scripted_external_set_return(4294967295u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_sentinel_hit_u32_wrap_db = Database { observed: 4294967295u32, sec_size: 5u32 };
        let actual_sentinel_hit_u32_wrap_sector_seed = Sector { seed: 0u32 };
        let mut actual_sentinel_hit_u32_wrap_itr = Owner { curr: Kv { addr: Address { start: 1u32 } }, traversed_len: 4294967294u32 };
        let actual_return = fdb_kv_iterate_next_sector_advance_continue_probe(&mut actual_sentinel_hit_u32_wrap_db, actual_sentinel_hit_u32_wrap_sector_seed, &mut actual_sentinel_hit_u32_wrap_itr);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (4294967295u32, 0u32, 1u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_sentinel_hit_u32_wrap_itr.curr.addr.start, 0u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_sentinel_hit_u32_wrap_itr.traversed_len, 3u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "zero-miss";
        __c2r_scripted_external_set_return(0u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_zero_miss_db = Database { observed: 17u32, sec_size: 9u32 };
        let actual_zero_miss_sector_seed = Sector { seed: 31u32 };
        let mut actual_zero_miss_itr = Owner { curr: Kv { addr: Address { start: 77u32 } }, traversed_len: 100u32 };
        let actual_return = fdb_kv_iterate_next_sector_advance_continue_probe(&mut actual_zero_miss_db, actual_zero_miss_sector_seed, &mut actual_zero_miss_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (17u32, 31u32, 77u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_zero_miss_itr.curr.addr.start, 0u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_zero_miss_itr.traversed_len, 100u32, "{} add state drifted", case_id);
    }
    {
        let case_id = "ordinary-nonzero-miss";
        __c2r_scripted_external_set_return(7u32);
        __c2r_scripted_external_reset_calls();
        let mut actual_ordinary_nonzero_miss_db = Database { observed: 3u32, sec_size: 11u32 };
        let actual_ordinary_nonzero_miss_sector_seed = Sector { seed: 44u32 };
        let mut actual_ordinary_nonzero_miss_itr = Owner { curr: Kv { addr: Address { start: 88u32 } }, traversed_len: 200u32 };
        let actual_return = fdb_kv_iterate_next_sector_advance_continue_probe(&mut actual_ordinary_nonzero_miss_db, actual_ordinary_nonzero_miss_sector_seed, &mut actual_ordinary_nonzero_miss_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), (3u32, 44u32, 88u32), "{} call snapshots drifted", case_id);
        assert_eq!(actual_ordinary_nonzero_miss_itr.curr.addr.start, 7u32, "{} assigned state drifted", case_id);
        assert_eq!(actual_ordinary_nonzero_miss_itr.traversed_len, 200u32, "{} add state drifted", case_id);
    }
}
