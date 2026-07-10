// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_traversed_len_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-traversed-len.json";
    let _api = "fdb_kv_iterate_traversed_len_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact u32 record-field wrapping-add fixture replay.
    {
        let case_id = "first-sector";
        let mut actual_first_sector_db = Database { sec_size: 4096u32 };
        let mut actual_first_sector_itr = FdbKvIterator { traversed_len: 0u32 };
        let expected_state = actual_first_sector_itr.traversed_len.wrapping_add(actual_first_sector_db.sec_size);
        assert_eq!(expected_state, 4096u32, "{} declared wrapping state drifted", case_id);
        let actual_return = fdb_kv_iterate_traversed_len_probe(&mut actual_first_sector_db, &mut actual_first_sector_itr);
        assert_eq!(actual_first_sector_itr.traversed_len, expected_state, "{} wrapping state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "accumulated-sectors";
        let mut actual_accumulated_sectors_db = Database { sec_size: 4096u32 };
        let mut actual_accumulated_sectors_itr = FdbKvIterator { traversed_len: 8192u32 };
        let expected_state = actual_accumulated_sectors_itr.traversed_len.wrapping_add(actual_accumulated_sectors_db.sec_size);
        assert_eq!(expected_state, 12288u32, "{} declared wrapping state drifted", case_id);
        let actual_return = fdb_kv_iterate_traversed_len_probe(&mut actual_accumulated_sectors_db, &mut actual_accumulated_sectors_itr);
        assert_eq!(actual_accumulated_sectors_itr.traversed_len, expected_state, "{} wrapping state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "u32-wrap";
        let mut actual_u32_wrap_db = Database { sec_size: 5u32 };
        let mut actual_u32_wrap_itr = FdbKvIterator { traversed_len: 4294967294u32 };
        let expected_state = actual_u32_wrap_itr.traversed_len.wrapping_add(actual_u32_wrap_db.sec_size);
        assert_eq!(expected_state, 3u32, "{} declared wrapping state drifted", case_id);
        let actual_return = fdb_kv_iterate_traversed_len_probe(&mut actual_u32_wrap_db, &mut actual_u32_wrap_itr);
        assert_eq!(actual_u32_wrap_itr.traversed_len, expected_state, "{} wrapping state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
