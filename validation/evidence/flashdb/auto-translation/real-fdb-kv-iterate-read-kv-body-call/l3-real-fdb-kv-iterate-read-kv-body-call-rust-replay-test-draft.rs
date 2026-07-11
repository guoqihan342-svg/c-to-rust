// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_read_kv_body_call_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-read-kv-body-call.json";
    let _api = "fdb_kv_iterate_read_kv_body_call_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Finite fixture sequence; real external callee semantics are not verified.
    {
        let case_id = "failed-address-first";
        __c2r_scripted_external_set_sequence(&[4294967295u32]);
        __c2r_scripted_external_reset_calls();
        let mut actual_failed_address_first_db = Database { generation: 17u32 };
        let actual_failed_address_first_sector_seed = Sector { offset: 29u32 };
        let mut actual_failed_address_first_itr = Owner { current: Kv { addr: Address { start: 0u32 } } };
        let actual_return = fdb_kv_iterate_read_kv_body_call_probe(&mut actual_failed_address_first_db, actual_failed_address_first_sector_seed, &mut actual_failed_address_first_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(actual_failed_address_first_itr.current.addr.start, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 1usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), vec![[17u32, 29u32, 0u32]], "{} external call arguments drifted", case_id);
        assert_eq!(__c2r_scripted_body_call_count(), 1usize, "{} body call count drifted", case_id);
        assert_eq!(__c2r_scripted_body_call_args(), vec![[17u32, 0u32]], "{} body call arguments drifted", case_id);
        assert_eq!(__c2r_scripted_call_order(), vec![1u32, 2u32], "{} body/tail call order drifted", case_id);
    }
    {
        let case_id = "one-kv-then-failed";
        __c2r_scripted_external_set_sequence(&[4096u32, 4294967295u32]);
        __c2r_scripted_external_reset_calls();
        let mut actual_one_kv_then_failed_db = Database { generation: 3u32 };
        let actual_one_kv_then_failed_sector_seed = Sector { offset: 5u32 };
        let mut actual_one_kv_then_failed_itr = Owner { current: Kv { addr: Address { start: 99u32 } } };
        let actual_return = fdb_kv_iterate_read_kv_body_call_probe(&mut actual_one_kv_then_failed_db, actual_one_kv_then_failed_sector_seed, &mut actual_one_kv_then_failed_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(actual_one_kv_then_failed_itr.current.addr.start, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 2usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), vec![[3u32, 5u32, 99u32], [3u32, 5u32, 4096u32]], "{} external call arguments drifted", case_id);
        assert_eq!(__c2r_scripted_body_call_count(), 2usize, "{} body call count drifted", case_id);
        assert_eq!(__c2r_scripted_body_call_args(), vec![[3u32, 99u32], [3u32, 4096u32]], "{} body call arguments drifted", case_id);
        assert_eq!(__c2r_scripted_call_order(), vec![1u32, 2u32, 1u32, 2u32], "{} body/tail call order drifted", case_id);
    }
    {
        let case_id = "two-kvs-then-failed";
        __c2r_scripted_external_set_sequence(&[12288u32, 16384u32, 4294967295u32]);
        __c2r_scripted_external_reset_calls();
        let mut actual_two_kvs_then_failed_db = Database { generation: 305419896u32 };
        let actual_two_kvs_then_failed_sector_seed = Sector { offset: 2271560481u32 };
        let mut actual_two_kvs_then_failed_itr = Owner { current: Kv { addr: Address { start: 17u32 } } };
        let actual_return = fdb_kv_iterate_read_kv_body_call_probe(&mut actual_two_kvs_then_failed_db, actual_two_kvs_then_failed_sector_seed, &mut actual_two_kvs_then_failed_itr);
        assert_eq!(actual_return, false, "{} return drifted", case_id);
        assert_eq!(actual_two_kvs_then_failed_itr.current.addr.start, 4294967295u32, "{} state drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_count(), 3usize, "{} external call count drifted", case_id);
        assert_eq!(__c2r_scripted_external_call_args(), vec![[305419896u32, 2271560481u32, 17u32], [305419896u32, 2271560481u32, 12288u32], [305419896u32, 2271560481u32, 16384u32]], "{} external call arguments drifted", case_id);
        assert_eq!(__c2r_scripted_body_call_count(), 3usize, "{} body call count drifted", case_id);
        assert_eq!(__c2r_scripted_body_call_args(), vec![[305419896u32, 17u32], [305419896u32, 12288u32], [305419896u32, 16384u32]], "{} body call arguments drifted", case_id);
        assert_eq!(__c2r_scripted_call_order(), vec![1u32, 2u32, 1u32, 2u32, 1u32, 2u32], "{} body/tail call order drifted", case_id);
    }
}
