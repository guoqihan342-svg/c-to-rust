use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SignedRshiftContractReport {
    pub return_value: i32,
    pub status: &'static str,
    pub contract: &'static str,
}

pub fn signed_rshift_contract(value: i32, count: u32) -> SignedRshiftContractReport {
    SignedRshiftContractReport {
        return_value: value
            .checked_shr(count)
            .expect("signed right shift count must be in range"),
        status: "ok",
        contract: "implementation_defined_arithmetic_shift",
    }
}
