use c_to_rust_l2_slices::fdb_tsl_to_blob::{
    fdb_tsl_to_blob, FdbBlob, FdbBlobSaved, FdbTsl, FdbTslAddr,
};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct FdbTslToBlobFixture {
    cases: Vec<FdbTslToBlobCase>,
}

#[derive(Debug, Deserialize)]
struct FdbTslToBlobCase {
    id: String,
    tsl: FdbTslFixture,
    initial_blob_saved: FdbBlobSavedFixture,
    expected_outputs: FdbTslToBlobExpected,
}

#[derive(Debug, Deserialize)]
struct FdbTslFixture {
    #[serde(rename = "addr.log")]
    addr_log: u32,
    #[serde(rename = "addr.index")]
    addr_index: u32,
    log_len: u32,
}

#[derive(Debug, Deserialize)]
struct FdbBlobSavedFixture {
    addr: u32,
    meta_addr: u32,
    len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbTslToBlobExpected {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.saved.addr")]
    blob_saved_addr: u32,
    #[serde(rename = "blob.saved.meta_addr")]
    blob_saved_meta_addr: u32,
    #[serde(rename = "blob.saved.len")]
    blob_saved_len: usize,
}

#[test]
fn fdb_tsl_to_blob_matches_real_flashdb_fixture() {
    let fixture: FdbTslToBlobFixture =
        serde_json::from_str(include_str!("../fixtures/real-fdb-tsl-to-blob.json"))
            .expect("real-fdb-tsl-to-blob fixture parses");

    assert_eq!(fixture.cases.len(), 3, "fixture case count");
    assert!(
        fixture.cases.iter().any(|case| {
            case.tsl.addr_log == u32::MAX
                && case.tsl.addr_index == u32::MAX
                && case.tsl.log_len == u32::MAX
        }),
        "fixture includes the u32::MAX conversion case"
    );

    for case in fixture.cases {
        let tsl = FdbTsl {
            addr: FdbTslAddr {
                index: case.tsl.addr_index,
                log: case.tsl.addr_log,
            },
            log_len: case.tsl.log_len,
        };
        let mut blob = FdbBlob {
            saved: FdbBlobSaved {
                meta_addr: case.initial_blob_saved.meta_addr,
                addr: case.initial_blob_saved.addr,
                len: case.initial_blob_saved.len,
            },
            ..FdbBlob::default()
        };
        let blob_addr = (&mut blob as *mut FdbBlob).cast::<core::ffi::c_void>();
        let returned = fdb_tsl_to_blob(&tsl, &mut blob);
        let returned_addr = (returned as *mut FdbBlob).cast::<core::ffi::c_void>();

        assert_eq!(
            returned_addr == blob_addr,
            case.expected_outputs.return_same_blob,
            "{} return identity",
            case.id
        );
        assert_eq!(
            returned.saved.addr, case.expected_outputs.blob_saved_addr,
            "{} blob.saved.addr",
            case.id
        );
        assert_eq!(
            returned.saved.meta_addr, case.expected_outputs.blob_saved_meta_addr,
            "{} blob.saved.meta_addr",
            case.id
        );
        assert_eq!(
            returned.saved.len, case.expected_outputs.blob_saved_len,
            "{} u32 log_len to usize blob.saved.len",
            case.id
        );
        assert_eq!(
            returned.saved.len,
            usize::try_from(case.tsl.log_len).expect("u32 log length fits usize"),
            "{} explicit u32 to usize conversion",
            case.id
        );
    }
}
