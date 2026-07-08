use c_to_rust_l2_slices::enum_constant::add_status;
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct EnumConstantOracleReport {
    cases: Vec<EnumConstantOracleCase>,
}

#[derive(Debug, Deserialize)]
struct EnumConstantOracleCase {
    id: String,
    value: i32,
    return_value: i32,
    status: String,
}

#[test]
fn enum_constant_matches_c_oracle_with_safe_boundary() {
    let report: EnumConstantOracleReport =
        serde_json::from_str(include_str!("../fixtures/enum-constant-c-oracle.json"))
            .expect("enum_constant oracle fixture parses");

    for case in report.cases {
        let rust = add_status(case.value);

        assert_eq!(rust, case.return_value, "{}", case.id);
        assert_eq!(case.status, "ok", "{}", case.id);
    }
}
