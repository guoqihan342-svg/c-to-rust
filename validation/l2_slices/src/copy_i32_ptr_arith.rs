use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CopyI32PtrArithReport {
    pub return_code: i32,
    pub status: &'static str,
    pub len: i32,
    pub values: Vec<i32>,
    pub out_values: Vec<i32>,
    pub source_reads: &'static str,
    pub canonical_reads: &'static str,
    pub source_writes: &'static str,
    pub canonical_writes: &'static str,
    pub write_count: usize,
}

pub fn copy_i32_ptr_arith(values: &[i32]) -> CopyI32PtrArithReport {
    let mut out_values = vec![0; values.len()];
    for (index, value) in values.iter().copied().enumerate() {
        out_values[index] = value;
    }
    CopyI32PtrArithReport {
        return_code: 0,
        status: "ok",
        len: values.len() as i32,
        values: values.to_vec(),
        out_values,
        source_reads: "*(values + i) under i < len",
        canonical_reads: "values[i]",
        source_writes: "*(out + i) under i < len",
        canonical_writes: "out[i]",
        write_count: values.len(),
    }
}
