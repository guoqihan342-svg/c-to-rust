use c_to_rust_l2_slices::fdb_is_str::fdb_is_str;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct FdbIsStrFixture {
    cases: Vec<FdbIsStrCase>,
}

#[derive(Debug, Deserialize)]
struct FdbIsStrCase {
    id: String,
    value_hex: String,
    len: usize,
    expected_outputs: FdbIsStrExpected,
}

#[derive(Debug, Deserialize)]
struct FdbIsStrExpected {
    return_value: bool,
}

#[test]
fn fdb_is_str_matches_real_flashdb_fixture() {
    let fixture: FdbIsStrFixture =
        serde_json::from_str(include_str!("../fixtures/real-fdb-is-str.json"))
            .expect("real-fdb-is-str fixture parses");

    assert_eq!(fixture.cases.len(), 8, "fixture case count");
    let expected_ids = [
        "empty",
        "all-printable",
        "printable-boundaries",
        "below-printable-range",
        "upper-exclusive-boundary",
        "u8-max",
        "internal-nul",
        "prefix-length",
    ];
    assert_eq!(
        fixture
            .cases
            .iter()
            .map(|case| case.id.as_str())
            .collect::<Vec<_>>(),
        expected_ids,
        "fixture preserves the required eight-case contract"
    );

    for case in fixture.cases {
        let value = decode_hex(&case.value_hex);
        assert!(
            case.len <= value.len(),
            "{} declares a readable prefix",
            case.id
        );
        assert_eq!(
            fdb_is_str(&value, case.len),
            case.expected_outputs.return_value,
            "{} return_value",
            case.id
        );
    }
}

#[test]
#[should_panic(expected = "fdb_is_str requires a readable prefix of len bytes")]
fn fdb_is_str_rejects_an_out_of_bounds_contract() {
    let _ = fdb_is_str(b"A", 2);
}

fn decode_hex(hex: &str) -> Vec<u8> {
    assert!(hex.len().is_multiple_of(2), "hex input has full bytes");
    (0..hex.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(&hex[index..index + 2], 16).expect("fixture hex byte"))
        .collect()
}
