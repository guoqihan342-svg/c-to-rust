use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SumI32BufferReport {
    pub return_code: i32,
    pub status: &'static str,
    pub len: i32,
    pub sum: i32,
    pub source_reads: &'static str,
    pub source_write: &'static str,
}

pub fn sum_i32_buffer(values: &[i32]) -> SumI32BufferReport {
    let sum = values.iter().copied().sum();
    SumI32BufferReport {
        return_code: 0,
        status: "ok",
        len: values.len() as i32,
        sum,
        source_reads: "values[i] under i < len",
        source_write: "out[0]",
    }
}
