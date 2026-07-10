use std::{
    error::Error,
    fs,
    path::{Path, PathBuf},
};

use c_to_rust_l2_slices::{
    add_i32_pair_ptr_arith, call_expression_chain, copy_i32_ptr_arith, external_direct_callee,
    fdb_blob_make, fdb_calc_crc32, fdb_kv_del, fdb_kv_set, fdb_kv_to_blob, fdb_tsl_to_blob,
    libuv_ip4_addr, signed_rshift_contract, sqlite_varint, store_add_one, sum_i32_buffer,
    sum_i32_ptr_arith, zlib_adler32, zstd_xxh32,
};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

include!("emit_reports/part_00.rs");
include!("emit_reports/part_01.rs");
include!("emit_reports/part_02.rs");
include!("emit_reports/part_03.rs");
include!("emit_reports/part_04.rs");
include!("emit_reports/part_05.rs");
include!("emit_reports/part_06.rs");
