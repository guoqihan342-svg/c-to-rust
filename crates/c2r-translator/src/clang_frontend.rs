use std::{collections::BTreeMap, error::Error, fmt, path::PathBuf};

use serde::{Deserialize, Serialize};

use crate::{SliceSpec, SourceSpanRef};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClangParseSpec {
    pub source_root: PathBuf,
    pub source_file: PathBuf,
    pub function_name: String,
    pub include_paths: Vec<String>,
    pub defines: Vec<String>,
    pub compile_commands: Option<PathBuf>,
    pub source_file_hashes: BTreeMap<String, String>,
    pub function_source_span: Option<SourceSpanRef>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClangFrontendError {
    pub kind: String,
    pub message: String,
}

impl fmt::Display for ClangFrontendError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for ClangFrontendError {}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangDryRun {
    pub status: String,
    pub source_root: String,
    pub source_file: String,
    pub function_name: String,
    pub arguments: Vec<String>,
    pub compile_commands: Option<String>,
    pub diagnostics: Vec<String>,
}

impl ClangParseSpec {
    pub fn from_slice_spec(spec: &SliceSpec) -> Result<Self, ClangFrontendError> {
        let source_root = required_path(spec.source_root.as_deref(), "source_root")?;
        let source_file = required_path(spec.source_file.as_deref(), "source_file")?;
        let source_file_key = normalized_path(&source_file);
        if spec.function_name.trim().is_empty() {
            return Err(ClangFrontendError {
                kind: "missing_function_name".to_string(),
                message: "clang frontend dry-run requires function_name".to_string(),
            });
        }
        if !spec.source_file_hashes.iter().any(|(path, sha256)| {
            normalized_metadata_path(path) == source_file_key && !sha256.trim().is_empty()
        }) {
            return Err(ClangFrontendError {
                kind: "missing_source_file_hash".to_string(),
                message: "clang frontend dry-run requires source_file_hashes entry for source_file"
                    .to_string(),
            });
        }
        let function_source_span =
            spec.function_source_span
                .clone()
                .ok_or_else(|| ClangFrontendError {
                    kind: "missing_function_source_span".to_string(),
                    message: "clang frontend dry-run requires function_source_span".to_string(),
                })?;
        if normalized_metadata_path(&function_source_span.file) != source_file_key {
            return Err(ClangFrontendError {
                kind: "function_span_source_file_mismatch".to_string(),
                message: format!(
                    "function_source_span.file must match source_file: {} != {}",
                    function_source_span.file,
                    source_file.to_string_lossy()
                ),
            });
        }
        if function_source_span.sha256.trim().is_empty() {
            return Err(ClangFrontendError {
                kind: "missing_function_source_span_hash".to_string(),
                message: "clang frontend dry-run requires function_source_span.sha256".to_string(),
            });
        }

        Ok(Self {
            source_root,
            source_file,
            function_name: spec.function_name.clone(),
            include_paths: spec.build_profile.include_paths.clone(),
            defines: spec.build_profile.defines.clone(),
            compile_commands: spec.compile_commands.as_ref().map(PathBuf::from),
            source_file_hashes: spec.source_file_hashes.clone(),
            function_source_span: Some(function_source_span),
        })
    }

    pub fn dry_run(&self) -> ClangDryRun {
        let mut diagnostics =
            vec!["libclang execution is not enabled in this dry-run skeleton".to_string()];
        if self.compile_commands.is_some() {
            diagnostics.push(
                "compile_commands is present; dry-run arguments omit synthesized include/define flags"
                    .to_string(),
            );
        }

        ClangDryRun {
            status: "ready_without_libclang".to_string(),
            source_root: self.source_root.to_string_lossy().into_owned(),
            source_file: self.source_file.to_string_lossy().into_owned(),
            function_name: self.function_name.clone(),
            arguments: self.clang_arguments(),
            compile_commands: self
                .compile_commands
                .as_ref()
                .map(|path| path.to_string_lossy().into_owned()),
            diagnostics,
        }
    }

    pub fn clang_arguments(&self) -> Vec<String> {
        if self.compile_commands.is_some() {
            return Vec::new();
        }

        self.include_paths
            .iter()
            .map(|include_path| {
                format!(
                    "-I{}",
                    self.source_root
                        .join(include_path)
                        .to_string_lossy()
                        .replace('\\', "/")
                )
            })
            .chain(self.defines.iter().map(|define| format!("-D{define}")))
            .collect()
    }
}

fn normalized_path(path: &PathBuf) -> String {
    normalized_metadata_path(&path.to_string_lossy())
}

fn normalized_metadata_path(path: &str) -> String {
    path.trim().replace('\\', "/")
}

fn required_path(value: Option<&str>, field: &str) -> Result<PathBuf, ClangFrontendError> {
    let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Err(ClangFrontendError {
            kind: format!("missing_{field}"),
            message: format!("clang frontend dry-run requires {field}"),
        });
    };
    Ok(PathBuf::from(value))
}
