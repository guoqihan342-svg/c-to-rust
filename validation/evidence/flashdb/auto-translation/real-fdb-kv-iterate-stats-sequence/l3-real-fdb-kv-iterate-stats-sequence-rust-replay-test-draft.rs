// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_stats_sequence_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-stats-sequence.json";
    let _api = "fdb_kv_iterate_stats_sequence_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact ordered owner-interior stats sequence fixture replay.
    {
        let case_id = "ordinary";
        let mut actual_ordinary_itr = FdbKvIterator { iterated_cnt: 4u32, curr_kv: FdbKv { len: 3u32, value_len: 7u32 }, iterated_obj_bytes: 10usize, iterated_value_bytes: 20usize };
        let expected_state_0 = actual_ordinary_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state_0, 5u32, "{} declared state 0 drifted", case_id);
        let expected_state_1 = actual_ordinary_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_ordinary_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_1, 13usize, "{} declared state 1 drifted", case_id);
        let expected_state_2 = actual_ordinary_itr.iterated_value_bytes.wrapping_add(usize::try_from(actual_ordinary_itr.curr_kv.value_len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_2, 27usize, "{} declared state 2 drifted", case_id);
        let actual_return = fdb_kv_iterate_stats_sequence_probe(&mut actual_ordinary_itr);
        assert_eq!(actual_ordinary_itr.iterated_cnt, expected_state_0, "{} state 0 drifted", case_id);
        assert_eq!(actual_ordinary_itr.iterated_obj_bytes, expected_state_1, "{} state 1 drifted", case_id);
        assert_eq!(actual_ordinary_itr.iterated_value_bytes, expected_state_2, "{} state 2 drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "zero-rhs";
        let mut actual_zero_rhs_itr = FdbKvIterator { iterated_cnt: 8u32, curr_kv: FdbKv { len: 0u32, value_len: 0u32 }, iterated_obj_bytes: 42usize, iterated_value_bytes: 99usize };
        let expected_state_0 = actual_zero_rhs_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state_0, 9u32, "{} declared state 0 drifted", case_id);
        let expected_state_1 = actual_zero_rhs_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_zero_rhs_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_1, 42usize, "{} declared state 1 drifted", case_id);
        let expected_state_2 = actual_zero_rhs_itr.iterated_value_bytes.wrapping_add(usize::try_from(actual_zero_rhs_itr.curr_kv.value_len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_2, 99usize, "{} declared state 2 drifted", case_id);
        let actual_return = fdb_kv_iterate_stats_sequence_probe(&mut actual_zero_rhs_itr);
        assert_eq!(actual_zero_rhs_itr.iterated_cnt, expected_state_0, "{} state 0 drifted", case_id);
        assert_eq!(actual_zero_rhs_itr.iterated_obj_bytes, expected_state_1, "{} state 1 drifted", case_id);
        assert_eq!(actual_zero_rhs_itr.iterated_value_bytes, expected_state_2, "{} state 2 drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "all-wrap";
        let mut actual_all_wrap_itr = FdbKvIterator { iterated_cnt: 4294967295u32, curr_kv: FdbKv { len: 3u32, value_len: 5u32 }, iterated_obj_bytes: 18446744073709551614usize, iterated_value_bytes: 18446744073709551613usize };
        let expected_state_0 = actual_all_wrap_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state_0, 0u32, "{} declared state 0 drifted", case_id);
        let expected_state_1 = actual_all_wrap_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_all_wrap_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_1, 1usize, "{} declared state 1 drifted", case_id);
        let expected_state_2 = actual_all_wrap_itr.iterated_value_bytes.wrapping_add(usize::try_from(actual_all_wrap_itr.curr_kv.value_len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_2, 2usize, "{} declared state 2 drifted", case_id);
        let actual_return = fdb_kv_iterate_stats_sequence_probe(&mut actual_all_wrap_itr);
        assert_eq!(actual_all_wrap_itr.iterated_cnt, expected_state_0, "{} state 0 drifted", case_id);
        assert_eq!(actual_all_wrap_itr.iterated_obj_bytes, expected_state_1, "{} state 1 drifted", case_id);
        assert_eq!(actual_all_wrap_itr.iterated_value_bytes, expected_state_2, "{} state 2 drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "source-discriminator";
        let mut actual_source_discriminator_itr = FdbKvIterator { iterated_cnt: 17u32, curr_kv: FdbKv { len: 1u32, value_len: 9u32 }, iterated_obj_bytes: 100usize, iterated_value_bytes: 200usize };
        let expected_state_0 = actual_source_discriminator_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state_0, 18u32, "{} declared state 0 drifted", case_id);
        let expected_state_1 = actual_source_discriminator_itr.iterated_obj_bytes.wrapping_add(usize::try_from(actual_source_discriminator_itr.curr_kv.len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_1, 101usize, "{} declared state 1 drifted", case_id);
        let expected_state_2 = actual_source_discriminator_itr.iterated_value_bytes.wrapping_add(usize::try_from(actual_source_discriminator_itr.curr_kv.value_len).expect("LP64 u32_to_usize contract"));
        assert_eq!(expected_state_2, 209usize, "{} declared state 2 drifted", case_id);
        let actual_return = fdb_kv_iterate_stats_sequence_probe(&mut actual_source_discriminator_itr);
        assert_eq!(actual_source_discriminator_itr.iterated_cnt, expected_state_0, "{} state 0 drifted", case_id);
        assert_eq!(actual_source_discriminator_itr.iterated_obj_bytes, expected_state_1, "{} state 1 drifted", case_id);
        assert_eq!(actual_source_discriminator_itr.iterated_value_bytes, expected_state_2, "{} state 2 drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
