use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct StoreAddOneReport {
    pub return_code: i32,
    pub status: &'static str,
    pub out0: i32,
    pub source_write: &'static str,
}

pub fn store_add_one(value: i32) -> StoreAddOneReport {
    StoreAddOneReport {
        return_code: 0,
        status: "ok",
        out0: value + 1,
        source_write: "out[0]",
    }
}
