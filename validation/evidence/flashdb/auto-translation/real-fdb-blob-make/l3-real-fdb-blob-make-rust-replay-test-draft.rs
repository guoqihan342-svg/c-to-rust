// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

#[test]
fn replay_real_fdb_blob_make_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/real-fdb-blob-make.json";
    let _api = "fdb_blob_make";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    struct FixtureCase {
        id: &'static str,
        value_buf: &'static [u8],
        value_buf_is_null: bool,
        buf_len: usize,
        initial_blob_size: usize,
    }

    let fixture_cases: &[FixtureCase] = &[
        FixtureCase { id: "null-empty", value_buf: &[], value_buf_is_null: true, buf_len: 0usize, initial_blob_size: 99usize },
        FixtureCase { id: "nominal-bytes", value_buf: &[16u8, 32u8, 48u8], value_buf_is_null: false, buf_len: 3usize, initial_blob_size: 0usize },
        FixtureCase { id: "shorter-length-than-buffer", value_buf: &[170u8, 187u8, 204u8, 221u8], value_buf_is_null: false, buf_len: 2usize, initial_blob_size: 7usize },
    ];
    assert_eq!(fixture_cases.len(), 3usize, "fixture case count drifted");
    for case in fixture_cases {
        if !case.value_buf_is_null {
            assert!(case.value_buf.len() >= case.buf_len, "{} fixture buffer shorter than declared length", case.id);
        }
        let value_ptr: *const core::ffi::c_void = if case.value_buf_is_null {
            core::ptr::null::<core::ffi::c_void>()
        } else {
            case.value_buf.as_ptr().cast::<core::ffi::c_void>()
        };
        let mut blob = FdbBlob { buf: core::ptr::null_mut(), size: case.initial_blob_size };
        let blob_ptr = &mut blob as *mut FdbBlob;
        let returned_ptr = {
            let returned = fdb_blob_make(&mut blob, value_ptr, case.buf_len);
            returned as *mut FdbBlob
        };
        assert_eq!(returned_ptr, blob_ptr, "{} return_same_blob drifted", case.id);
        assert_eq!(blob.buf, value_ptr as *mut core::ffi::c_void, "{} blob.buf drifted", case.id);
        assert_eq!(blob.size, case.buf_len, "{} blob.size drifted", case.id);
    }
}
