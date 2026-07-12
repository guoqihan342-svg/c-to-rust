#[derive(Debug, Deserialize)]
struct SqliteVarintCase {
    id: String,
    value: u64,
    encoded_hex: String,
    bytes_used: usize,
    decoded_value: u64,
    decoded_bytes: usize,
}

#[derive(Debug, Deserialize)]
struct ChecksumCase {
    id: String,
    input_hex: String,
    seed: Option<u32>,
    value: u32,
}

#[derive(Debug, Deserialize)]
struct LibuvIp4OracleReport {
    cases: Vec<LibuvIp4OracleCase>,
}

#[derive(Debug, Deserialize)]
struct LibuvIp4OracleCase {
    id: String,
    ip: String,
    port: i32,
    coverage_kind: String,
    return_code: i32,
    status: String,
    family: u16,
    port_host: u16,
    port_bytes_hex: String,
    addr_bytes_hex: String,
}

#[derive(Debug, Deserialize)]
struct StoreAddOneOracleReport {
    cases: Vec<StoreAddOneOracleCase>,
}

#[derive(Debug, Deserialize)]
struct StoreAddOneOracleCase {
    id: String,
    coverage_kind: String,
    value: i32,
    return_code: i32,
    status: String,
    out0: i32,
}

#[derive(Debug, Deserialize)]
struct SumI32BufferOracleReport {
    cases: Vec<SumI32BufferOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SumI32BufferOracleCase {
    id: String,
    coverage_kind: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    sum: i32,
    source_reads: String,
    source_write: String,
}

#[derive(Debug, Deserialize)]
struct CallExpressionChainOracleReport {
    cases: Vec<CallExpressionChainOracleCase>,
}

#[derive(Debug, Deserialize)]
struct CallExpressionChainOracleCase {
    id: String,
    coverage_kind: String,
    input_value: i32,
    return_value: i32,
    status: String,
    call_expression_count: usize,
    call_expression_contexts: Vec<String>,
    source_calls: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SignedRshiftContractOracleReport {
    cases: Vec<SignedRshiftContractOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SignedRshiftContractOracleCase {
    id: String,
    coverage_kind: String,
    value: i32,
    count: u32,
    return_value: i32,
    status: String,
    contract: String,
}

#[derive(Debug, Deserialize)]
struct ExternalDirectCalleeOracleReport {
    cases: Vec<ExternalDirectCalleeOracleCase>,
}

#[derive(Debug, Deserialize)]
struct ExternalDirectCalleeOracleCase {
    id: String,
    coverage_kind: String,
    input_value: i32,
    return_value: i32,
    status: String,
    external_callee_call_count: usize,
    external_callee_contexts: Vec<String>,
    external_callee_bindings: Vec<String>,
    source_calls: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SumI32PtrArithOracleReport {
    cases: Vec<SumI32PtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct SumI32PtrArithOracleCase {
    id: String,
    coverage_kind: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    sum: i32,
    source_reads: String,
    canonical_reads: String,
    source_write: String,
}

#[derive(Debug, Deserialize)]
struct CopyI32PtrArithOracleReport {
    cases: Vec<CopyI32PtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct CopyI32PtrArithOracleCase {
    id: String,
    coverage_kind: String,
    values: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    out_values: Vec<i32>,
    source_reads: String,
    canonical_reads: String,
    source_writes: String,
    canonical_writes: String,
    write_count: usize,
}

#[derive(Debug, Deserialize)]
struct AddI32PairPtrArithOracleReport {
    cases: Vec<AddI32PairPtrArithOracleCase>,
}

#[derive(Debug, Deserialize)]
struct AddI32PairPtrArithOracleCase {
    id: String,
    coverage_kind: String,
    lhs: Vec<i32>,
    rhs: Vec<i32>,
    len: i32,
    return_code: i32,
    status: String,
    out_values: Vec<i32>,
    source_reads: String,
    canonical_reads: String,
    source_writes: String,
    canonical_writes: String,
    write_count: usize,
    safe_noalias_precondition: bool,
    alias_case: String,
    alias_matrix: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct FdbCalcCrc32OracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbCalcCrc32OracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbCalcCrc32OracleCase {
    id: String,
    coverage_kind: String,
    crc: u32,
    buf: Vec<u8>,
    size: usize,
    return_code: u32,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbBlobMakeOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeOracleCase {
    id: String,
    coverage_kind: String,
    buf_len: usize,
    initial_blob_size: usize,
    value_buf: Option<Vec<u8>>,
    expected_outputs: FdbBlobMakeExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbBlobMakeExpectedOutputs {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.buf")]
    blob_buf: String,
    #[serde(rename = "blob.size")]
    blob_size: usize,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbKvToBlobOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobOracleCase {
    id: String,
    coverage_kind: String,
    kv: FdbKvToBlobKvInput,
    initial_blob_saved: FdbKvToBlobSavedInput,
    expected_outputs: FdbKvToBlobExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobKvInput {
    #[serde(rename = "addr.start")]
    addr_start: u32,
    #[serde(rename = "addr.value")]
    addr_value: u32,
    value_len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobSavedInput {
    meta_addr: u32,
    addr: u32,
    len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbKvToBlobExpectedOutputs {
    #[serde(rename = "return_same_blob")]
    return_same_blob: bool,
    #[serde(rename = "blob.saved.meta_addr")]
    blob_saved_meta_addr: u32,
    #[serde(rename = "blob.saved.addr")]
    blob_saved_addr: u32,
    #[serde(rename = "blob.saved.len")]
    blob_saved_len: usize,
}

#[derive(Debug, Deserialize)]
struct FdbKvDelOracleReport {
    level: String,
    target_id: String,
    slice_id: String,
    source_commit: String,
    source_boundary: Value,
    compared_fields: Vec<String>,
    case_count: usize,
    cases: Vec<FdbKvDelOracleCase>,
}

#[derive(Debug, Deserialize)]
struct FdbKvDelOracleCase {
    id: String,
    coverage_kind: String,
    db_name: String,
    db_state: String,
    key: String,
    return_code: i32,
    expected_outputs: FdbKvDelExpectedOutputs,
    status: String,
}

#[derive(Debug, Deserialize)]
struct FdbKvDelExpectedOutputs {
    return_code: i32,
}
