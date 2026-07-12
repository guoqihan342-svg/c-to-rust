use std::fs;
use std::path::{Component, Path, PathBuf};

use serde::Deserialize;
use sha2::{Digest, Sha256};

use super::{ClangFrontendError, CompileDatabaseRef, ResolvedCompileCommand};

const MAX_COMPILE_DATABASE_BYTES: u64 = 16 * 1024 * 1024;

#[derive(Debug, Deserialize)]
struct CompileCommandEntry {
    directory: String,
    file: String,
    #[serde(default)]
    arguments: Option<Vec<String>>,
    #[serde(default)]
    command: Option<String>,
}

pub fn resolve_compile_database(
    reference: &CompileDatabaseRef,
    reference_root: &Path,
    source_file: &Path,
) -> Result<ResolvedCompileCommand, ClangFrontendError> {
    let expected_sha256 = reference.sha256().ok_or_else(|| {
        error(
            "unhashed_compile_database",
            "compile database replay requires a {path, sha256} reference",
        )
    })?;
    validate_sha256(expected_sha256)?;
    let database_path = resolve_reference_path(reference_root, reference.path())?;
    let bytes = read_bounded(&database_path)?;
    let observed_sha256 = format!("{:x}", Sha256::digest(&bytes));
    if observed_sha256 != expected_sha256 {
        return Err(error(
            "compile_database_hash_mismatch",
            format!(
                "compile database SHA-256 mismatch: expected {expected_sha256}, observed {observed_sha256}"
            ),
        ));
    }

    let entries: Vec<CompileCommandEntry> = serde_json::from_slice(&bytes).map_err(|cause| {
        error(
            "invalid_compile_database_json",
            format!("compile database is not a JSON array of command entries: {cause}"),
        )
    })?;
    let wanted = comparable_path(source_file, reference_root);
    let mut matches = Vec::new();
    for (index, entry) in entries.into_iter().enumerate() {
        let directory = resolve_working_directory(reference_root, &entry.directory, index)?;
        if comparable_path(Path::new(&entry.file), &directory) == wanted {
            matches.push((index, entry, directory));
        }
    }
    if matches.is_empty() {
        return Err(error(
            "compile_database_source_missing",
            format!(
                "compile database has no entry for {}",
                source_file.display()
            ),
        ));
    }
    if matches.len() != 1 {
        return Err(error(
            "compile_database_source_ambiguous",
            format!(
                "compile database has {} entries for {}",
                matches.len(),
                source_file.display()
            ),
        ));
    }

    let (index, entry, working_directory) = matches.pop().expect("one checked match");
    let raw_arguments = entry_arguments(&entry, index)?;
    let arguments = sanitize_arguments(raw_arguments, &entry.file, &working_directory)?;
    Ok(ResolvedCompileCommand {
        database_path,
        database_sha256: observed_sha256,
        working_directory,
        arguments,
    })
}

fn validate_sha256(value: &str) -> Result<(), ClangFrontendError> {
    if value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Ok(());
    }
    Err(error(
        "invalid_compile_database_reference",
        "compile database sha256 must be 64 lowercase hexadecimal characters",
    ))
}

fn resolve_reference_path(root: &Path, value: &str) -> Result<PathBuf, ClangFrontendError> {
    let path = Path::new(value);
    if value.trim().is_empty()
        || value.contains('\\')
        || path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(error(
            "invalid_compile_database_reference",
            "compile database path must be a non-empty relative path without dot, parent, or backslash components",
        ));
    }
    let root = fs::canonicalize(root).map_err(|cause| {
        error(
            "compile_database_read_failed",
            format!(
                "cannot resolve compile database reference root {}: {cause}",
                root.display()
            ),
        )
    })?;
    let resolved = fs::canonicalize(root.join(path)).map_err(|cause| {
        error(
            "compile_database_read_failed",
            format!(
                "cannot resolve compile database {}: {cause}",
                path.display()
            ),
        )
    })?;
    if !resolved.starts_with(&root) {
        return Err(error(
            "invalid_compile_database_reference",
            "compile database path resolves outside its reference root",
        ));
    }
    Ok(resolved)
}

fn read_bounded(path: &Path) -> Result<Vec<u8>, ClangFrontendError> {
    let metadata = fs::metadata(path).map_err(|cause| {
        error(
            "compile_database_read_failed",
            format!(
                "cannot inspect compile database {}: {cause}",
                path.display()
            ),
        )
    })?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_COMPILE_DATABASE_BYTES {
        return Err(error(
            "compile_database_size_invalid",
            format!("compile database must be a non-empty file no larger than {MAX_COMPILE_DATABASE_BYTES} bytes"),
        ));
    }
    fs::read(path).map_err(|cause| {
        error(
            "compile_database_read_failed",
            format!("cannot read compile database {}: {cause}", path.display()),
        )
    })
}

fn resolve_working_directory(
    reference_root: &Path,
    value: &str,
    index: usize,
) -> Result<PathBuf, ClangFrontendError> {
    if value.trim().is_empty() || value.contains('\0') {
        return Err(entry_error(index, "directory must be a non-empty path"));
    }
    let path = Path::new(value);
    Ok(if path.is_absolute() {
        path.to_path_buf()
    } else {
        reference_root.join(path)
    })
}

fn entry_arguments(
    entry: &CompileCommandEntry,
    index: usize,
) -> Result<Vec<String>, ClangFrontendError> {
    match (&entry.arguments, &entry.command) {
        (Some(_), Some(_)) | (None, None) => Err(entry_error(
            index,
            "exactly one of arguments or command is required",
        )),
        (Some(arguments), None) => {
            if arguments
                .iter()
                .any(|argument| argument.is_empty() || argument.contains('\0'))
            {
                return Err(entry_error(
                    index,
                    "arguments must be non-empty and must not contain NUL bytes",
                ));
            }
            Ok(arguments.clone())
        }
        (None, Some(command)) => tokenize_command(command).map_err(|message| {
            entry_error(index, format!("unsafe or malformed command: {message}"))
        }),
    }
}

fn tokenize_command(command: &str) -> Result<Vec<String>, String> {
    if command.contains(['\n', '\r', '\0']) {
        return Err("control characters are not allowed".to_string());
    }
    let mut arguments = Vec::new();
    let mut current = String::new();
    let mut quote = None;
    let mut escaped = false;
    let mut started = false;
    for character in command.chars() {
        if escaped {
            current.push(character);
            escaped = false;
            started = true;
            continue;
        }
        match quote {
            Some(active) if character == active => quote = None,
            Some('\'') => {
                current.push(character);
                started = true;
            }
            Some('"') if character == '\\' => escaped = true,
            Some('"') if matches!(character, '$' | '`') => {
                return Err("shell expansion is not allowed".to_string())
            }
            Some(_) => {
                current.push(character);
                started = true;
            }
            None if character == '\\' => escaped = true,
            None if matches!(character, '\'' | '"') => {
                quote = Some(character);
                started = true;
            }
            None if character.is_whitespace() => {
                if started {
                    arguments.push(std::mem::take(&mut current));
                    started = false;
                }
            }
            None if matches!(character, ';' | '|' | '&' | '<' | '>' | '$' | '`') => {
                return Err("shell operators and expansions are not allowed".to_string())
            }
            None => {
                current.push(character);
                started = true;
            }
        }
    }
    if escaped || quote.is_some() {
        return Err("unterminated escape or quote".to_string());
    }
    if started {
        arguments.push(current);
    }
    if arguments.is_empty() {
        return Err("command is empty".to_string());
    }
    Ok(arguments)
}

fn sanitize_arguments(
    mut arguments: Vec<String>,
    source_spelling: &str,
    working_directory: &Path,
) -> Result<Vec<String>, ClangFrontendError> {
    if arguments.is_empty() || arguments[0].trim().is_empty() {
        return Err(error(
            "invalid_compile_database_entry",
            "compiler argument is missing",
        ));
    }
    if arguments.iter().any(|argument| argument.starts_with('@')) {
        return Err(error(
            "compile_database_response_file_unsupported",
            "response-file arguments are not replayable without a separate hash binding",
        ));
    }
    arguments.remove(0);

    let source_key = comparable_path(Path::new(source_spelling), working_directory);
    let mut sanitized = Vec::new();
    let mut index = 0;
    while index < arguments.len() {
        let argument = &arguments[index];
        if is_no_value_action_or_dependency_flag(argument)
            || comparable_path(Path::new(argument), working_directory) == source_key
        {
            index += 1;
            continue;
        }
        if is_value_flag(argument) {
            if index + 1 >= arguments.len() {
                return Err(error(
                    "invalid_compile_database_entry",
                    format!("compile flag {argument} requires a value"),
                ));
            }
            index += 2;
            continue;
        }
        if is_joined_output_or_dependency_flag(argument) {
            index += 1;
            continue;
        }
        sanitized.push(argument.clone());
        index += 1;
    }
    Ok(sanitized)
}

fn is_no_value_action_or_dependency_flag(argument: &str) -> bool {
    matches!(
        argument,
        "-c" | "--compile"
            | "-S"
            | "-E"
            | "-fsyntax-only"
            | "-M"
            | "-MM"
            | "-MD"
            | "-MMD"
            | "-MP"
            | "-MG"
    )
}

fn is_value_flag(argument: &str) -> bool {
    matches!(
        argument,
        "-o" | "--output" | "-MF" | "-MT" | "-MQ" | "-MJ" | "--dependency-file"
    )
}

fn is_joined_output_or_dependency_flag(argument: &str) -> bool {
    (argument.starts_with("-o") && argument.len() > 2)
        || argument.starts_with("--output=")
        || ["-MF", "-MT", "-MQ", "-MJ"]
            .iter()
            .any(|prefix| argument.starts_with(prefix) && argument.len() > prefix.len())
        || argument.starts_with("--dependency-file=")
}

fn comparable_path(path: &Path, base: &Path) -> String {
    let resolved = if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    };
    let mut parts = Vec::new();
    for component in resolved.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                parts.pop();
            }
            other => parts.push(other.as_os_str().to_string_lossy().into_owned()),
        }
    }
    let normalized = parts.join("/").replace('\\', "/");
    if cfg!(windows) {
        normalized.to_ascii_lowercase()
    } else {
        normalized
    }
}

fn entry_error(index: usize, message: impl Into<String>) -> ClangFrontendError {
    error(
        "invalid_compile_database_entry",
        format!("compile database entry {index}: {}", message.into()),
    )
}

fn error(kind: &str, message: impl Into<String>) -> ClangFrontendError {
    ClangFrontendError {
        kind: kind.to_string(),
        message: message.into(),
    }
}
