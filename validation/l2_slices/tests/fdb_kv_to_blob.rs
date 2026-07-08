use c_to_rust_l2_slices::fdb_kv_to_blob::{
    fdb_kv_to_blob, FdbBlob, FdbBlobSaved, FdbKv, FdbKvAddr,
};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct FdbKvToBlobFixture {
    cases: Vec<FdbKvToBlobCase>,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobCase {
    id: String,
    kv: FdbKvFixture,
    initial_blob_saved: FdbBlobSavedFixture,
    expected_outputs: FdbKvToBlobExpected,
}

#[derive(Debug, Deserialize)]
struct FdbKvFixture {
    #[serde(rename = "addr.start")]
    addr_start: u32,
    #[serde(rename = "addr.value")]
    addr_value: u32,
    value_len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbBlobSavedFixture {
    meta_addr: u32,
    addr: u32,
    len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobExpected {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.saved.meta_addr")]
    blob_saved_meta_addr: u32,
    #[serde(rename = "blob.saved.addr")]
    blob_saved_addr: u32,
    #[serde(rename = "blob.saved.len")]
    blob_saved_len: usize,
}

#[test]
fn fdb_kv_to_blob_matches_real_flashdb_fixture() {
    let fixture: FdbKvToBlobFixture =
        serde_json::from_str(include_str!("../fixtures/real-fdb-kv-to-blob.json"))
            .expect("real-fdb-kv-to-blob fixture parses");

    for case in fixture.cases {
        let kv = FdbKv {
            addr: FdbKvAddr {
                start: case.kv.addr_start,
                value: case.kv.addr_value,
            },
            value_len: case.kv.value_len,
        };
        let mut blob = FdbBlob {
            saved: FdbBlobSaved {
                meta_addr: case.initial_blob_saved.meta_addr,
                addr: case.initial_blob_saved.addr,
                len: case.initial_blob_saved.len,
            },
        };
        let blob_addr = (&mut blob as *mut FdbBlob).cast::<core::ffi::c_void>();
        let returned = fdb_kv_to_blob(&kv, &mut blob);
        let returned_addr = (returned as *mut FdbBlob).cast::<core::ffi::c_void>();

        assert_eq!(
            returned_addr == blob_addr,
            case.expected_outputs.return_same_blob,
            "{} return identity",
            case.id
        );
        assert_eq!(
            returned.saved.meta_addr, case.expected_outputs.blob_saved_meta_addr,
            "{} blob.saved.meta_addr",
            case.id
        );
        assert_eq!(
            returned.saved.addr, case.expected_outputs.blob_saved_addr,
            "{} blob.saved.addr",
            case.id
        );
        assert_eq!(
            returned.saved.len, case.expected_outputs.blob_saved_len,
            "{} blob.saved.len",
            case.id
        );
    }
}
