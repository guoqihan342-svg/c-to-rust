use std::{env, error::Error, fs, path::PathBuf};

use c2r_translator::{write_translation_artifacts, SliceSpec};

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args().skip(1);
    let mut slice_spec = None;
    let mut out_dir = None;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--slice-spec" => slice_spec = args.next().map(PathBuf::from),
            "--out-dir" => out_dir = args.next().map(PathBuf::from),
            "--help" | "-h" => {
                print_usage();
                return Ok(());
            }
            other => return Err(format!("unknown argument `{other}`").into()),
        }
    }

    let slice_spec = slice_spec.ok_or("missing --slice-spec <path>")?;
    let out_dir = out_dir.ok_or("missing --out-dir <path>")?;
    let spec: SliceSpec = serde_json::from_str(&fs::read_to_string(&slice_spec)?)?;
    let manifest = write_translation_artifacts(&spec, &out_dir)?;
    println!("{}", serde_json::to_string_pretty(&manifest)?);
    Ok(())
}

fn print_usage() {
    println!("Usage: c2r_translate --slice-spec <path> --out-dir <dir>");
}
