use c_to_rust_l2_slices::implicit_integer_noop_cast::identity_noop;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct ImplicitIntegerNoopCastOracleReport {
    cases: Vec<ImplicitIntegerNoopCastOracleCase>,
}

#[derive(Debug, Deserialize)]
struct ImplicitIntegerNoopCastOracleCase {
    id: String,
    value: i32,
    return_value: i32,
    status: String,
}

#[test]
fn implicit_integer_noop_cast_matches_c_oracle_with_identity_boundary() {
    let report: ImplicitIntegerNoopCastOracleReport = serde_json::from_str(include_str!(
        "../fixtures/implicit-integer-noop-cast-c-oracle.json"
    ))
    .expect("implicit_integer_noop_cast oracle fixture parses");

    for case in report.cases {
        let rust = identity_noop(case.value);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}
