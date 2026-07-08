fn write_json(path: &Path, value: &Value) -> Result<(), Box<dyn Error>> {
    fs::write(path, serde_json::to_string_pretty(value)? + "\n")?;
    Ok(())
}

fn sha256_hex(path: &Path) -> Result<String, Box<dyn Error>> {
    let bytes = lf_stable_file_bytes(path)?;
    let mut digest = Sha256::new();
    digest.update(bytes);
    Ok(format!("{:x}", digest.finalize()))
}

fn lf_stable_file_bytes(path: &Path) -> Result<Vec<u8>, Box<dyn Error>> {
    let bytes = fs::read(path)?;
    if !should_normalize_lf_for_hash(path) {
        return Ok(bytes);
    }
    let mut normalized = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'\r' {
            normalized.push(b'\n');
            if bytes.get(index + 1) == Some(&b'\n') {
                index += 2;
            } else {
                index += 1;
            }
        } else {
            normalized.push(bytes[index]);
            index += 1;
        }
    }
    Ok(normalized)
}

fn should_normalize_lf_for_hash(path: &Path) -> bool {
    let suffix_matches = path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| {
            matches!(
                ext.to_ascii_lowercase().as_str(),
                "c" | "h"
                    | "json"
                    | "jsonl"
                    | "lock"
                    | "md"
                    | "conf"
                    | "rs"
                    | "sh"
                    | "toml"
                    | "txt"
                    | "yaml"
                    | "yml"
            )
        })
        .unwrap_or(false);
    let name_matches = path
        .file_name()
        .and_then(|name| name.to_str())
        .map(|name| matches!(name, ".npmrc" | "sources.list"))
        .unwrap_or(false);
    suffix_matches || name_matches
}

fn compare_field(
    first_mismatch: &mut Option<Value>,
    case_id: &str,
    field: &str,
    c: Value,
    rust: Value,
) {
    if first_mismatch.is_none() && c != rust {
        *first_mismatch = Some(json!({
            "case_id": case_id,
            "field": field,
            "c_value": c,
            "rust_value": rust
        }));
    }
}

fn status_from_mismatch(first_mismatch: &Option<Value>) -> &'static str {
    if first_mismatch.is_none() {
        "passed"
    } else {
        "failed"
    }
}

fn hex_to_bytes(hex: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    if !hex.len().is_multiple_of(2) {
        return Err("hex length must be even".into());
    }
    (0..hex.len())
        .step_by(2)
        .map(|idx| Ok(u8::from_str_radix(&hex[idx..idx + 2], 16)?))
        .collect()
}

fn bytes_to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn scan_rust_files(
    dir: &Path,
    on_line: &mut dyn FnMut(&Path, usize, &str),
) -> Result<(), Box<dyn Error>> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            scan_rust_files(&path, on_line)?;
        } else if path.extension().and_then(|ext| ext.to_str()) == Some("rs") {
            let text = fs::read_to_string(&path)?;
            for (index, line) in text.lines().enumerate() {
                let code = strip_strings_and_line_comments(line);
                on_line(&path, index + 1, &code);
            }
        }
    }
    Ok(())
}

fn strip_strings_and_line_comments(line: &str) -> String {
    let mut out = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();
    let mut in_string = false;
    let mut in_char = false;
    let mut escaped = false;

    while let Some(ch) = chars.next() {
        if !in_string && !in_char && ch == '/' && chars.peek() == Some(&'/') {
            break;
        }

        if in_string {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_string = false;
            }
            out.push(' ');
            continue;
        }

        if in_char {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '\'' {
                in_char = false;
            }
            out.push(' ');
            continue;
        }

        if ch == '"' {
            in_string = true;
            out.push(' ');
        } else if ch == '\'' {
            in_char = true;
            out.push(' ');
        } else {
            out.push(ch);
        }
    }

    out
}

fn relative_path(path: &Path) -> String {
    let crate_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = crate_dir
        .parent()
        .and_then(Path::parent)
        .unwrap_or(crate_dir.as_path());
    path.strip_prefix(repo_root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}
