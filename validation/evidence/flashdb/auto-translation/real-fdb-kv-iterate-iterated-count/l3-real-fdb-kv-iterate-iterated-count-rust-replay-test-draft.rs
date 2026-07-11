// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_iterated_count_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-iterated-count.json";
    let _api = "fdb_kv_iterate_iterated_count_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact direct record-field postfix-increment fixture replay.
    {
        let case_id = "zero";
        let mut actual_zero_itr = FdbKvIterator { iterated_cnt: 0u32 };
        let expected_state = actual_zero_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state, 1u32, "{} declared postfix state drifted", case_id);
        let actual_return = fdb_kv_iterate_iterated_count_probe(&mut actual_zero_itr);
        assert_eq!(actual_zero_itr.iterated_cnt, expected_state, "{} postfix state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "ordinary";
        let mut actual_ordinary_itr = FdbKvIterator { iterated_cnt: 41u32 };
        let expected_state = actual_ordinary_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state, 42u32, "{} declared postfix state drifted", case_id);
        let actual_return = fdb_kv_iterate_iterated_count_probe(&mut actual_ordinary_itr);
        assert_eq!(actual_ordinary_itr.iterated_cnt, expected_state, "{} postfix state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "u32-wrap";
        let mut actual_u32_wrap_itr = FdbKvIterator { iterated_cnt: 4294967295u32 };
        let expected_state = actual_u32_wrap_itr.iterated_cnt.wrapping_add(1u32);
        assert_eq!(expected_state, 0u32, "{} declared postfix state drifted", case_id);
        let actual_return = fdb_kv_iterate_iterated_count_probe(&mut actual_u32_wrap_itr);
        assert_eq!(actual_u32_wrap_itr.iterated_cnt, expected_state, "{} postfix state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
