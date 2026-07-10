// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_interior_projection_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-interior-projection.json";
    let _api = "fdb_kv_iterate_projection_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact safe owner-interior projection fixture replay.
    {
        let case_id = "already-zero";
        let mut actual_already_zero_itr = FdbKvIterator { curr_kv: Kv { addr: Address { start: 0u32 } } };
        let actual_return = fdb_kv_iterate_projection_probe(&mut actual_already_zero_itr);
        assert_eq!(actual_already_zero_itr.curr_kv.addr.start, 0u32, "{} projected state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "ordinary-address";
        let mut actual_ordinary_address_itr = FdbKvIterator { curr_kv: Kv { addr: Address { start: 8192u32 } } };
        let actual_return = fdb_kv_iterate_projection_probe(&mut actual_ordinary_address_itr);
        assert_eq!(actual_ordinary_address_itr.curr_kv.addr.start, 0u32, "{} projected state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "maximum-address";
        let mut actual_maximum_address_itr = FdbKvIterator { curr_kv: Kv { addr: Address { start: 4294967295u32 } } };
        let actual_return = fdb_kv_iterate_projection_probe(&mut actual_maximum_address_itr);
        assert_eq!(actual_maximum_address_itr.curr_kv.addr.start, 0u32, "{} projected state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
