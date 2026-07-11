// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_sector_advance_continue_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-advance-continue.json";
    let _api = "fdb_kv_iterate_sector_advance_continue_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact safe reset/add/current-while-continue fixture replay.
    {
        let case_id = "ordinary-sector-advance";
        let actual_ordinary_sector_advance_db = Database { sec_size: 4096u32 };
        let mut actual_ordinary_sector_advance_itr = FdbKvIterator { curr_kv: Kv { addr: Address { start: 8192u32 } }, traversed_len: 4096u32 };
        let actual_return = fdb_kv_iterate_sector_advance_continue_probe(&actual_ordinary_sector_advance_db, &mut actual_ordinary_sector_advance_itr);
        assert_eq!(actual_ordinary_sector_advance_itr.curr_kv.addr.start, 0u32, "{} reset state drifted", case_id);
        assert_eq!(actual_ordinary_sector_advance_itr.traversed_len, 8192u32, "{} add state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "zero-sector-size";
        let actual_zero_sector_size_db = Database { sec_size: 0u32 };
        let mut actual_zero_sector_size_itr = FdbKvIterator { curr_kv: Kv { addr: Address { start: 1u32 } }, traversed_len: 17u32 };
        let actual_return = fdb_kv_iterate_sector_advance_continue_probe(&actual_zero_sector_size_db, &mut actual_zero_sector_size_itr);
        assert_eq!(actual_zero_sector_size_itr.curr_kv.addr.start, 0u32, "{} reset state drifted", case_id);
        assert_eq!(actual_zero_sector_size_itr.traversed_len, 17u32, "{} add state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "u32-wrap-and-maximum-address";
        let actual_u32_wrap_and_maximum_address_db = Database { sec_size: 5u32 };
        let mut actual_u32_wrap_and_maximum_address_itr = FdbKvIterator { curr_kv: Kv { addr: Address { start: 4294967295u32 } }, traversed_len: 4294967294u32 };
        let actual_return = fdb_kv_iterate_sector_advance_continue_probe(&actual_u32_wrap_and_maximum_address_db, &mut actual_u32_wrap_and_maximum_address_itr);
        assert_eq!(actual_u32_wrap_and_maximum_address_itr.curr_kv.addr.start, 0u32, "{} reset state drifted", case_id);
        assert_eq!(actual_u32_wrap_and_maximum_address_itr.traversed_len, 3u32, "{} add state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
