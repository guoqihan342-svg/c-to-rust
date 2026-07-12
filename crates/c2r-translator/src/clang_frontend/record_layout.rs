#[cfg(feature = "typed-ir")]
const MAX_RECORD_LAYOUT_DUMP_BYTES: usize = 16 * 1024 * 1024;

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug)]
struct RecordLayoutDump {
    arguments: Vec<String>,
    dump_sha256: String,
    diagnostics_sha256: String,
    compile_arguments_sha256: String,
    compile_database_sha256: String,
    target_abi: TargetAbiProfile,
    layouts: BTreeMap<String, ClangRecordLayout>,
    ambiguous_records: Vec<String>,
}

#[cfg(feature = "typed-ir")]
fn clang_record_layout_dump(
    clang_path: &Path,
    ast_arguments: &[String],
    compile_arguments_sha256: &str,
    compile_database_sha256: &str,
    target_abi: &TargetAbiProfile,
) -> Result<RecordLayoutDump, ClangFrontendError> {
    use sha2::{Digest, Sha256};

    let arguments = record_layout_dump_arguments(ast_arguments)?;
    let output = Command::new(clang_path)
        .args(&arguments)
        .output()
        .map_err(|error| ClangFrontendError {
            kind: "clang_record_layout_dump_unavailable".to_string(),
            message: format!("failed to execute clang record-layout dump: {error}"),
        })?;
    if !output.status.success() {
        return Err(ClangFrontendError {
            kind: "clang_record_layout_dump_failed".to_string(),
            message: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        });
    }
    let combined_len = output.stdout.len().saturating_add(output.stderr.len());
    if combined_len > MAX_RECORD_LAYOUT_DUMP_BYTES {
        return Err(ClangFrontendError {
            kind: "clang_record_layout_dump_too_large".to_string(),
            message: format!(
                "clang record-layout dump is {combined_len} bytes; limit is {MAX_RECORD_LAYOUT_DUMP_BYTES}"
            ),
        });
    }
    let dump_sha256 = format!("{:x}", Sha256::digest(&output.stdout));
    let diagnostics_sha256 = format!("{:x}", Sha256::digest(&output.stderr));
    let text = String::from_utf8_lossy(&output.stdout);
    let (layouts, ambiguous_records) = parse_record_layout_dump(&text)?;
    Ok(RecordLayoutDump {
        arguments,
        dump_sha256,
        diagnostics_sha256,
        compile_arguments_sha256: compile_arguments_sha256.to_string(),
        compile_database_sha256: compile_database_sha256.to_string(),
        target_abi: target_abi.clone(),
        layouts,
        ambiguous_records,
    })
}

#[cfg(feature = "typed-ir")]
fn record_layout_dump_arguments(
    ast_arguments: &[String],
) -> Result<Vec<String>, ClangFrontendError> {
    let mut arguments = Vec::with_capacity(ast_arguments.len());
    let mut index = 0;
    let mut removed_ast_dump = 0;
    while index < ast_arguments.len() {
        if ast_arguments[index] == "-Xclang"
            && ast_arguments.get(index + 1).map(String::as_str) == Some("-ast-dump=json")
        {
            removed_ast_dump += 1;
            index += 2;
            continue;
        }
        arguments.push(ast_arguments[index].clone());
        index += 1;
    }
    if removed_ast_dump != 1 {
        return Err(ClangFrontendError {
            kind: "invalid_clang_record_layout_arguments".to_string(),
            message: format!(
                "record-layout replay requires exactly one -Xclang -ast-dump=json pair; found {removed_ast_dump}"
            ),
        });
    }
    arguments.insert(0, "-fdump-record-layouts-complete".to_string());
    arguments.insert(0, "-Xclang".to_string());
    Ok(arguments)
}

#[cfg(feature = "typed-ir")]
fn shared_compile_arguments_sha256(
    ast_arguments: &[String],
) -> Result<String, ClangFrontendError> {
    use sha2::{Digest, Sha256};

    let mut shared = ast_arguments.to_vec();
    let index = shared
        .windows(2)
        .position(|pair| pair == ["-Xclang", "-ast-dump=json"])
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_clang_record_layout_arguments".to_string(),
            message: "shared compile arguments are missing AST frontend action".to_string(),
        })?;
    shared.drain(index..index + 2);
    let bytes = serde_json::to_vec(&shared).map_err(|error| ClangFrontendError {
        kind: "invalid_clang_record_layout_arguments".to_string(),
        message: format!("failed to canonicalize shared compile arguments: {error}"),
    })?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

#[cfg(feature = "typed-ir")]
fn parse_record_layout_dump(
    text: &str,
) -> Result<(BTreeMap<String, ClangRecordLayout>, Vec<String>), ClangFrontendError> {
    let mut layouts = BTreeMap::new();
    let mut ambiguous = std::collections::BTreeSet::new();
    let mut expect_header = false;
    let mut current: Option<String> = None;

    for line in text.lines() {
        if line.trim() == "*** Dumping AST Record Layout" {
            expect_header = true;
            current = None;
            continue;
        }
        if expect_header {
            let Some((_, candidate)) = line.split_once('|') else {
                continue;
            };
            expect_header = false;
            current = record_type_from_layout_header(candidate.trim());
            continue;
        }
        let Some(record_type) = current.as_ref() else {
            continue;
        };
        let Some((size_bytes, align_bytes)) = layout_size_and_alignment(line) else {
            continue;
        };
        let layout = ClangRecordLayout {
            record_type: record_type.clone(),
            size_bytes,
            align_bytes,
        };
        if layouts.insert(record_type.clone(), layout).is_some() {
            layouts.remove(record_type);
            ambiguous.insert(record_type.clone());
        }
        current = None;
    }
    if layouts.is_empty() && ambiguous.is_empty() {
        return Err(ClangFrontendError {
            kind: "invalid_clang_record_layout_dump".to_string(),
            message: "clang record-layout dump contains no named complete records".to_string(),
        });
    }
    for record in &ambiguous {
        layouts.remove(record);
    }
    Ok((layouts, ambiguous.into_iter().collect()))
}

#[cfg(feature = "typed-ir")]
fn record_type_from_layout_header(value: &str) -> Option<String> {
    let name = value.strip_prefix("struct ")?;
    let name = name.trim();
    if name.is_empty()
        || !name
            .bytes()
            .enumerate()
            .all(|(index, byte)| byte == b'_' || byte.is_ascii_alphanumeric() && (index > 0 || !byte.is_ascii_digit()))
    {
        return None;
    }
    Some(format!("struct {name}"))
}

#[cfg(feature = "typed-ir")]
fn layout_size_and_alignment(line: &str) -> Option<(u64, u64)> {
    let summary = line.split_once("[sizeof=")?.1;
    let (size, rest) = summary.split_once(", align=")?;
    let align = rest.split_once(']')?.0;
    let size = size.parse::<u64>().ok()?;
    let align = align.parse::<u64>().ok()?;
    (size > 0 && align > 0).then_some((size, align))
}

#[cfg(feature = "typed-ir")]
fn record_layout_evidence(
    dump: Result<RecordLayoutDump, ClangFrontendError>,
    used_layouts: Vec<ClangRecordLayoutBinding>,
) -> ClangRecordLayoutEvidence {
    match dump {
        Ok(dump) => ClangRecordLayoutEvidence {
            status: "captured".to_string(),
            dump_sha256: Some(dump.dump_sha256),
            diagnostics_sha256: Some(dump.diagnostics_sha256),
            compile_arguments_sha256: Some(dump.compile_arguments_sha256),
            compile_database_sha256: Some(dump.compile_database_sha256),
            target_abi: Some(dump.target_abi),
            arguments: dump.arguments,
            used_layouts,
            ambiguous_records: dump.ambiguous_records,
            error: None,
        },
        Err(error) => ClangRecordLayoutEvidence {
            status: "unavailable".to_string(),
            dump_sha256: None,
            diagnostics_sha256: None,
            compile_arguments_sha256: None,
            compile_database_sha256: None,
            target_abi: None,
            arguments: Vec::new(),
            used_layouts: Vec::new(),
            ambiguous_records: Vec::new(),
            error: Some(format!("{}: {}", error.kind, error.message)),
        },
    }
}
