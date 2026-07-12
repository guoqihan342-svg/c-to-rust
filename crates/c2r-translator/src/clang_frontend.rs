//! Clang AST frontend: parse real `clang -ast-dump=json` output and lower to typed IR.
//!
//! # Architecture
//!
//! The clang frontend operates in three stages:
//!
//! 1. **AST dump parse**: invokes `clang -Xclang -ast-dump=json -fsyntax-only` on a real
//!    C translation unit, producing JSON that describes every AST node.
//!
//! 2. **Skeleton lowering**: the JSON is lowered into a compact `Clang*Skeleton` tree.
//!    This is a narrow, deliberately conservative mapping. Only AST nodes that the current
//!    translator understands are accepted; everything else returns an `Unsupported` skeleton
//!    with a specific fail-closed reason (e.g., "WhileStmt without condition is outside
//!    the current clang lowering skeleton").
//!
//! 3. **Typed IR conversion**: skeleton nodes are converted into `typed_ir::Ir*` data
//!    structures, which feed into the generic Rust emitter or evidence recording.
//!
//! # Key Design Principles
//!
//! - **Fail-closed**: any unsupported AST node or type produces a structured error, never
//!   a silent fallback. Errors carry `kind` (e.g., `unsupported_clang_stmt`) and a message.
//! - **AST-driven, not string-driven**: the legacy string matcher for crc32 has been deleted.
//!   All forward Rust generation for FlashDB crc32 now goes through this clang frontend.
//! - **The frontend does not decide Rust semantics**: it lowers C AST into typed IR.
//!   The typed IR emitter decides what Rust to emit. The validation pipeline decides
//!   whether the result is correct.
//! - **Type mapping is conservative**: fixed-width integer typedef aliases (int8_t through
//!   uint64_t) and `signed char` map directly to typed IR integer types. Target-dependent
//!   spellings fail closed unless an explicit target ABI profile provides the required evidence;
//!   the current profile-bound path lowers `char`, `short`, `long`,
//!   `long long`, and `size_t` only when the target profile provides the
//!   required width and signedness evidence. A narrow enum path rewrites only complete
//!   `enum T` declarations whose constants are all explicit non-negative `int` literals
//!   fitting `i32`; it is not a general C enum ABI model.
//!
//! # Coverage
//!
//! See `docs/c2rust-migration-agent/COVERAGE.md` for the full supported/unsupported
//! C construct inventory. The `expr_skeleton_from_ast` and `stmt_skeleton_from_ast`
//! functions are the primary entry points for expression and statement lowering.

#[cfg(feature = "typed-ir")]
use std::process::Command;
use std::{
    collections::BTreeMap,
    env,
    error::Error,
    fmt,
    path::{Path, PathBuf},
};

use serde::{Deserialize, Serialize};
#[cfg(feature = "typed-ir")]
use serde_json::Value;

pub use crate::model::CompileDatabaseRef;
#[cfg(feature = "typed-ir")]
use crate::typed_ir::{
    IrBinOp, IrExpr, IrFunction, IrGlobal, IrGlobalInit, IrParam, IrStmt, IrType, IrTypeKind,
};
use crate::{SliceSpec, SourceSpanRef, TargetAbiProfile};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClangParseSpec {
    pub source_root: PathBuf,
    pub source_file: PathBuf,
    pub function_name: String,
    pub include_paths: Vec<String>,
    pub defines: Vec<String>,
    pub target_abi: Option<TargetAbiProfile>,
    pub compile_commands: Option<CompileDatabaseRef>,
    pub source_file_hashes: BTreeMap<String, String>,
    pub function_source_span: Option<SourceSpanRef>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolvedCompileCommand {
    pub database_path: PathBuf,
    pub database_sha256: String,
    pub working_directory: PathBuf,
    pub arguments: Vec<String>,
}

impl ClangParseSpec {
    pub fn resolved_compile_command(
        &self,
    ) -> Result<Option<ResolvedCompileCommand>, ClangFrontendError> {
        let Some(reference) = &self.compile_commands else {
            return Ok(None);
        };
        let source_file = if self.source_file.is_absolute() {
            self.source_file.clone()
        } else {
            self.source_root.join(&self.source_file)
        };
        resolve_compile_database(reference, &self.source_root, &source_file).map(Some)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
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
pub struct ClangEnvironment {
    pub status: String,
    pub source: Option<String>,
    pub observed_libclang_path: Option<String>,
    pub role: String,
    pub diagnostics: Vec<String>,
}

impl ClangEnvironment {
    pub fn detect() -> Self {
        let environment = env::vars().collect();
        Self::detect_from_env(&environment)
    }

    pub fn detect_from_env(environment: &BTreeMap<String, String>) -> Self {
        if let Some(libclang_path) = environment
            .get("LIBCLANG_PATH")
            .map(|value| value.trim())
            .filter(|value| !value.is_empty())
        {
            return Self {
                status: "ignored_for_ast_dump".to_string(),
                source: Some("LIBCLANG_PATH".to_string()),
                observed_libclang_path: Some(libclang_path.to_string()),
                role: "diagnostic_only".to_string(),
                diagnostics: vec![
                    "LIBCLANG_PATH is configured but ignored for clang AST dump lowering; active lowering uses CLANG_PATH"
                        .to_string(),
                ],
            };
        }

        Self {
            status: "not_configured".to_string(),
            source: None,
            observed_libclang_path: None,
            role: "diagnostic_only".to_string(),
            diagnostics: vec![
                "LIBCLANG_PATH is not set and is ignored for clang AST dump lowering".to_string(),
            ],
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangActiveFrontend {
    pub kind: String,
    pub command: String,
    pub required_env: Vec<String>,
    pub uses_libclang: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangClaimBoundary {
    pub role: String,
    pub affects_manifest_status: bool,
    pub affects_semantic_pass: bool,
    pub authoritative_evidence: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangDryRun {
    pub status: String,
    pub active_frontend: ClangActiveFrontend,
    pub claim_boundary: ClangClaimBoundary,
    pub source_root: String,
    pub source_file: String,
    pub function_name: String,
    pub arguments: Vec<String>,
    pub compile_commands: Option<String>,
    pub environment: ClangEnvironment,
    pub diagnostics: Vec<String>,
}

/// Resolve the clang binary path for AST dump JSON lowering.
///
/// Resolution order:
/// 1. `CLANG_PATH` environment variable (an existing path or a bare command
///    name resolved by the process `PATH`)
/// 2. Vendored local paths under the workspace / project root
///    - `tools/llvm/bin/clang` (or `.exe` on Windows)
///    - `tools/llvm/bin/clang-18` (or `.exe` on Windows)
///    - `tools/clang/bin/clang` (or `.exe` on Windows)
///
/// The searched paths are relative to the current working directory, which is
/// expected to be the repository root when invoked by `auto_migrate.py`.
///
/// Returns `(path, source_label)` where `source_label` describes which
/// resolution strategy succeeded.
pub fn resolve_clang_path(environment: &BTreeMap<String, String>) -> Option<(PathBuf, String)> {
    // 1. Prefer CLANG_PATH env var
    if let Some(clang_path) = environment
        .get("CLANG_PATH")
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    {
        let path = PathBuf::from(clang_path);
        if path.exists() || path.components().count() == 1 {
            return Some((path, "CLANG_PATH".to_string()));
        }
        return None;
    }

    // 2. Fall back to vendored local paths (relative to cwd / repo root)
    #[cfg(target_os = "windows")]
    let candidates: &[&str] = &[
        "tools/llvm/bin/clang.exe",
        "tools/llvm/bin/clang-18.exe",
        "tools/clang/bin/clang.exe",
    ];
    #[cfg(not(target_os = "windows"))]
    let candidates: &[&str] = &[
        "tools/llvm/bin/clang-18",
        "tools/llvm/bin/clang",
        "tools/clang/bin/clang",
    ];

    let cwd = env::current_dir().ok()?;
    for candidate in candidates {
        let path = cwd.join(candidate);
        if path.exists() {
            return Some((path, format!("vendored:{}", candidate)));
        }
    }

    // 3. Also try with CARGO_MANIFEST_DIR fallback (relative to the crate root)
    if let Ok(manifest_dir) = env::var("CARGO_MANIFEST_DIR") {
        let workspace_root = PathBuf::from(&manifest_dir)
            .parent()
            .unwrap_or(Path::new(&manifest_dir))
            .parent()
            .unwrap_or(Path::new(&manifest_dir))
            .to_path_buf();
        for candidate in candidates {
            let path = workspace_root.join(candidate);
            if path.exists() {
                return Some((path, format!("vendored(cargo):{}", candidate)));
            }
        }
    }

    None
}

mod compile_database;
#[cfg(feature = "typed-ir")]
mod enums;
#[cfg(feature = "typed-ir")]
mod lower_ir;
#[cfg(feature = "typed-ir")]
mod records;
#[cfg(feature = "typed-ir")]
mod skeleton;
#[cfg(feature = "typed-ir")]
mod types;
pub use compile_database::resolve_compile_database;
#[cfg(feature = "typed-ir")]
use enums::*;
#[cfg(all(test, feature = "typed-ir"))]
#[path = "clang_frontend/tests/compile_database.rs"]
mod compile_database_tests;
#[cfg(feature = "typed-ir")]
use lower_ir::*;
#[cfg(feature = "typed-ir")]
use records::*;
#[cfg(feature = "typed-ir")]
pub use skeleton::*;
#[cfg(feature = "typed-ir")]
use types::*;

include!("clang_frontend/parse_spec_impl.rs");
include!("clang_frontend/ast_dump.rs");
include!("clang_frontend/record_layout.rs");
include!("clang_frontend/record_layout_binding.rs");
include!("clang_frontend/interior_reborrow.rs");
include!("clang_frontend/record_scalar_add.rs");
include!("clang_frontend/record_scalar_add_validation.rs");
include!("clang_frontend/globals.rs");
include!("clang_frontend/functions.rs");
include!("clang_frontend/statements.rs");
include!("clang_frontend/expressions.rs");
include!("clang_frontend/calls.rs");
include!("clang_frontend/ast_utils.rs");
include!("clang_frontend/tests.rs");
