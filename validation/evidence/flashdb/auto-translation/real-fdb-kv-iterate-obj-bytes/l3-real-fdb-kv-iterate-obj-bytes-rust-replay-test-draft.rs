// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_obj_bytes_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-obj-bytes.json";
    let _api = "fdb_kv_iterate_obj_bytes_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact LP64 owner-interior u32-to-usize wrapping-add fixture replay.
    {
        let case_id = "ordinary-add";
        let mut actual_ordinary_add_itr = FdbKvIterator { curr_kv: FdbKv { len: 5u32 }, iterated_obj_bytes: 11usize };
        let expected_state = actual_ordinary_add_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_ordinary_add_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state, 16usize, "{} declared usize state drifted", case_id);
        let actual_return = fdb_kv_iterate_obj_bytes_probe(&mut actual_ordinary_add_itr);
        assert_eq!(actual_ordinary_add_itr.iterated_obj_bytes, expected_state, "{} usize state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "zero-rhs";
        let mut actual_zero_rhs_itr = FdbKvIterator { curr_kv: FdbKv { len: 0u32 }, iterated_obj_bytes: 42usize };
        let expected_state = actual_zero_rhs_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_zero_rhs_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state, 42usize, "{} declared usize state drifted", case_id);
        let actual_return = fdb_kv_iterate_obj_bytes_probe(&mut actual_zero_rhs_itr);
        assert_eq!(actual_zero_rhs_itr.iterated_obj_bytes, expected_state, "{} usize state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "usize-wrap";
        let mut actual_usize_wrap_itr = FdbKvIterator { curr_kv: FdbKv { len: 3u32 }, iterated_obj_bytes: 18446744073709551614usize };
        let expected_state = actual_usize_wrap_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_usize_wrap_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state, 1usize, "{} declared usize state drifted", case_id);
        let actual_return = fdb_kv_iterate_obj_bytes_probe(&mut actual_usize_wrap_itr);
        assert_eq!(actual_usize_wrap_itr.iterated_obj_bytes, expected_state, "{} usize state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
