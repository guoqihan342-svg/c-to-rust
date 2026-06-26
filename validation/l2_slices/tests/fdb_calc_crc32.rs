use c_to_rust_l2_slices::fdb_calc_crc32::fdb_calc_crc32;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct FdbCalcCrc32Fixture {
    cases: Vec<FdbCalcCrc32Case>,
}

#[derive(Debug, Deserialize)]
struct FdbCalcCrc32Case {
    id: String,
    crc: u32,
    buf: Vec<u8>,
    size: usize,
    return_code: u32,
}

#[test]
fn fdb_calc_crc32_matches_real_flashdb_c_oracle_fixture() {
    let fixture: FdbCalcCrc32Fixture =
        serde_json::from_str(include_str!("../fixtures/real-fdb-calc-crc32.json"))
            .expect("real-fdb-calc-crc32 fixture parses");

    for case in fixture.cases {
        assert_eq!(
            case.buf.len(),
            case.size,
            "{} fixture size must match byte buffer length",
            case.id
        );
        let actual = fdb_calc_crc32(case.crc, &case.buf);
        assert_eq!(actual, case.return_code, "{}", case.id);
    }
}
