use std::error::Error;
use std::io::{self, Write};

use c2r_translator::rust_source_witness::{
    build_rust_source_witness_from_reader, rust_source_witness_json_bytes,
};

fn main() -> Result<(), Box<dyn Error>> {
    let witness = build_rust_source_witness_from_reader(io::stdin().lock())?;
    let output = rust_source_witness_json_bytes(&witness)?;
    io::stdout().lock().write_all(&output)?;
    Ok(())
}
