// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_iterate_sector_start_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-iterate-sector-start.json";
    let _api = "fdb_kv_iterate_sector_start_probe";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    // Exact nested-state record-field plus scalar fixture replay.
    {
        let case_id = "first-sector-data";
        let actual_first_sector_data_sector = Sector { addr: 0u32 };
        let actual_first_sector_data_SECTOR_HDR_DATA_SIZE = 32u32;
        let mut actual_first_sector_data_kv = Kv { addr: Address { start: 4294967295u32 } };
        let expected_state = actual_first_sector_data_sector.addr.wrapping_add(actual_first_sector_data_SECTOR_HDR_DATA_SIZE);
        assert_eq!(expected_state, 32u32, "{} declared field-scalar state drifted", case_id);
        let actual_return = fdb_kv_iterate_sector_start_probe(actual_first_sector_data_sector, actual_first_sector_data_SECTOR_HDR_DATA_SIZE, &mut actual_first_sector_data_kv);
        assert_eq!(actual_first_sector_data_kv.addr.start, expected_state, "{} field-scalar state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "ordinary-sector-data";
        let actual_ordinary_sector_data_sector = Sector { addr: 4096u32 };
        let actual_ordinary_sector_data_SECTOR_HDR_DATA_SIZE = 64u32;
        let mut actual_ordinary_sector_data_kv = Kv { addr: Address { start: 7u32 } };
        let expected_state = actual_ordinary_sector_data_sector.addr.wrapping_add(actual_ordinary_sector_data_SECTOR_HDR_DATA_SIZE);
        assert_eq!(expected_state, 4160u32, "{} declared field-scalar state drifted", case_id);
        let actual_return = fdb_kv_iterate_sector_start_probe(actual_ordinary_sector_data_sector, actual_ordinary_sector_data_SECTOR_HDR_DATA_SIZE, &mut actual_ordinary_sector_data_kv);
        assert_eq!(actual_ordinary_sector_data_kv.addr.start, expected_state, "{} field-scalar state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
    {
        let case_id = "u32-wrap";
        let actual_u32_wrap_sector = Sector { addr: 4294967280u32 };
        let actual_u32_wrap_SECTOR_HDR_DATA_SIZE = 32u32;
        let mut actual_u32_wrap_kv = Kv { addr: Address { start: 123u32 } };
        let expected_state = actual_u32_wrap_sector.addr.wrapping_add(actual_u32_wrap_SECTOR_HDR_DATA_SIZE);
        assert_eq!(expected_state, 16u32, "{} declared field-scalar state drifted", case_id);
        let actual_return = fdb_kv_iterate_sector_start_probe(actual_u32_wrap_sector, actual_u32_wrap_SECTOR_HDR_DATA_SIZE, &mut actual_u32_wrap_kv);
        assert_eq!(actual_u32_wrap_kv.addr.start, expected_state, "{} field-scalar state drifted", case_id);
        assert_eq!(actual_return, true, "{} return drifted", case_id);
    }
}
