use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct StoreAddOneReport {
    pub return_code: i32,
    pub status: &'static str,
    pub out0: i32,
    pub source_write: &'static str,
}

pub fn store_add_one(value: i32) -> StoreAddOneReport {
    let mut out0 = 0;
    let return_code = store_add_one_raw(value, &mut out0 as *mut i32);
    StoreAddOneReport {
        return_code,
        status: "ok",
        out0,
        source_write: "out[0]",
    }
}

fn store_add_one_raw(value: i32, out: *mut i32) -> i32 {
    unsafe {
        *out.add(0) = value + 1;
    }
    0
}
