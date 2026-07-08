// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_kv_to_blob_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-kv-to-blob.json";
    let _api = "fdb_kv_to_blob";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        kv_addr_start: u32,
        kv_addr_value: u32,
        kv_value_len: usize,
        initial_blob_saved_meta_addr: u32,
        initial_blob_saved_addr: u32,
        initial_blob_saved_len: usize,
        blob_saved_meta_addr: u32,
        blob_saved_addr: u32,
        blob_saved_len: usize,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "zero-addresses-empty-value", kv_addr_start: 0u32, kv_addr_value: 0u32, kv_value_len: 0usize, initial_blob_saved_meta_addr: 99u32, initial_blob_saved_addr: 88u32, initial_blob_saved_len: 77usize, blob_saved_meta_addr: 0u32, blob_saved_addr: 0u32, blob_saved_len: 0usize },
        FixtureCase { id: "nominal-kv-value", kv_addr_start: 4096u32, kv_addr_value: 4352u32, kv_value_len: 128usize, initial_blob_saved_meta_addr: 1u32, initial_blob_saved_addr: 2u32, initial_blob_saved_len: 3usize, blob_saved_meta_addr: 4096u32, blob_saved_addr: 4352u32, blob_saved_len: 128usize },
        FixtureCase { id: "max-u32-addresses", kv_addr_start: 4294967280u32, kv_addr_value: 4294967295u32, kv_value_len: 65535usize, initial_blob_saved_meta_addr: 10u32, initial_blob_saved_addr: 20u32, initial_blob_saved_len: 30usize, blob_saved_meta_addr: 4294967280u32, blob_saved_addr: 4294967295u32, blob_saved_len: 65535usize },
    ];
    assert_eq!(fixture_cases.len(), 3usize, "fixture case count drifted");
    for case in fixture_cases {
        let kv = FdbKv {
            addr: FdbKvAddr { start: case.kv_addr_start, value: case.kv_addr_value },
            value_len: case.kv_value_len,
        };
        let mut blob = FdbBlob {
            buf: core::ptr::null_mut(),
            size: 0usize,
            saved: FdbBlobSaved {
                meta_addr: case.initial_blob_saved_meta_addr,
                addr: case.initial_blob_saved_addr,
                len: case.initial_blob_saved_len,
            },
        };
        let blob_ptr = &mut blob as *mut FdbBlob;
        let returned_ptr = {
            let returned = fdb_kv_to_blob(&kv, &mut blob);
            returned as *mut FdbBlob
        };
        assert_eq!(returned_ptr, blob_ptr, "{} return_same_blob drifted", case.id);
        assert_eq!(blob.saved.meta_addr, case.blob_saved_meta_addr, "{} blob.saved.meta_addr drifted", case.id);
        assert_eq!(blob.saved.addr, case.blob_saved_addr, "{} blob.saved.addr drifted", case.id);
        assert_eq!(blob.saved.len, case.blob_saved_len, "{} blob.saved.len drifted", case.id);
    }
}
