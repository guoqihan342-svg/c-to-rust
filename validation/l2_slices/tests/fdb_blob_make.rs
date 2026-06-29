use c_to_rust_l2_slices::fdb_blob_make::{fdb_blob_make, FdbBlob};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct FdbBlobMakeFixture {
    cases: Vec<FdbBlobMakeCase>,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeCase {
    id: String,
    buf_len: usize,
    initial_blob_size: usize,
    value_buf: Option<Vec<u8>>,
    expected_outputs: FdbBlobMakeExpected,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeExpected {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.size")]
    blob_size: usize,
}

#[test]
fn fdb_blob_make_matches_real_flashdb_fixture() {
    let fixture: FdbBlobMakeFixture =
        serde_json::from_str(include_str!("../fixtures/real-fdb-blob-make.json"))
            .expect("real-fdb-blob-make fixture parses");

    for case in fixture.cases {
        let value_buf = case.value_buf.unwrap_or_default();
        let value_ptr = if value_buf.is_empty() {
            core::ptr::null()
        } else {
            value_buf.as_ptr().cast()
        };
        let mut blob = FdbBlob {
            buf: core::ptr::null_mut(),
            size: case.initial_blob_size,
        };
        let blob_addr = (&mut blob as *mut FdbBlob).cast::<core::ffi::c_void>();
        let returned = fdb_blob_make(&mut blob, value_ptr, case.buf_len);
        let returned_addr = (returned as *mut FdbBlob).cast::<core::ffi::c_void>();

        assert_eq!(
            returned_addr == blob_addr,
            case.expected_outputs.return_same_blob,
            "{} return identity",
            case.id
        );
        assert_eq!(returned.buf, value_ptr.cast_mut(), "{} blob.buf", case.id);
        assert_eq!(returned.size, case.expected_outputs.blob_size, "{} blob.size", case.id);
    }
}
