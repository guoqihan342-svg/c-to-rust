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

#[cfg(feature = "typed-ir")]
use crate::typed_ir::{
    IrBinOp, IrExpr, IrFunction, IrGlobal, IrGlobalInit, IrIncDecOp, IrParam, IrRecordField,
    IrStmt, IrType, IrTypeKind, IrUnOp,
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
    pub compile_commands: Option<PathBuf>,
    pub source_file_hashes: BTreeMap<String, String>,
    pub function_source_span: Option<SourceSpanRef>,
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
/// 1. `CLANG_PATH` environment variable (if set and the file exists)
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
        if path.exists() {
            return Some((path, "CLANG_PATH".to_string()));
        }
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

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClangFunctionSkeleton {
    pub name: String,
    pub return_type: ClangTypeSkeleton,
    pub params: Vec<ClangParamSkeleton>,
    pub body: Vec<ClangStmtSkeleton>,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClangParamSkeleton {
    pub name: String,
    pub ty: ClangTypeSkeleton,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ClangTypeSkeleton {
    pub spelled: String,
    pub canonical: String,
    pub kind: ClangTypeKind,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangTypeKind {
    Void,
    Integer {
        signed: bool,
        width: u16,
    },
    Pointer {
        pointee: Box<ClangTypeSkeleton>,
        width: Option<u16>,
    },
    Array {
        element: Box<ClangTypeSkeleton>,
        len: Option<usize>,
    },
    Record {
        name: String,
    },
    Function,
    Unsupported {
        reason: String,
    },
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangStmtSkeleton {
    Decl {
        name: String,
        ty: ClangTypeSkeleton,
        init: Option<ClangExprSkeleton>,
    },
    Assign {
        target: ClangExprSkeleton,
        value: ClangExprSkeleton,
    },
    CompoundAssign {
        target: ClangExprSkeleton,
        op: ClangBinaryOperator,
        value: ClangExprSkeleton,
        result_ty: ClangTypeSkeleton,
        compute_lhs_ty: ClangTypeSkeleton,
        compute_result_ty: ClangTypeSkeleton,
    },
    If {
        condition: ClangExprSkeleton,
        then_body: Vec<ClangStmtSkeleton>,
        else_body: Vec<ClangStmtSkeleton>,
    },
    While {
        condition: ClangExprSkeleton,
        body: Vec<ClangStmtSkeleton>,
    },
    DoWhile {
        body: Vec<ClangStmtSkeleton>,
        condition: ClangExprSkeleton,
    },
    For {
        init: Vec<ClangStmtSkeleton>,
        condition: Option<ClangExprSkeleton>,
        step: Option<Box<ClangStmtSkeleton>>,
        body: Vec<ClangStmtSkeleton>,
    },
    Return {
        value: Option<ClangExprSkeleton>,
    },
    Break,
    Continue,
    Expr {
        expr: ClangExprSkeleton,
    },
    Unsupported {
        reason: String,
    },
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangExprSkeleton {
    DeclRef {
        name: String,
        ty: ClangTypeSkeleton,
    },
    IntegerLiteral {
        value: u64,
        spelling: String,
        ty: ClangTypeSkeleton,
    },
    SizeOfType {
        arg_type: ClangTypeSkeleton,
        ty: ClangTypeSkeleton,
    },
    AlignOfType {
        arg_type: ClangTypeSkeleton,
        ty: ClangTypeSkeleton,
        alignment_bits: Option<u16>,
    },
    NullPtr {
        ty: ClangTypeSkeleton,
    },
    Binary {
        op: ClangBinaryOperator,
        lhs: Box<ClangExprSkeleton>,
        rhs: Box<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    Unary {
        op: ClangUnaryOperator,
        operand: Box<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    Conditional {
        condition: Box<ClangExprSkeleton>,
        then_expr: Box<ClangExprSkeleton>,
        else_expr: Box<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    IncDec {
        target: Box<ClangExprSkeleton>,
        op: ClangIncDecOperator,
        prefix: bool,
        ty: ClangTypeSkeleton,
    },
    Deref {
        ptr: Box<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    AddrOf {
        operand: Box<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    Cast {
        target: ClangTypeSkeleton,
        expr: Box<ClangExprSkeleton>,
        implicit: bool,
    },
    LValueToRValue {
        target: ClangTypeSkeleton,
        expr: Box<ClangExprSkeleton>,
    },
    ArrayToPointerDecay {
        target: ClangTypeSkeleton,
        expr: Box<ClangExprSkeleton>,
    },
    FunctionToPointerDecay {
        target: ClangTypeSkeleton,
        expr: Box<ClangExprSkeleton>,
    },
    Index {
        base: Box<ClangExprSkeleton>,
        index: Box<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    ArrayLiteral {
        elements: Vec<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    Call {
        callee: String,
        args: Vec<ClangExprSkeleton>,
        ty: ClangTypeSkeleton,
    },
    Member {
        base: Box<ClangExprSkeleton>,
        field: String,
        ty: ClangTypeSkeleton,
        is_arrow: bool,
    },
    Unsupported {
        node: String,
        reason: String,
    },
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangBinaryOperator {
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    BitAnd,
    BitOr,
    BitXor,
    Shl,
    Shr,
    LogAnd,
    LogOr,
    Eq,
    Neq,
    Lt,
    Le,
    Gt,
    Ge,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangUnaryOperator {
    Neg,
    Not,
    BitNot,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangIncDecOperator {
    Inc,
    Dec,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangLoweringReport {
    pub status: String,
    pub frontend: String,
    pub source_file: Option<String>,
    pub function_name: String,
    pub clang_path: Option<String>,
    pub arguments: Vec<String>,
    pub environment: ClangEnvironment,
    pub diagnostics: Vec<String>,
    pub errors: Vec<ClangFrontendError>,
    pub function_ir: Option<IrFunction>,
    pub globals: Vec<IrGlobal>,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LoweredFunctionWithGlobals {
    pub function_ir: IrFunction,
    pub globals: Vec<IrGlobal>,
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
            target_abi: spec.build_profile.target.clone(),
            compile_commands: spec.compile_commands.as_ref().map(PathBuf::from),
            source_file_hashes: spec.source_file_hashes.clone(),
            function_source_span: Some(function_source_span),
        })
    }

    pub fn dry_run(&self) -> ClangDryRun {
        self.dry_run_with_environment(&env::vars().collect())
    }

    pub fn dry_run_with_environment(&self, environment: &BTreeMap<String, String>) -> ClangDryRun {
        let mut diagnostics = vec![
            "LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH"
                .to_string(),
        ];
        if self.compile_commands.is_some() {
            diagnostics.push(
                "compile_commands is present; dry-run arguments omit synthesized include/define flags"
                    .to_string(),
            );
        }

        ClangDryRun {
            status: "diagnostic_only".to_string(),
            active_frontend: clang_ast_dump_active_frontend(),
            claim_boundary: diagnostic_claim_boundary(),
            source_root: self.source_root.to_string_lossy().into_owned(),
            source_file: self.source_file.to_string_lossy().into_owned(),
            function_name: self.function_name.clone(),
            arguments: self.clang_arguments(),
            compile_commands: self
                .compile_commands
                .as_ref()
                .map(|path| path.to_string_lossy().into_owned()),
            environment: ClangEnvironment::detect_from_env(environment),
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

pub fn clang_ast_dump_active_frontend() -> ClangActiveFrontend {
    ClangActiveFrontend {
        kind: "clang_ast_dump_json".to_string(),
        command: "clang -Xclang -ast-dump=json -fsyntax-only".to_string(),
        required_env: vec!["CLANG_PATH".to_string()],
        uses_libclang: false,
    }
}

pub fn diagnostic_claim_boundary() -> ClangClaimBoundary {
    ClangClaimBoundary {
        role: "diagnostic_only".to_string(),
        affects_manifest_status: false,
        affects_semantic_pass: false,
        authoritative_evidence: false,
    }
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_ast_dump(
    clang_path: &Path,
    source_file: &Path,
    function_name: &str,
) -> Result<IrFunction, ClangFrontendError> {
    let arguments = clang_ast_dump_arguments(source_file);
    lower_function_from_clang_ast_dump_with_arguments(clang_path, &arguments, function_name)
}

#[cfg(feature = "typed-ir")]
fn lower_function_from_clang_ast_dump_with_arguments(
    clang_path: &Path,
    arguments: &[String],
    function_name: &str,
) -> Result<IrFunction, ClangFrontendError> {
    lower_function_and_globals_from_clang_ast_dump_with_arguments(
        clang_path,
        arguments,
        function_name,
    )
    .map(|lowered| lowered.function_ir)
}

#[cfg(feature = "typed-ir")]
fn lower_function_and_globals_from_clang_ast_dump_with_arguments(
    clang_path: &Path,
    arguments: &[String],
    function_name: &str,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    let ast = clang_ast_dump_json(clang_path, arguments)?;
    lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_and_globals_from_clang_ast_json_value(
    ast: &Value,
    function_name: &str,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    lower_function_and_globals_from_clang_ast_json_value_with_target_abi(ast, function_name, None)
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
    ast: &Value,
    function_name: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<LoweredFunctionWithGlobals, ClangFrontendError> {
    let record_inventory = record_inventory_from_ast_with_target_abi(&ast, target_abi);
    let enum_constant_inventory = enum_constant_inventory_from_ast(&ast);
    let enum_type_inventory = enum_type_inventory_from_ast(&ast, target_abi);
    let function = find_function_decl(&ast, function_name).ok_or_else(|| ClangFrontendError {
        kind: "missing_function_decl".to_string(),
        message: format!("clang AST JSON does not contain FunctionDecl named {function_name}"),
    })?;
    let mut function = function.clone();
    rewrite_enum_constant_decl_refs_to_integer_literals(&mut function, &enum_constant_inventory)?;
    let mut skeleton = function_skeleton_from_ast(&function)?;
    rewrite_supported_enum_types_in_function_skeleton(&mut skeleton, &enum_type_inventory)?;
    if let Some(target_abi) = target_abi {
        bind_target_abi_to_function_skeleton(&mut skeleton, target_abi);
    }
    let mut function_ir = lower_function_skeleton(&skeleton)?;
    attach_record_inventory_to_function(&mut function_ir, &record_inventory);
    let globals = readonly_globals_from_ast(&ast)?;

    Ok(LoweredFunctionWithGlobals {
        function_ir,
        globals,
    })
}

#[cfg(feature = "typed-ir")]
fn clang_ast_dump_json(
    clang_path: &Path,
    arguments: &[String],
) -> Result<Value, ClangFrontendError> {
    let output = Command::new(clang_path)
        .args(arguments)
        .output()
        .map_err(|error| ClangFrontendError {
            kind: "clang_ast_dump_unavailable".to_string(),
            message: format!("failed to execute clang ast dump: {error}"),
        })?;
    if !output.status.success() {
        return Err(ClangFrontendError {
            kind: "clang_ast_dump_failed".to_string(),
            message: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        });
    }

    let ast: Value =
        serde_json::from_slice(&output.stdout).map_err(|error| ClangFrontendError {
            kind: "invalid_clang_ast_json".to_string(),
            message: format!("failed to parse clang AST JSON: {error}"),
        })?;
    Ok(ast)
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_parse_spec_report(
    environment: &BTreeMap<String, String>,
    parse_spec: &ClangParseSpec,
) -> ClangLoweringReport {
    let source_file = parse_spec.source_root.join(&parse_spec.source_file);
    let arguments =
        clang_ast_dump_arguments_with_extra(&source_file, &parse_spec.clang_arguments());
    let Some((clang_path, _clang_source)) = resolve_clang_path(environment) else {
        return ClangLoweringReport {
            status: "unavailable".to_string(),
            frontend: "clang".to_string(),
            source_file: Some(normalized_report_path(&source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![
                "CLANG_PATH is not set and no vendored clang binary found in tools/llvm/bin/ or tools/clang/bin/; clang AST lowering is unavailable".to_string()
            ],
            errors: vec![ClangFrontendError {
                kind: "missing_clang_path".to_string(),
                message: "clang AST lowering requires CLANG_PATH or a vendored clang binary".to_string(),
            }],
            function_ir: None,
            globals: Vec::new(),
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(&source_file)),
        parse_spec.function_name.clone(),
        Some(clang_path.to_string_lossy().to_string()),
        arguments.clone(),
        environment,
        clang_ast_dump_json(&clang_path, &arguments).and_then(|ast| {
            lower_function_and_globals_from_clang_ast_json_value_with_target_abi(
                &ast,
                &parse_spec.function_name,
                parse_spec.target_abi.as_ref(),
            )
        }),
    )
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_ast_dump_report(
    environment: &BTreeMap<String, String>,
    source_file: &Path,
    function_name: &str,
) -> ClangLoweringReport {
    let arguments = clang_ast_dump_arguments(source_file);
    let Some((clang_path, _clang_source)) = resolve_clang_path(environment) else {
        return ClangLoweringReport {
            status: "unavailable".to_string(),
            frontend: "clang".to_string(),
            source_file: Some(normalized_report_path(source_file)),
            function_name: function_name.to_string(),
            clang_path: None,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![
                "CLANG_PATH is not set and no vendored clang binary found in tools/llvm/bin/ or tools/clang/bin/; clang AST lowering is unavailable".to_string()
            ],
            errors: vec![ClangFrontendError {
                kind: "missing_clang_path".to_string(),
                message: "clang AST lowering requires CLANG_PATH or a vendored clang binary".to_string(),
            }],
            function_ir: None,
            globals: Vec::new(),
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(source_file)),
        function_name.to_string(),
        Some(clang_path.to_string_lossy().to_string()),
        arguments.clone(),
        environment,
        lower_function_and_globals_from_clang_ast_dump_with_arguments(
            &clang_path,
            &arguments,
            function_name,
        ),
    )
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_skeleton_report(
    function: &ClangFunctionSkeleton,
    environment: &BTreeMap<String, String>,
) -> ClangLoweringReport {
    report_from_lowering_result(
        None,
        function.name.clone(),
        None,
        Vec::new(),
        environment,
        lower_function_skeleton(function).map(|function_ir| LoweredFunctionWithGlobals {
            function_ir,
            globals: Vec::new(),
        }),
    )
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_skeleton(
    function: &ClangFunctionSkeleton,
) -> Result<IrFunction, ClangFrontendError> {
    Ok(IrFunction {
        name: function.name.clone(),
        return_type: lower_type(&function.return_type)?,
        params: function
            .params
            .iter()
            .map(|param| {
                Ok(IrParam {
                    name: param.name.clone(),
                    ty: lower_type(&param.ty)?,
                    source_span: None,
                })
            })
            .collect::<Result<Vec<_>, ClangFrontendError>>()?,
        body: function
            .body
            .iter()
            .map(lower_stmt)
            .collect::<Result<Vec<_>, ClangFrontendError>>()?,
        source_span: None,
    })
}

#[cfg(feature = "typed-ir")]
fn clang_ast_dump_arguments(source_file: &Path) -> Vec<String> {
    clang_ast_dump_arguments_with_extra(source_file, &[])
}

#[cfg(feature = "typed-ir")]
fn clang_ast_dump_arguments_with_extra(
    source_file: &Path,
    extra_arguments: &[String],
) -> Vec<String> {
    vec![
        "-Xclang".to_string(),
        "-ast-dump=json".to_string(),
        "-fsyntax-only".to_string(),
    ]
    .into_iter()
    .chain(extra_arguments.iter().cloned())
    .chain(std::iter::once(source_file.to_string_lossy().into_owned()))
    .collect()
}

#[cfg(feature = "typed-ir")]
fn report_from_lowering_result(
    source_file: Option<String>,
    function_name: String,
    clang_path: Option<String>,
    arguments: Vec<String>,
    environment: &BTreeMap<String, String>,
    result: Result<LoweredFunctionWithGlobals, ClangFrontendError>,
) -> ClangLoweringReport {
    match result {
        Ok(lowered) => ClangLoweringReport {
            status: "lowered".to_string(),
            frontend: "clang".to_string(),
            source_file,
            function_name,
            clang_path,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: Vec::new(),
            errors: Vec::new(),
            function_ir: Some(lowered.function_ir),
            globals: lowered.globals,
        },
        Err(error) => ClangLoweringReport {
            status: lowering_status_for_error(&error).to_string(),
            frontend: "clang".to_string(),
            source_file,
            function_name,
            clang_path,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![error.message.clone()],
            errors: vec![error],
            function_ir: None,
            globals: Vec::new(),
        },
    }
}

#[cfg(feature = "typed-ir")]
fn lowering_status_for_error(error: &ClangFrontendError) -> &'static str {
    if error.kind == "missing_clang_path" || error.kind == "clang_ast_dump_unavailable" {
        "unavailable"
    } else if error.kind.starts_with("unsupported_") {
        "unsupported"
    } else {
        "blocked"
    }
}

#[cfg(feature = "typed-ir")]
fn readonly_globals_from_ast(ast: &Value) -> Result<Vec<IrGlobal>, ClangFrontendError> {
    let enum_constant_inventory = enum_constant_inventory_from_ast(ast);
    readonly_globals_from_ast_with_enum_inventory(ast, &enum_constant_inventory)
}

#[cfg(feature = "typed-ir")]
fn readonly_globals_from_ast_with_enum_inventory(
    ast: &Value,
    enum_constant_inventory: &EnumConstantInventory,
) -> Result<Vec<IrGlobal>, ClangFrontendError> {
    inner(ast)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("VarDecl"))
        .filter_map(|var_decl| {
            readonly_global_from_toplevel_var_decl(var_decl, enum_constant_inventory)
        })
        .collect()
}

#[cfg(feature = "typed-ir")]
fn readonly_global_from_toplevel_var_decl(
    var_decl: &Value,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<Result<IrGlobal, ClangFrontendError>> {
    if string_field(var_decl, "storageClass").as_deref() != Some("static") {
        return None;
    }

    let name = string_field(var_decl, "name")?;
    let clang_ty = type_from_ast_type_object(var_decl.get("type")?, None).ok()?;
    let ClangTypeKind::Array { element, len } = &clang_ty.kind else {
        return None;
    };
    if !clang_type_is_const(&clang_ty)
        || len.is_none()
        || !matches!(element.kind, ClangTypeKind::Integer { .. })
    {
        return None;
    }

    let [initializer] = inner(var_decl) else {
        return None;
    };
    if string_field(initializer, "kind").as_deref() != Some("InitListExpr") {
        return None;
    }

    let array_len = (*len)?;
    let values = integer_literal_init_list_values(initializer, array_len, enum_constant_inventory)?;
    if values.len() != array_len {
        return None;
    }

    Some(lower_type(&clang_ty).map(|ty| IrGlobal {
        name,
        ty,
        init: IrGlobalInit::IntegerArray(values),
        source_span: None,
    }))
}

#[cfg(feature = "typed-ir")]
fn integer_literal_init_list_values(
    init_list: &Value,
    len: usize,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<Vec<u64>> {
    let entries = inner(init_list);
    if entries.is_empty() {
        return integer_literal_array_filler_values(init_list, len, enum_constant_inventory);
    }
    entries
        .iter()
        .map(|entry| integer_literal_init_value(entry, enum_constant_inventory))
        .collect()
}

#[cfg(feature = "typed-ir")]
fn integer_literal_array_filler_values(
    init_list: &Value,
    len: usize,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<Vec<u64>> {
    let filler_entries = array_filler(init_list)?;
    let filler = filler_entries.first()?;
    if string_field(filler, "kind").as_deref() != Some("ImplicitValueInitExpr") {
        return None;
    }
    if filler_entries.len().saturating_sub(1) > len {
        return None;
    }
    let filler_value = integer_literal_init_value(filler, enum_constant_inventory)?;
    let mut values = filler_entries[1..]
        .iter()
        .map(|entry| integer_literal_init_value(entry, enum_constant_inventory))
        .collect::<Option<Vec<_>>>()?;
    while values.len() < len {
        values.push(filler_value);
    }
    Some(values)
}

#[cfg(feature = "typed-ir")]
fn integer_literal_init_value(
    item: &Value,
    enum_constant_inventory: &EnumConstantInventory,
) -> Option<u64> {
    match string_field(item, "kind").as_deref() {
        Some("IntegerLiteral") => string_field(item, "value")?.parse::<u64>().ok(),
        Some("DeclRefExpr") => {
            enum_constant_literal_for_decl_ref_expr(item, enum_constant_inventory)
                .ok()
                .map(|literal| literal.value)
        }
        Some("ImplicitValueInitExpr") => {
            let ty = expr_type(item).ok()?;
            if matches!(ty.kind, ClangTypeKind::Integer { .. }) {
                Some(0)
            } else {
                None
            }
        }
        Some("ImplicitCastExpr" | "ParenExpr") => {
            let [operand] = inner(item) else {
                return None;
            };
            integer_literal_init_value(operand, enum_constant_inventory)
        }
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
struct ClangEnumConstantLiteral {
    name: String,
    value: u64,
    spelling: String,
    ty: ClangTypeSkeleton,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Default)]
struct EnumConstantInventory {
    by_id: BTreeMap<String, Result<ClangEnumConstantLiteral, String>>,
    by_name: BTreeMap<String, Option<Result<ClangEnumConstantLiteral, String>>>,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Default)]
struct EnumTypeInventory {
    by_name: BTreeMap<String, Result<ClangTypeSkeleton, String>>,
}

#[cfg(feature = "typed-ir")]
fn enum_constant_inventory_from_ast(ast: &Value) -> EnumConstantInventory {
    let mut inventory = EnumConstantInventory::default();
    collect_enum_constant_inventory_from_ast(ast, &mut inventory);
    inventory
}

#[cfg(feature = "typed-ir")]
fn enum_type_inventory_from_ast(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> EnumTypeInventory {
    let mut inventory = EnumTypeInventory::default();
    collect_enum_type_inventory_from_ast(ast, target_abi, &mut inventory);
    inventory
}

#[cfg(feature = "typed-ir")]
fn collect_enum_type_inventory_from_ast(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
    inventory: &mut EnumTypeInventory,
) {
    if string_field(node, "kind").as_deref() == Some("EnumDecl") {
        if let Some(name) = enum_decl_name(node) {
            let entry = enum_type_from_decl(node, &name, target_abi);
            match inventory.by_name.entry(name) {
                std::collections::btree_map::Entry::Vacant(slot) => {
                    slot.insert(entry);
                }
                std::collections::btree_map::Entry::Occupied(mut slot) => {
                    let _previous = slot.insert(Err(
                        "duplicate EnumDecl name in clang AST; enum type lowering requires unique declaration provenance"
                            .to_string(),
                    ));
                }
            }
        }
    }
    for child in inner(node) {
        collect_enum_type_inventory_from_ast(child, target_abi, inventory);
    }
}

#[cfg(feature = "typed-ir")]
fn enum_decl_name(node: &Value) -> Option<String> {
    let name = string_field(node, "name")?;
    if is_simple_c_identifier(&name) {
        Some(name)
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
fn enum_type_from_decl(
    node: &Value,
    name: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, String> {
    let Some(target_abi) = target_abi else {
        return Err(format!(
            "EnumDecl {name} requires target ABI profile evidence before enum-typed scalar lowering"
        ));
    };
    if nonzero_width(target_abi.int_width) != Some(32) {
        return Err(format!(
            "EnumDecl {name} requires target ABI int_width=32 for the current enum-typed scalar subset"
        ));
    }
    if node.get("completeDefinition").and_then(Value::as_bool) != Some(true) {
        return Err(format!(
            "EnumDecl {name} is not a complete definition; enum type lowering requires all constants"
        ));
    }
    if node.get("isImplicit").and_then(Value::as_bool) == Some(true) {
        return Err(format!(
            "EnumDecl {name} is implicit; enum type lowering requires explicit source provenance"
        ));
    }

    let constants = inner(node)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("EnumConstantDecl"))
        .collect::<Vec<_>>();
    if constants.is_empty() {
        return Err(format!(
            "EnumDecl {name} has no constants; enum type lowering requires an explicit i32 value domain"
        ));
    }

    for constant in constants {
        let literal = enum_constant_literal_from_decl(constant)?;
        if !matches!(
            literal.ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ) {
            return Err(format!(
                "EnumDecl {name} constant {} has type {}; only explicit int-backed enums are currently supported",
                literal.name, literal.ty.spelled
            ));
        }
        if literal.value > i32::MAX as u64 {
            return Err(format!(
                "EnumDecl {name} constant {} value {} does not fit the current i32 enum subset",
                literal.name, literal.spelling
            ));
        }
    }

    Ok(ClangTypeSkeleton {
        spelled: format!("enum {name}"),
        canonical: "int".to_string(),
        kind: ClangTypeKind::Integer {
            signed: true,
            width: 32,
        },
    })
}

#[cfg(feature = "typed-ir")]
fn collect_enum_constant_inventory_from_ast(node: &Value, inventory: &mut EnumConstantInventory) {
    if string_field(node, "kind").as_deref() == Some("EnumConstantDecl") {
        let entry = enum_constant_literal_from_decl(node);
        if let Some(id) = string_field(node, "id") {
            match inventory.by_id.entry(id) {
                std::collections::btree_map::Entry::Vacant(slot) => {
                    slot.insert(entry.clone());
                }
                std::collections::btree_map::Entry::Occupied(mut slot) => {
                    let _previous = slot.insert(Err(
                    "duplicate EnumConstantDecl id in clang AST; enum constant lowering requires a unique declaration id"
                        .to_string(),
                ));
                }
            }
        }
        if let Some(name) = enum_constant_decl_name(node) {
            match inventory.by_name.entry(name) {
                std::collections::btree_map::Entry::Vacant(slot) => {
                    slot.insert(Some(entry));
                }
                std::collections::btree_map::Entry::Occupied(mut slot) => {
                    slot.insert(None);
                }
            }
        }
    }
    for child in inner(node) {
        collect_enum_constant_inventory_from_ast(child, inventory);
    }
}

#[cfg(feature = "typed-ir")]
fn enum_constant_literal_from_decl(node: &Value) -> Result<ClangEnumConstantLiteral, String> {
    let name = enum_constant_decl_name(node)
        .ok_or_else(|| "EnumConstantDecl is missing name".to_string())?;
    let type_object = node
        .get("type")
        .ok_or_else(|| format!("EnumConstantDecl {name} is missing type.qualType"))?;
    let ty = type_from_ast_type_object(type_object, None).map_err(|error| {
        format!(
            "EnumConstantDecl {name} has unsupported type: {}",
            error.message
        )
    })?;
    if !matches!(ty.kind, ClangTypeKind::Integer { .. }) {
        return Err(format!(
            "EnumConstantDecl {name} type {} is not an integer type; enum type lowering is outside the current skeleton",
            ty.spelled
        ));
    }

    let constant_expr = inner(node)
        .iter()
        .find(|child| string_field(child, "kind").as_deref() == Some("ConstantExpr"))
        .ok_or_else(|| {
            format!(
                "EnumConstantDecl {name} is missing explicit ConstantExpr value; implicit enum values are outside the current clang lowering skeleton"
            )
        })?;
    let spelling = string_field(constant_expr, "value").ok_or_else(|| {
        format!(
            "EnumConstantDecl {name} is missing explicit ConstantExpr value; computed enum constants are outside the current clang lowering skeleton"
        )
    })?;
    let value = spelling.parse::<u64>().map_err(|error| {
        format!(
            "EnumConstantDecl {name} explicit ConstantExpr value {spelling} is not a supported non-negative u64 integer literal: {error}"
        )
    })?;
    if !enum_constant_has_matching_direct_integer_literal(constant_expr, &spelling) {
        return Err(format!(
            "EnumConstantDecl {name} requires a direct IntegerLiteral child matching explicit ConstantExpr value {spelling}; computed enum constants are outside the current clang lowering skeleton"
        ));
    }

    Ok(ClangEnumConstantLiteral {
        name,
        value,
        spelling,
        ty,
    })
}

#[cfg(feature = "typed-ir")]
fn enum_constant_has_matching_direct_integer_literal(
    constant_expr: &Value,
    spelling: &str,
) -> bool {
    inner(constant_expr).iter().any(|child| {
        string_field(child, "kind").as_deref() == Some("IntegerLiteral")
            && string_field(child, "value").as_deref() == Some(spelling)
    })
}

#[cfg(feature = "typed-ir")]
fn enum_constant_decl_name(node: &Value) -> Option<String> {
    string_field(node, "name").filter(|name| !name.trim().is_empty())
}

#[cfg(feature = "typed-ir")]
fn rewrite_enum_constant_decl_refs_to_integer_literals(
    node: &mut Value,
    inventory: &EnumConstantInventory,
) -> Result<(), ClangFrontendError> {
    if enum_constant_ref_from_decl_ref_expr(node).is_some() {
        let literal = enum_constant_literal_for_decl_ref_expr(node, inventory)?;
        *node = serde_json::json!({
            "kind": "IntegerLiteral",
            "type": {
                "qualType": literal.ty.spelled,
            },
            "value": literal.spelling,
        });
        return Ok(());
    }

    if let Some(children) = node.get_mut("inner").and_then(Value::as_array_mut) {
        for child in children {
            rewrite_enum_constant_decl_refs_to_integer_literals(child, inventory)?;
        }
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn enum_constant_ref_from_decl_ref_expr(node: &Value) -> Option<&Value> {
    if string_field(node, "kind").as_deref() != Some("DeclRefExpr") {
        return None;
    }
    let referenced_decl = node.get("referencedDecl")?;
    if string_field(referenced_decl, "kind").as_deref() == Some("EnumConstantDecl") {
        Some(referenced_decl)
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
fn enum_constant_literal_for_decl_ref_expr(
    node: &Value,
    inventory: &EnumConstantInventory,
) -> Result<ClangEnumConstantLiteral, ClangFrontendError> {
    let referenced_decl =
        enum_constant_ref_from_decl_ref_expr(node).ok_or_else(|| ClangFrontendError {
            kind: "invalid_decl_ref_expr".to_string(),
            message: "DeclRefExpr is not an EnumConstantDecl reference".to_string(),
        })?;
    let name = enum_constant_decl_name(referenced_decl).ok_or_else(|| ClangFrontendError {
        kind: "invalid_decl_ref_expr".to_string(),
        message: "DeclRefExpr EnumConstantDecl reference is missing name".to_string(),
    })?;
    if let Some(id) = string_field(referenced_decl, "id") {
        let entry = inventory.by_id.get(&id).ok_or_else(|| ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "EnumConstantDecl {name} with id {id} is not present in the clang enum constant inventory"
            ),
        })?;
        return enum_constant_inventory_entry_result(&name, entry);
    }

    match inventory.by_name.get(&name) {
        Some(Some(entry)) => enum_constant_inventory_entry_result(&name, entry),
        Some(None) => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "EnumConstantDecl {name} reference is ambiguous without a declaration id; enum constant lowering requires unique clang provenance"
            ),
        }),
        None => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "EnumConstantDecl {name} is not present in the clang enum constant inventory"
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn enum_constant_inventory_entry_result(
    name: &str,
    entry: &Result<ClangEnumConstantLiteral, String>,
) -> Result<ClangEnumConstantLiteral, ClangFrontendError> {
    match entry {
        Ok(literal) => Ok(literal.clone()),
        Err(reason) => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!("EnumConstantDecl {name}: {reason}"),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_function_skeleton(
    function: &mut ClangFunctionSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    rewrite_supported_enum_type(&mut function.return_type, inventory)?;
    for param in &mut function.params {
        rewrite_supported_enum_type(&mut param.ty, inventory)?;
    }
    rewrite_supported_enum_types_in_stmts(&mut function.body, inventory)
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_stmts(
    statements: &mut [ClangStmtSkeleton],
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    for statement in statements {
        rewrite_supported_enum_types_in_stmt(statement, inventory)?;
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_stmt(
    statement: &mut ClangStmtSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    match statement {
        ClangStmtSkeleton::Decl { ty, init, .. } => {
            rewrite_supported_enum_type(ty, inventory)?;
            if let Some(init) = init {
                rewrite_supported_enum_types_in_expr(init, inventory)?;
            }
        }
        ClangStmtSkeleton::Assign { target, value } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_types_in_expr(value, inventory)?;
        }
        ClangStmtSkeleton::CompoundAssign {
            target,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            ..
        } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_types_in_expr(value, inventory)?;
            rewrite_supported_enum_type(result_ty, inventory)?;
            rewrite_supported_enum_type(compute_lhs_ty, inventory)?;
            rewrite_supported_enum_type(compute_result_ty, inventory)?;
        }
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_stmts(then_body, inventory)?;
            rewrite_supported_enum_types_in_stmts(else_body, inventory)?;
        }
        ClangStmtSkeleton::While { condition, body } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
        }
        ClangStmtSkeleton::DoWhile { body, condition } => {
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
        }
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => {
            rewrite_supported_enum_types_in_stmts(init, inventory)?;
            if let Some(condition) = condition {
                rewrite_supported_enum_types_in_expr(condition, inventory)?;
            }
            if let Some(step) = step {
                rewrite_supported_enum_types_in_stmt(step, inventory)?;
            }
            rewrite_supported_enum_types_in_stmts(body, inventory)?;
        }
        ClangStmtSkeleton::Return { value } => {
            if let Some(value) = value {
                rewrite_supported_enum_types_in_expr(value, inventory)?;
            }
        }
        ClangStmtSkeleton::Expr { expr } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
        }
        ClangStmtSkeleton::Break
        | ClangStmtSkeleton::Continue
        | ClangStmtSkeleton::Unsupported { .. } => {}
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_types_in_expr(
    expr: &mut ClangExprSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::NullPtr { ty } => {
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::SizeOfType { ty, .. } | ClangExprSkeleton::AlignOfType { ty, .. } => {
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Binary { lhs, rhs, ty, .. } => {
            rewrite_supported_enum_types_in_expr(lhs, inventory)?;
            rewrite_supported_enum_types_in_expr(rhs, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Unary { operand, ty, .. } => {
            rewrite_supported_enum_types_in_expr(operand, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => {
            rewrite_supported_enum_types_in_expr(condition, inventory)?;
            rewrite_supported_enum_types_in_expr(then_expr, inventory)?;
            rewrite_supported_enum_types_in_expr(else_expr, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Cast { expr, target, .. }
        | ClangExprSkeleton::LValueToRValue { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::Call { args, ty, .. } => {
            for arg in args {
                rewrite_supported_enum_types_in_expr(arg, inventory)?;
            }
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::IncDec { target, ty, .. } => {
            rewrite_supported_enum_types_in_expr(target, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Deref { ptr, ty } => {
            rewrite_supported_enum_types_in_expr(ptr, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::AddrOf { operand, ty } => {
            rewrite_supported_enum_types_in_expr(operand, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::ArrayToPointerDecay { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::FunctionToPointerDecay { expr, target } => {
            rewrite_supported_enum_types_in_expr(expr, inventory)?;
            rewrite_supported_enum_type(target, inventory)?;
        }
        ClangExprSkeleton::Index { base, index, ty } => {
            rewrite_supported_enum_types_in_expr(base, inventory)?;
            rewrite_supported_enum_types_in_expr(index, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::ArrayLiteral { elements, ty } => {
            for element in elements {
                rewrite_supported_enum_types_in_expr(element, inventory)?;
            }
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Member { base, ty, .. } => {
            rewrite_supported_enum_types_in_expr(base, inventory)?;
            rewrite_supported_enum_type(ty, inventory)?;
        }
        ClangExprSkeleton::Unsupported { .. } => {}
    }
    Ok(())
}

#[cfg(feature = "typed-ir")]
fn rewrite_supported_enum_type(
    ty: &mut ClangTypeSkeleton,
    inventory: &EnumTypeInventory,
) -> Result<(), ClangFrontendError> {
    let Some(name) = direct_enum_type_name(ty) else {
        return Ok(());
    };
    let entry = inventory.by_name.get(&name).ok_or_else(|| ClangFrontendError {
        kind: "unsupported_clang_type".to_string(),
        message: format!(
            "enum {name} is not present in the clang enum type inventory; enum type lowering requires a complete EnumDecl"
        ),
    })?;
    match entry {
        Ok(mapped) => {
            *ty = mapped.clone();
            Ok(())
        }
        Err(reason) => Err(ClangFrontendError {
            kind: "unsupported_clang_type".to_string(),
            message: format!("enum {name}: {reason}"),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn direct_enum_type_name(ty: &ClangTypeSkeleton) -> Option<String> {
    direct_enum_name_from_spelling(&ty.spelled)
        .or_else(|| direct_enum_name_from_spelling(&ty.canonical))
}

#[cfg(feature = "typed-ir")]
fn direct_enum_name_from_spelling(spelling: &str) -> Option<String> {
    let name = spelling.trim().strip_prefix("enum ")?.trim();
    if is_simple_c_identifier(name) {
        Some(name.to_string())
    } else {
        None
    }
}

#[cfg(feature = "typed-ir")]
fn function_skeleton_from_ast(
    function: &Value,
) -> Result<ClangFunctionSkeleton, ClangFrontendError> {
    let name = string_field(function, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_function_decl".to_string(),
        message: "FunctionDecl is missing name".to_string(),
    })?;
    let function_type = function.get("type").ok_or_else(|| ClangFrontendError {
        kind: "invalid_function_decl".to_string(),
        message: format!("FunctionDecl {name} is missing qualType"),
    })?;
    let return_type = function_return_type_from_type_object(function_type)?;
    let children = inner(function);
    let params = children
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("ParmVarDecl"))
        .map(param_skeleton_from_ast)
        .collect::<Result<Vec<_>, ClangFrontendError>>()?;
    let compound = children
        .iter()
        .find(|child| string_field(child, "kind").as_deref() == Some("CompoundStmt"))
        .ok_or_else(|| ClangFrontendError {
            kind: "unsupported_function_body".to_string(),
            message: format!("FunctionDecl {name} does not contain a CompoundStmt body"),
        })?;
    let body = compound_body_skeleton_from_ast(compound)?;

    Ok(ClangFunctionSkeleton {
        name,
        return_type,
        params,
        body,
    })
}

#[cfg(feature = "typed-ir")]
fn param_skeleton_from_ast(param: &Value) -> Result<ClangParamSkeleton, ClangFrontendError> {
    let name = string_field(param, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_param_decl".to_string(),
        message: "ParmVarDecl is missing name".to_string(),
    })?;
    let ty = param
        .get("type")
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_param_decl".to_string(),
            message: format!("ParmVarDecl {name} is missing qualType"),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))?;

    Ok(ClangParamSkeleton { name, ty })
}

#[cfg(feature = "typed-ir")]
fn stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("DeclStmt") => decl_stmt_skeleton_from_ast(stmt),
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            assign_stmt_skeleton_from_ast(stmt)
        }
        Some("CompoundAssignOperator") => compound_assign_stmt_skeleton_from_ast(stmt),
        Some("IfStmt") => if_stmt_skeleton_from_ast(stmt),
        Some("WhileStmt") => while_stmt_skeleton_from_ast(stmt),
        Some("DoStmt") => do_stmt_skeleton_from_ast(stmt),
        Some("ForStmt") => for_stmt_skeleton_from_ast(stmt),
        Some("UnaryOperator") => inc_dec_stmt_skeleton_from_ast(stmt, "statement"),
        Some("CallExpr") => Ok(ClangStmtSkeleton::Expr {
            expr: call_stmt_expr_skeleton_from_ast(stmt)?,
        }),
        Some("ReturnStmt") => {
            let value = inner(stmt)
                .first()
                .map(value_expr_skeleton_from_ast)
                .transpose()?;
            Ok(ClangStmtSkeleton::Return { value })
        }
        Some("BreakStmt") => Ok(ClangStmtSkeleton::Break),
        Some("ContinueStmt") => Ok(ClangStmtSkeleton::Continue),
        Some("GotoStmt" | "SwitchStmt" | "LabelStmt" | "CaseStmt" | "DefaultStmt") => {
            Ok(ClangStmtSkeleton::Unsupported {
                reason: unsupported_control_flow_stmt_reason(stmt),
            })
        }
        Some(kind) => Ok(ClangStmtSkeleton::Unsupported {
            reason: unsupported_stmt_reason(stmt, kind),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_clang_stmt".to_string(),
            message: "clang statement node is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn for_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [init, condition_var, condition, step, body] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt must have init, condition variable, condition, step, and body slots"
                .to_string(),
        });
    };
    if !is_empty_ast_slot(condition_var) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt condition variable is outside the current clang lowering skeleton"
                .to_string(),
        });
    }
    let init = if is_empty_ast_slot(init) {
        Vec::new()
    } else {
        for_init_stmt_skeletons_from_ast(init)?
    };
    if is_empty_ast_slot(condition) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt without condition is outside the current clang lowering skeleton"
                .to_string(),
        });
    }
    if is_empty_ast_slot(step) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt without step is outside the current clang lowering skeleton"
                .to_string(),
        });
    }
    Ok(ClangStmtSkeleton::For {
        init,
        condition: Some(condition_expr_skeleton_from_ast(condition)?),
        step: Some(Box::new(for_step_stmt_skeleton_from_ast(step)?)),
        body: stmt_body_skeleton_from_ast(body)?,
    })
}

#[cfg(feature = "typed-ir")]
fn is_empty_ast_slot(value: &Value) -> bool {
    value.as_object().is_some_and(|object| object.is_empty())
}

#[cfg(feature = "typed-ir")]
fn for_init_stmt_skeletons_from_ast(
    stmt: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("DeclStmt") => body_stmt_skeletons_from_ast(stmt),
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            Ok(vec![assign_stmt_skeleton_from_ast(stmt)?])
        }
        Some(kind) => Ok(vec![ClangStmtSkeleton::Unsupported {
            reason: format!("ForStmt init {kind} is outside the current clang lowering skeleton"),
        }]),
        None => Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt init slot is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn for_step_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    match string_field(stmt, "kind").as_deref() {
        Some("BinaryOperator") if string_field(stmt, "opcode").as_deref() == Some("=") => {
            assign_stmt_skeleton_from_ast(stmt)
        }
        Some("CompoundAssignOperator") => compound_assign_stmt_skeleton_from_ast(stmt),
        Some("UnaryOperator") => inc_dec_for_step_skeleton_from_ast(stmt),
        Some(kind) => Ok(ClangStmtSkeleton::Unsupported {
            reason: format!("ForStmt step {kind} is outside the current clang lowering skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_for_stmt".to_string(),
            message: "ForStmt step slot is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn inc_dec_for_step_skeleton_from_ast(
    stmt: &Value,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    inc_dec_stmt_skeleton_from_ast(stmt, "ForStmt step")
}

#[cfg(feature = "typed-ir")]
fn inc_dec_stmt_skeleton_from_ast(
    stmt: &Value,
    context: &str,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let step = inc_dec_expr_skeleton_from_ast(stmt, true, false)?;
    let ClangExprSkeleton::IncDec { target, op, ty, .. } = step else {
        let reason = match step {
            ClangExprSkeleton::Unsupported { reason, .. } => reason,
            _ => format!("{context} must be an increment/decrement expression"),
        };
        return Ok(ClangStmtSkeleton::Unsupported { reason });
    };
    let target_ty = match inc_dec_assignment_target_type(target.as_ref(), context) {
        Ok(target_ty) => target_ty,
        Err(reason) => {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    }
    .clone();
    if !matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
        || !compound_assignment_types_match(&target_ty, &ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "{context} inc/dec target type {} is unsupported",
                target_ty.canonical
            ),
        });
    }
    let bin_op = match op {
        ClangIncDecOperator::Inc => ClangBinaryOperator::Add,
        ClangIncDecOperator::Dec => ClangBinaryOperator::Sub,
    };
    Ok(ClangStmtSkeleton::Assign {
        target: target.as_ref().clone(),
        value: ClangExprSkeleton::Binary {
            op: bin_op,
            lhs: target,
            rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                value: 1,
                spelling: "1".to_string(),
                ty: target_ty.clone(),
            }),
            ty: target_ty.clone(),
        },
    })
}

#[cfg(feature = "typed-ir")]
fn inc_dec_assignment_target_type<'a>(
    target: &'a ClangExprSkeleton,
    context: &str,
) -> Result<&'a ClangTypeSkeleton, String> {
    match target {
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ty),
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: true,
            ..
        } => {
            if context != "statement" {
                return Err(format!(
                    "{context} inc/dec record pointer field targets are unsupported outside standalone statements"
                ));
            }
            match base.as_ref() {
                ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                    if clang_type_is_mutable_record_pointer(base_ty) =>
                {
                    Ok(ty)
                }
                ClangExprSkeleton::DeclRef { .. } => Err(format!(
                    "{context} inc/dec record pointer field target base must be a non-const record pointer variable"
                )),
                _ => Err(format!(
                    "{context} inc/dec record pointer field target must have a direct record pointer variable base"
                )),
            }
        }
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: false,
            ..
        } => {
            if context != "statement" {
                return Err(format!(
                    "{context} inc/dec record field targets are unsupported outside standalone statements"
                ));
            }
            match base.as_ref() {
                ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                    if matches!(&base_ty.kind, ClangTypeKind::Record { .. }) =>
                {
                    Ok(ty)
                }
                ClangExprSkeleton::DeclRef { .. } => Err(format!(
                    "{context} inc/dec record field target base must be a record variable"
                )),
                _ => Err(format!(
                    "{context} inc/dec record field target must have a direct record variable base"
                )),
            }
        }
        _ => Err(format!(
            "{context} inc/dec target must be a simple variable, by-value record field, or direct mutable record pointer field"
        )),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_body_skeleton_from_ast(
    compound: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(compound, "kind").as_deref() != Some("CompoundStmt") {
        return Err(ClangFrontendError {
            kind: "invalid_compound_stmt".to_string(),
            message: "expected CompoundStmt body".to_string(),
        });
    }

    let mut body = Vec::new();
    for stmt in inner(compound) {
        body.extend(body_stmt_skeletons_from_ast(stmt)?);
    }
    Ok(body)
}

#[cfg(feature = "typed-ir")]
fn body_stmt_skeletons_from_ast(
    stmt: &Value,
) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(stmt, "kind").as_deref() != Some("DeclStmt") {
        return Ok(vec![stmt_skeleton_from_ast(stmt)?]);
    }

    let var_decls = decl_stmt_var_decls(stmt);
    if var_decls.is_empty() {
        return Ok(vec![ClangStmtSkeleton::Unsupported {
            reason: decl_stmt_var_decl_count_reason(0),
        }]);
    }

    var_decls
        .into_iter()
        .map(var_decl_skeleton_from_ast)
        .collect()
}

#[cfg(feature = "typed-ir")]
fn stmt_body_skeleton_from_ast(body: &Value) -> Result<Vec<ClangStmtSkeleton>, ClangFrontendError> {
    if string_field(body, "kind").as_deref() == Some("CompoundStmt") {
        compound_body_skeleton_from_ast(body)
    } else {
        Ok(vec![stmt_skeleton_from_ast(body)?])
    }
}

#[cfg(feature = "typed-ir")]
fn assign_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [target, value] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_assignment_operator".to_string(),
            message: "assignment BinaryOperator must have two operands".to_string(),
        });
    };

    Ok(ClangStmtSkeleton::Assign {
        target: expr_skeleton_from_ast(target)?,
        value: value_expr_skeleton_from_ast(value)?,
    })
}

#[cfg(feature = "typed-ir")]
fn compound_assign_stmt_skeleton_from_ast(
    stmt: &Value,
) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let op = compound_assignment_operator_from_opcode(string_field(stmt, "opcode").as_deref())?;
    let result_ty = expr_type(stmt)?;
    let compute_lhs_ty = compound_assignment_type_field(stmt, "computeLHSType")?;
    let compute_result_ty = compound_assignment_type_field(stmt, "computeResultType")?;
    let children = inner(stmt);
    let [target, value] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: "CompoundAssignOperator must have two operands".to_string(),
        });
    };
    let target = expr_skeleton_from_ast(target)?;
    let target_ty = match compound_assignment_target_type(&target) {
        Ok(target_ty) => target_ty,
        Err(reason) => {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    };
    if !compound_assignment_types_match(target_ty, &result_ty) {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "compound assignment result type must match target type: target={}, result={}",
                target_ty.canonical, result_ty.canonical
            ),
        });
    }
    if !compound_assignment_integer_types_supported(target_ty, &compute_lhs_ty, &compute_result_ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "compound assignment integer promotion types are unsupported: target={}, compute_lhs={}, compute_result={}",
                target_ty.canonical, compute_lhs_ty.canonical, compute_result_ty.canonical
            ),
        });
    }
    let preserve_integral_casts = preserves_integral_operand_casts(&op);
    let value = expr_skeleton_from_ast_with_options(value, preserve_integral_casts)?;
    if compound_assignment_target_is_direct_record_field(&target) {
        if let Some(reason) = record_field_compound_assignment_value_rejection_reason(&value) {
            return Ok(ClangStmtSkeleton::Unsupported { reason });
        }
    }

    Ok(ClangStmtSkeleton::CompoundAssign {
        target,
        op,
        value,
        result_ty,
        compute_lhs_ty,
        compute_result_ty,
    })
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_type(
    target: &ClangExprSkeleton,
) -> Result<&ClangTypeSkeleton, String> {
    match target {
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ty),
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: true,
            ..
        } => match base.as_ref() {
            ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                if clang_type_is_mutable_record_pointer(base_ty) =>
            {
                Ok(ty)
            }
            ClangExprSkeleton::DeclRef { .. } => Err(
                "compound assignment arrow member target base must be a non-const record pointer variable"
                    .to_string(),
            ),
            _ => Err(
                "compound assignment arrow member target must have a direct record pointer variable base"
                    .to_string(),
            ),
        },
        ClangExprSkeleton::Member {
            base,
            ty,
            is_arrow: false,
            ..
        } => match base.as_ref() {
            ClangExprSkeleton::DeclRef { ty: base_ty, .. }
                if matches!(&base_ty.kind, ClangTypeKind::Record { .. }) =>
            {
                Ok(ty)
            }
            ClangExprSkeleton::DeclRef { .. } => Err(
                "compound assignment record field target base must be a record variable"
                    .to_string(),
            ),
            _ => Err(
                "compound assignment record field target must have a direct record variable base"
                    .to_string(),
            ),
        },
        _ => Err(
            "compound assignment target must be a simple variable or by-value record field, or direct mutable record pointer field"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_direct_record_field(target: &ClangExprSkeleton) -> bool {
    compound_assignment_target_is_by_value_record_field(target)
        || compound_assignment_target_is_mutable_record_pointer_field(target)
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_by_value_record_field(target: &ClangExprSkeleton) -> bool {
    matches!(
        target,
        ClangExprSkeleton::Member {
            base,
            is_arrow: false,
            ..
        } if matches!(
            base.as_ref(),
            ClangExprSkeleton::DeclRef {
                ty: ClangTypeSkeleton {
                    kind: ClangTypeKind::Record { .. },
                    ..
                },
                ..
            }
        )
    )
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_target_is_mutable_record_pointer_field(target: &ClangExprSkeleton) -> bool {
    matches!(
        target,
        ClangExprSkeleton::Member {
            base,
            is_arrow: true,
            ..
        } if matches!(
            base.as_ref(),
            ClangExprSkeleton::DeclRef {
                ty,
                ..
            } if clang_type_is_mutable_record_pointer(ty)
        )
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_record_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Record { .. })
    )
}

#[cfg(feature = "typed-ir")]
fn record_field_compound_assignment_value_rejection_reason(
    value: &ClangExprSkeleton,
) -> Option<String> {
    match value {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. } => {
            if matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                None
            } else {
                Some(format!(
                    "record field compound assignment RHS must be a simple integer variable, literal, or integral cast; got {}",
                    ty.spelled
                ))
            }
        }
        ClangExprSkeleton::Cast { target, expr, .. } => {
            if !matches!(&target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "record field compound assignment RHS cast target must be an integer; got {}",
                    target.spelled
                ));
            }
            record_field_compound_assignment_value_rejection_reason(expr)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "record field compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "record field compound assignment RHS must be a simple integer variable, literal, or integral cast"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_type_field(
    stmt: &Value,
    field: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    stmt.get(field)
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: format!("CompoundAssignOperator is missing {field}.qualType"),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_types_match(lhs: &ClangTypeSkeleton, rhs: &ClangTypeSkeleton) -> bool {
    lhs.canonical == rhs.canonical && lhs.kind == rhs.kind
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_integer_types_supported(
    target_ty: &ClangTypeSkeleton,
    compute_lhs_ty: &ClangTypeSkeleton,
    compute_result_ty: &ClangTypeSkeleton,
) -> bool {
    matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
        && matches!(&compute_lhs_ty.kind, ClangTypeKind::Integer { .. })
        && compound_assignment_types_match(compute_lhs_ty, compute_result_ty)
}

#[cfg(feature = "typed-ir")]
fn if_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let (condition, then_body, else_body) = match children {
        [condition, then_body] => (condition, then_body, None),
        [condition, then_body, else_body] => (condition, then_body, Some(else_body)),
        _ => {
            return Err(ClangFrontendError {
                kind: "invalid_if_stmt".to_string(),
                message: "IfStmt must have condition and then body".to_string(),
            })
        }
    };
    let else_body = match else_body {
        Some(else_body) => stmt_body_skeleton_from_ast(else_body)?,
        None => Vec::new(),
    };

    Ok(ClangStmtSkeleton::If {
        condition: condition_expr_skeleton_from_ast(condition)?,
        then_body: stmt_body_skeleton_from_ast(then_body)?,
        else_body,
    })
}

#[cfg(feature = "typed-ir")]
fn while_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [condition, body] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_while_stmt".to_string(),
            message: "WhileStmt must have condition and body".to_string(),
        });
    };
    Ok(ClangStmtSkeleton::While {
        condition: while_condition_expr_skeleton_from_ast(condition)?,
        body: stmt_body_skeleton_from_ast(body)?,
    })
}

#[cfg(feature = "typed-ir")]
fn do_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let children = inner(stmt);
    let [body, condition] = children else {
        return Err(ClangFrontendError {
            kind: "invalid_do_stmt".to_string(),
            message: "DoStmt must have body and condition".to_string(),
        });
    };
    Ok(ClangStmtSkeleton::DoWhile {
        body: stmt_body_skeleton_from_ast(body)?,
        condition: condition_expr_skeleton_from_ast(condition)?,
    })
}

#[cfg(feature = "typed-ir")]
fn unsupported_stmt_reason(stmt: &Value, kind: &str) -> String {
    match string_field(stmt, "opcode") {
        Some(opcode) => {
            format!("{kind} opcode {opcode} is outside the current clang lowering skeleton")
        }
        None => format!("{kind} is outside the current clang lowering skeleton"),
    }
}

#[cfg(feature = "typed-ir")]
fn unsupported_control_flow_stmt_reason(stmt: &Value) -> String {
    let kind = string_field(stmt, "kind").unwrap_or_else(|| "unknown".to_string());
    let mut reason =
        format!("unsupported control-flow {kind} requires structured CFG/relooper support");
    match kind.as_str() {
        "GotoStmt" => {
            if let Some(label) = inner(stmt)
                .iter()
                .find(|child| string_field(child, "kind").as_deref() == Some("LabelDecl"))
                .and_then(|child| string_field(child, "name"))
            {
                reason.push_str(&format!(" before lowering target label {label}"));
            }
        }
        "LabelStmt" => {
            if let Some(label) = string_field(stmt, "name") {
                reason.push_str(&format!(" before lowering label {label}"));
            }
        }
        "CaseStmt" => {
            if let Some(value) = inner(stmt).first().and_then(case_label_value) {
                reason.push_str(&format!(" before lowering case {value}"));
            }
        }
        _ => {}
    }
    if let Some(source_range) = clang_source_range_summary(stmt) {
        reason.push_str(&format!(" source_range={source_range}"));
    }
    reason
}

#[cfg(feature = "typed-ir")]
fn clang_source_range_summary(node: &Value) -> Option<String> {
    let (begin_node, end_node) = match node.get("range") {
        Some(range) => (range.get("begin")?, range.get("end")?),
        None => {
            let loc = node.get("loc")?;
            (loc, loc)
        }
    };
    let begin = clang_location_summary(begin_node)?;
    let end = clang_location_summary(end_node)?;
    Some(format!("{begin}-{end}"))
}

#[cfg(feature = "typed-ir")]
fn clang_location_summary(node: &Value) -> Option<String> {
    let location = node
        .get("spellingLoc")
        .or_else(|| node.get("expansionLoc"))
        .unwrap_or(node);
    let line = integer_field(location, "line")?;
    let col = integer_field(location, "col")?;
    Some(format!("{line}:{col}"))
}

#[cfg(feature = "typed-ir")]
fn case_label_value(node: &Value) -> Option<String> {
    match string_field(node, "kind").as_deref() {
        Some("IntegerLiteral") => string_field(node, "value"),
        Some("ImplicitCastExpr" | "ParenExpr") => inner(node).first().and_then(case_label_value),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn decl_stmt_skeleton_from_ast(stmt: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let var_decls = decl_stmt_var_decls(stmt);
    let [var_decl] = var_decls.as_slice() else {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: decl_stmt_var_decl_count_reason(var_decls.len()),
        });
    };
    var_decl_skeleton_from_ast(var_decl)
}

#[cfg(feature = "typed-ir")]
fn decl_stmt_var_decls(stmt: &Value) -> Vec<&Value> {
    inner(stmt)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("VarDecl"))
        .collect()
}

#[cfg(feature = "typed-ir")]
fn decl_stmt_var_decl_count_reason(count: usize) -> String {
    format!("DeclStmt with {count} VarDecl children is outside the current clang lowering skeleton")
}

#[cfg(feature = "typed-ir")]
fn var_decl_skeleton_from_ast(var_decl: &Value) -> Result<ClangStmtSkeleton, ClangFrontendError> {
    let name = string_field(var_decl, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_var_decl".to_string(),
        message: "VarDecl is missing name".to_string(),
    })?;
    let ty = var_decl
        .get("type")
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_var_decl".to_string(),
            message: format!("VarDecl {name} is missing qualType"),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))?;
    let initializer_children = inner(var_decl);
    let init = match initializer_children {
        [] if var_decl.get("init").is_none() => None,
        [] => {
            return Ok(ClangStmtSkeleton::Unsupported {
                reason: "VarDecl initializer marker without initializer child is outside the current clang lowering skeleton".to_string(),
            });
        }
        [initializer] => Some(value_expr_skeleton_from_ast(initializer)?),
        _ => {
            return Ok(ClangStmtSkeleton::Unsupported {
                reason: format!(
                    "VarDecl with {} initializer children is outside the current clang lowering skeleton",
                    initializer_children.len()
                ),
            });
        }
    };

    Ok(ClangStmtSkeleton::Decl { name, ty, init })
}

#[cfg(feature = "typed-ir")]
fn expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, false)
}

#[cfg(feature = "typed-ir")]
fn value_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, true)
}

#[cfg(feature = "typed-ir")]
fn condition_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    expr_skeleton_from_ast_with_options(expr, true)
}

#[cfg(feature = "typed-ir")]
fn while_condition_expr_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(expr, "kind").as_deref() == Some("UnaryOperator")
        && string_field(expr, "opcode").as_deref() == Some("--")
        && expr.get("isPostfix").and_then(Value::as_bool) == Some(false)
    {
        let skeleton = inc_dec_expr_skeleton_from_ast(expr, true, true)?;
        let ClangExprSkeleton::IncDec {
            target,
            op: ClangIncDecOperator::Dec,
            prefix: true,
            ty,
        } = &skeleton
        else {
            return Ok(skeleton);
        };
        let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = target.as_ref() else {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: "while prefix decrement condition must target a simple integer variable"
                    .to_string(),
            });
        };
        if !matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
            || !compound_assignment_types_match(target_ty, ty)
        {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: format!(
                    "while prefix decrement target type {} is unsupported",
                    target_ty.canonical
                ),
            });
        }
        return Ok(skeleton);
    }
    condition_expr_skeleton_from_ast(expr)
}

#[cfg(feature = "typed-ir")]
/// Converts one clang JSON expression into the conservative skeleton layer.
///
/// This is the AST semantic boundary before typed IR. It accepts only node
/// shapes whose C meaning is explicitly modeled, preserves integral casts when
/// value contexts need them, and returns `Unsupported` skeletons or structured
/// errors instead of guessing through unfamiliar clang nodes.
fn expr_skeleton_from_ast_with_options(
    expr: &Value,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    match string_field(expr, "kind").as_deref() {
        Some("ImplicitCastExpr") => {
            let cast_kind = string_field(expr, "castKind");
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_clang_expr".to_string(),
                message: "ImplicitCastExpr is missing operand".to_string(),
            })?;
            let operand = expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)?;
            if cast_kind.as_deref() == Some("FunctionToPointerDecay") {
                return Ok(ClangExprSkeleton::FunctionToPointerDecay {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                });
            }
            if cast_kind.as_deref() == Some("NullToPointer") {
                return null_pointer_skeleton_from_cast(expr, &operand, "ImplicitCastExpr");
            }
            if cast_kind.as_deref() == Some("ArrayToPointerDecay") {
                return Ok(ClangExprSkeleton::ArrayToPointerDecay {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                });
            }
            if preserve_integral_casts && is_integral_conversion_cast_expr(expr) {
                return Ok(ClangExprSkeleton::Cast {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                    implicit: true,
                });
            }
            if preserve_integral_casts && is_integer_lvalue_to_rvalue_cast_expr(expr) {
                return Ok(ClangExprSkeleton::LValueToRValue {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                });
            }
            match cast_kind.as_deref() {
                Some("LValueToRValue" | "NoOp") => Ok(operand),
                Some(cast_kind) => Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: format!(
                        "castKind {cast_kind} is outside the current clang lowering skeleton"
                    ),
                }),
                None => Ok(ClangExprSkeleton::Unsupported {
                    node: "ImplicitCastExpr".to_string(),
                    reason: "missing castKind is outside the current clang lowering skeleton"
                        .to_string(),
                }),
            }
        }
        Some("ParenExpr") => inner(expr)
            .first()
            .ok_or_else(|| ClangFrontendError {
                kind: "invalid_clang_expr".to_string(),
                message: "ParenExpr is missing operand".to_string(),
            })
            .and_then(|operand| {
                expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)
            }),
        Some("DeclRefExpr") => {
            let name = expr
                .get("referencedDecl")
                .and_then(|value| string_field(value, "name"))
                .ok_or_else(|| ClangFrontendError {
                    kind: "invalid_decl_ref_expr".to_string(),
                    message: "DeclRefExpr is missing referencedDecl.name".to_string(),
                })?;
            let ty = expr_type(expr)?;
            Ok(ClangExprSkeleton::DeclRef { name, ty })
        }
        Some("IntegerLiteral") => {
            let spelling = string_field(expr, "value").ok_or_else(|| ClangFrontendError {
                kind: "invalid_integer_literal".to_string(),
                message: "IntegerLiteral is missing value".to_string(),
            })?;
            let value = spelling
                .parse::<u64>()
                .map_err(|error| ClangFrontendError {
                    kind: "invalid_integer_literal".to_string(),
                    message: format!("IntegerLiteral value is not u64: {error}"),
                })?;
            let ty = expr_type(expr)?;
            Ok(ClangExprSkeleton::IntegerLiteral {
                value,
                spelling,
                ty,
            })
        }
        Some("UnaryExprOrTypeTraitExpr") => unary_expr_or_type_trait_skeleton_from_ast(expr),
        Some("BinaryOperator") => {
            let op = match string_field(expr, "opcode").as_deref() {
                Some("+") => ClangBinaryOperator::Add,
                Some("-") => ClangBinaryOperator::Sub,
                Some("*") => ClangBinaryOperator::Mul,
                Some("/") => ClangBinaryOperator::Div,
                Some("%") => ClangBinaryOperator::Mod,
                Some("&") => ClangBinaryOperator::BitAnd,
                Some("|") => ClangBinaryOperator::BitOr,
                Some("^") => ClangBinaryOperator::BitXor,
                Some("<<") => ClangBinaryOperator::Shl,
                Some(">>") => ClangBinaryOperator::Shr,
                Some("&&") => ClangBinaryOperator::LogAnd,
                Some("||") => ClangBinaryOperator::LogOr,
                Some("==") => ClangBinaryOperator::Eq,
                Some("!=") => ClangBinaryOperator::Neq,
                Some("<") => ClangBinaryOperator::Lt,
                Some("<=") => ClangBinaryOperator::Le,
                Some(">") => ClangBinaryOperator::Gt,
                Some(">=") => ClangBinaryOperator::Ge,
                Some(opcode) => {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "BinaryOperator".to_string(),
                        reason: format!("opcode {opcode} is outside the current skeleton"),
                    });
                }
                None => {
                    return Err(ClangFrontendError {
                        kind: "invalid_binary_operator".to_string(),
                        message: "BinaryOperator is missing opcode".to_string(),
                    });
                }
            };
            let children = inner(expr);
            let [lhs, rhs] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_binary_operator".to_string(),
                    message: "BinaryOperator must have two operands".to_string(),
                });
            };
            let preserve_operand_integral_casts =
                preserve_integral_casts || preserves_integral_operand_casts(&op);
            Ok(ClangExprSkeleton::Binary {
                op,
                lhs: Box::new(expr_skeleton_from_ast_with_options(
                    lhs,
                    preserve_operand_integral_casts,
                )?),
                rhs: Box::new(expr_skeleton_from_ast_with_options(
                    rhs,
                    preserve_operand_integral_casts,
                )?),
                ty: expr_type(expr)?,
            })
        }
        Some("ConditionalOperator") => {
            let children = inner(expr);
            let [condition, then_expr, else_expr] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_conditional_operator".to_string(),
                    message: "ConditionalOperator must have condition, then, and else operands"
                        .to_string(),
                });
            };
            Ok(ClangExprSkeleton::Conditional {
                condition: Box::new(condition_expr_skeleton_from_ast(condition)?),
                then_expr: Box::new(expr_skeleton_from_ast_with_options(then_expr, true)?),
                else_expr: Box::new(expr_skeleton_from_ast_with_options(else_expr, true)?),
                ty: expr_type(expr)?,
            })
        }
        Some("BinaryConditionalOperator") => Ok(ClangExprSkeleton::Unsupported {
            node: "BinaryConditionalOperator".to_string(),
            reason: "GNU omitted-middle conditional operator is outside the current skeleton"
                .to_string(),
        }),
        Some("ArraySubscriptExpr") => {
            let children = inner(expr);
            let [base, index] = children else {
                return Err(ClangFrontendError {
                    kind: "invalid_array_subscript_expr".to_string(),
                    message: "ArraySubscriptExpr must have base and index operands".to_string(),
                });
            };
            Ok(ClangExprSkeleton::Index {
                base: Box::new(array_subscript_base_skeleton_from_ast(
                    base,
                    preserve_integral_casts,
                )?),
                index: Box::new(expr_skeleton_from_ast_with_options(
                    index,
                    preserve_integral_casts,
                )?),
                ty: expr_type(expr)?,
            })
        }
        Some("MemberExpr") => {
            let base = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_member_expr".to_string(),
                message: "MemberExpr is missing base operand".to_string(),
            })?;
            let field = string_field(expr, "name").ok_or_else(|| ClangFrontendError {
                kind: "invalid_member_expr".to_string(),
                message: "MemberExpr is missing name".to_string(),
            })?;
            let is_arrow = expr
                .get("isArrow")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            Ok(ClangExprSkeleton::Member {
                base: Box::new(expr_skeleton_from_ast_with_options(
                    base,
                    preserve_integral_casts,
                )?),
                field,
                ty: expr_type(expr)?,
                is_arrow,
            })
        }
        Some("InitListExpr") => init_list_expr_skeleton_from_ast(expr),
        Some("ImplicitValueInitExpr") => implicit_value_init_expr_skeleton_from_ast(expr),
        Some("CallExpr") => call_expr_skeleton_from_ast(expr),
        Some("UnaryOperator") => {
            let opcode = string_field(expr, "opcode").ok_or_else(|| ClangFrontendError {
                kind: "invalid_unary_operator".to_string(),
                message: "UnaryOperator is missing opcode".to_string(),
            })?;
            if opcode == "++" || opcode == "--" {
                return inc_dec_expr_skeleton_from_ast(expr, false, preserve_integral_casts);
            }
            if opcode == "*" {
                let ptr = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_unary_operator".to_string(),
                    message: "UnaryOperator is missing operand".to_string(),
                })?;
                return Ok(ClangExprSkeleton::Deref {
                    ptr: Box::new(expr_skeleton_from_ast_with_options(
                        ptr,
                        preserve_integral_casts,
                    )?),
                    ty: expr_type(expr)?,
                });
            }
            if opcode == "&" {
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_unary_operator".to_string(),
                    message: "UnaryOperator is missing operand".to_string(),
                })?;
                return Ok(ClangExprSkeleton::AddrOf {
                    operand: Box::new(expr_skeleton_from_ast_with_options(
                        operand,
                        preserve_integral_casts,
                    )?),
                    ty: expr_type(expr)?,
                });
            }
            if opcode == "+" {
                let result_ty = expr_type(expr)?;
                if !matches!(&result_ty.kind, ClangTypeKind::Integer { .. }) {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "UnaryOperator".to_string(),
                        reason: format!(
                            "unary plus result type {} is outside the integer promotion subset",
                            result_ty.spelled
                        ),
                    });
                }
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_unary_operator".to_string(),
                    message: "UnaryOperator is missing operand".to_string(),
                })?;
                let operand = expr_skeleton_from_ast_with_options(operand, true)?;
                if let Some(operand_ty) = clang_expr_skeleton_type(&operand) {
                    if !compound_assignment_types_match(operand_ty, &result_ty) {
                        return Ok(ClangExprSkeleton::Unsupported {
                            node: "UnaryOperator".to_string(),
                            reason: format!(
                                "unary plus operand type {} must match result type {} after clang-proven integer promotion",
                                operand_ty.spelled, result_ty.spelled
                            ),
                        });
                    }
                }
                return Ok(operand);
            }

            let op = match opcode.as_str() {
                "-" => ClangUnaryOperator::Neg,
                "!" => ClangUnaryOperator::Not,
                "~" => ClangUnaryOperator::BitNot,
                opcode => {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "UnaryOperator".to_string(),
                        reason: format!("opcode {opcode} is outside the current skeleton"),
                    });
                }
            };
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_unary_operator".to_string(),
                message: "UnaryOperator is missing operand".to_string(),
            })?;
            Ok(ClangExprSkeleton::Unary {
                op,
                operand: Box::new(expr_skeleton_from_ast_with_options(
                    operand,
                    preserve_integral_casts,
                )?),
                ty: expr_type(expr)?,
            })
        }
        Some("CStyleCastExpr") => {
            if string_field(expr, "castKind").as_deref() == Some("NullToPointer") {
                let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                    kind: "invalid_cast_expr".to_string(),
                    message: "CStyleCastExpr is missing operand".to_string(),
                })?;
                let operand =
                    expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)?;
                return null_pointer_skeleton_from_cast(expr, &operand, "CStyleCastExpr");
            }
            if !matches!(
                string_field(expr, "castKind").as_deref(),
                Some("BitCast" | "IntegralCast" | "IntegralPromotion" | "NoOp")
            ) {
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "CStyleCastExpr".to_string(),
                    reason: match string_field(expr, "castKind") {
                        Some(cast_kind) => format!(
                            "castKind {cast_kind} is outside the current clang lowering skeleton"
                        ),
                        None => "missing castKind is outside the current clang lowering skeleton"
                            .to_string(),
                    },
                });
            }
            let target = expr_type(expr)?;
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_cast_expr".to_string(),
                message: "CStyleCastExpr is missing operand".to_string(),
            })?;
            Ok(ClangExprSkeleton::Cast {
                target,
                expr: Box::new(expr_skeleton_from_ast_with_options(
                    operand,
                    preserve_integral_casts,
                )?),
                implicit: false,
            })
        }
        Some(kind) => Ok(ClangExprSkeleton::Unsupported {
            node: kind.to_string(),
            reason: format!("{kind} is outside the current clang lowering skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "clang expression node is missing kind".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn unary_expr_or_type_trait_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let name = string_field(expr, "name").ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_expr_or_type_trait_expr".to_string(),
        message: "UnaryExprOrTypeTraitExpr is missing name".to_string(),
    })?;
    if name != "sizeof" && name != "_Alignof" {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryExprOrTypeTraitExpr".to_string(),
            reason: format!("{name} requires explicit alignment/lowering support"),
        });
    }
    let arg_type_object = expr.get("argType").ok_or_else(|| ClangFrontendError {
        kind: if expr.get("inner").is_some() {
            format!("unsupported_{name}_operand")
        } else {
            "invalid_unary_expr_or_type_trait_expr".to_string()
        },
        message: if expr.get("inner").is_some() {
            format!("{name} expression operand requires clang argType.qualType before typed IR lowering")
        } else {
            format!("{name} type operand is missing argType.qualType")
        },
    })?;
    if clang_type_candidate_spellings(arg_type_object)
        .iter()
        .any(|spelling| is_enum_qual_type_spelling(spelling))
    {
        let spelled = string_field(arg_type_object, "qualType")
            .or_else(|| string_field(arg_type_object, "desugaredQualType"))
            .or_else(|| string_field(arg_type_object, "canonicalQualType"))
            .unwrap_or_else(|| "enum".to_string());
        return Err(ClangFrontendError {
            kind: format!("unsupported_{name}_type"),
            message: format!(
                "{name}({spelled}) requires explicit C layout/ABI provenance before typed IR lowering"
            ),
        });
    }
    let arg_type = type_from_ast_type_object(arg_type_object, None)?;
    if !matches!(
        arg_type.kind,
        ClangTypeKind::Integer { .. }
            | ClangTypeKind::Array { .. }
            | ClangTypeKind::Pointer { .. }
            | ClangTypeKind::Unsupported { .. }
    ) {
        return Err(ClangFrontendError {
            kind: format!("unsupported_{name}_type"),
            message: format!(
                "{name}({}) requires explicit C layout/ABI provenance before typed IR lowering",
                arg_type.spelled
            ),
        });
    }
    let ty = expr_type(expr)?;
    if name == "_Alignof" {
        Ok(ClangExprSkeleton::AlignOfType {
            arg_type,
            ty,
            alignment_bits: None,
        })
    } else {
        Ok(ClangExprSkeleton::SizeOfType { arg_type, ty })
    }
}

#[cfg(feature = "typed-ir")]
fn is_enum_qual_type_spelling(qual_type: &str) -> bool {
    let mut trimmed = qual_type.trim();
    while let Some(unqualified) = trimmed.strip_prefix("const ") {
        trimmed = unqualified.trim();
    }
    trimmed
        .strip_prefix("enum ")
        .map(|name| is_simple_c_identifier(name.trim()))
        .unwrap_or(false)
}

#[cfg(feature = "typed-ir")]
fn null_pointer_skeleton_from_cast(
    expr: &Value,
    operand: &ClangExprSkeleton,
    node: &str,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let target = expr_type(expr)?;
    if !matches!(target.kind, ClangTypeKind::Pointer { .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: node.to_string(),
            reason: format!(
                "castKind NullToPointer target {} is outside the current clang lowering skeleton",
                target.spelled
            ),
        });
    }
    if !matches!(operand, ClangExprSkeleton::IntegerLiteral { value: 0, .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: node.to_string(),
            reason: "castKind NullToPointer without integer zero operand is outside the current clang lowering skeleton".to_string(),
        });
    }
    Ok(ClangExprSkeleton::NullPtr { ty: target })
}

#[cfg(feature = "typed-ir")]
fn array_subscript_base_skeleton_from_ast(
    base: &Value,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(base, "kind").as_deref() == Some("ImplicitCastExpr")
        && string_field(base, "castKind").as_deref() == Some("ArrayToPointerDecay")
    {
        let operand = inner(base).first().ok_or_else(|| ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "ArrayToPointerDecay in ArraySubscriptExpr base is missing operand"
                .to_string(),
        })?;
        return expr_skeleton_from_ast_with_options(operand, preserve_integral_casts);
    }
    expr_skeleton_from_ast_with_options(base, preserve_integral_casts)
}

#[cfg(feature = "typed-ir")]
fn init_list_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let ty = expr_type(expr)?;
    let ClangTypeKind::Array { element, len } = &ty.kind else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "initializer list type {} is outside the current clang lowering skeleton",
                ty.spelled
            ),
        });
    };
    let Some(len) = len else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason:
                "incomplete array initializer list is outside the current clang lowering skeleton"
                    .to_string(),
        });
    };
    if !matches!(&element.kind, ClangTypeKind::Integer { .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "array element type {} is outside the current clang lowering skeleton",
                element.spelled
            ),
        });
    }
    let init_children = inner(expr);
    if init_children
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("DesignatedInitExpr"))
    {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: "unexpanded DesignatedInitExpr is outside the bounded fixed-array initializer subset".to_string(),
        });
    }
    let elements = if init_children.is_empty() {
        match materialized_array_filler_elements(expr, *len)? {
            Some(elements) => elements,
            None => {
                return Ok(ClangExprSkeleton::Unsupported {
                    node: "InitListExpr".to_string(),
                    reason: format!(
                        "initializer element count 0 does not match array length {len}"
                    ),
                });
            }
        }
    } else {
        if init_children.len() != *len {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "InitListExpr".to_string(),
                reason: format!(
                    "initializer element count {} does not match array length {len}",
                    init_children.len()
                ),
            });
        }
        init_children
            .iter()
            .map(|element| expr_skeleton_from_ast_with_options(element, true))
            .collect::<Result<Vec<_>, ClangFrontendError>>()?
    };
    for (index, element) in elements.iter().enumerate() {
        if let Some(reason) = array_literal_element_rejection_reason(element) {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "InitListExpr".to_string(),
                reason: format!("initializer element {index} {reason}"),
            });
        }
    }

    Ok(ClangExprSkeleton::ArrayLiteral { elements, ty })
}

#[cfg(feature = "typed-ir")]
fn materialized_array_filler_elements(
    expr: &Value,
    len: usize,
) -> Result<Option<Vec<ClangExprSkeleton>>, ClangFrontendError> {
    let Some(filler_entries) = array_filler(expr) else {
        return Ok(None);
    };
    let Some(filler) = filler_entries.first() else {
        return Ok(Some(vec![ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: "array_filler is empty".to_string(),
        }]));
    };
    if string_field(filler, "kind").as_deref() != Some("ImplicitValueInitExpr") {
        return Ok(Some(vec![ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: "array_filler first entry is not ImplicitValueInitExpr".to_string(),
        }]));
    }
    if filler_entries.len().saturating_sub(1) > len {
        return Ok(Some(vec![ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "array_filler materializes {} elements for array length {len}",
                filler_entries.len().saturating_sub(1)
            ),
        }]));
    }

    let mut elements = filler_entries[1..]
        .iter()
        .map(|element| expr_skeleton_from_ast_with_options(element, true))
        .collect::<Result<Vec<_>, ClangFrontendError>>()?;
    while elements.len() < len {
        elements.push(expr_skeleton_from_ast_with_options(filler, true)?);
    }
    Ok(Some(elements))
}

#[cfg(feature = "typed-ir")]
fn implicit_value_init_expr_skeleton_from_ast(
    expr: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let ty = expr_type(expr)?;
    if !matches!(ty.kind, ClangTypeKind::Integer { .. }) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitValueInitExpr".to_string(),
            reason: format!(
                "zero initializer type {} is outside the bounded integer array subset",
                ty.spelled
            ),
        });
    }
    Ok(ClangExprSkeleton::IntegerLiteral {
        value: 0,
        spelling: "0".to_string(),
        ty,
    })
}

#[cfg(feature = "typed-ir")]
fn array_literal_element_rejection_reason(expr: &ClangExprSkeleton) -> Option<String> {
    match expr {
        ClangExprSkeleton::IntegerLiteral { .. } => None,
        ClangExprSkeleton::Cast { target, expr, .. } => {
            if !matches!(target.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "cast target {} is not an integer; only pure integer literal elements are supported",
                    target.spelled
                ));
            }
            array_literal_element_rejection_reason(expr)
        }
        ClangExprSkeleton::Unsupported { node, reason } => Some(format!(
            "is unsupported {node}: {reason}; only pure integer literal elements are supported"
        )),
        _ => Some(
            "uses a non-literal or side-effecting expression; only pure integer literal elements are supported"
                .to_string(),
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn inc_dec_expr_skeleton_from_ast(
    expr: &Value,
    allow_prefix: bool,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let opcode = string_field(expr, "opcode").ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_operator".to_string(),
        message: "UnaryOperator is missing opcode".to_string(),
    })?;
    let op = match opcode.as_str() {
        "++" => ClangIncDecOperator::Inc,
        "--" => ClangIncDecOperator::Dec,
        _ => {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "UnaryOperator".to_string(),
                reason: format!("opcode {opcode} is outside the current inc/dec skeleton"),
            })
        }
    };
    let Some(is_postfix) = expr.get("isPostfix").and_then(Value::as_bool) else {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryOperator".to_string(),
            reason: "inc/dec UnaryOperator is missing an explicit isPostfix flag".to_string(),
        });
    };
    if !is_postfix && !allow_prefix {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "UnaryOperator".to_string(),
            reason: format!("prefix opcode {opcode} is outside the current skeleton"),
        });
    }
    let target = inner(expr).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_unary_operator".to_string(),
        message: "UnaryOperator is missing operand".to_string(),
    })?;
    Ok(ClangExprSkeleton::IncDec {
        target: Box::new(expr_skeleton_from_ast_with_options(
            target,
            preserve_integral_casts,
        )?),
        op,
        prefix: !is_postfix,
        ty: expr_type(expr)?,
    })
}

#[cfg(feature = "typed-ir")]
fn call_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    call_expr_skeleton_from_ast_with_memory_statement_args(expr, false)
}

#[cfg(feature = "typed-ir")]
fn call_stmt_expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    call_expr_skeleton_from_ast_with_memory_statement_args(expr, true)
}

#[cfg(feature = "typed-ir")]
fn call_expr_skeleton_from_ast_with_memory_statement_args(
    expr: &Value,
    allow_memory_statement_args: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    let children = inner(expr);
    let Some((callee_node, arg_nodes)) = children.split_first() else {
        return Err(ClangFrontendError {
            kind: "invalid_call_expr".to_string(),
            message: "CallExpr is missing callee".to_string(),
        });
    };
    let callee = match direct_call_callee_name(callee_node) {
        Ok(callee) => callee,
        Err(reason) => {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "CallExpr".to_string(),
                reason,
            });
        }
    };
    let mut args = Vec::with_capacity(arg_nodes.len());
    for (index, arg_node) in arg_nodes.iter().enumerate() {
        let arg = match (allow_memory_statement_args, callee.as_str(), index) {
            (true, "memset", 0) => memory_destination_arg_skeleton_from_ast(arg_node, "memset")?,
            (true, "memcpy", 0) => memory_destination_arg_skeleton_from_ast(arg_node, "memcpy")?,
            (true, "memcpy", 1) => memcpy_source_arg_skeleton_from_ast(arg_node)?,
            _ => expr_skeleton_from_ast_with_options(arg_node, true)?,
        };
        args.push(arg);
    }
    if let Some(reason) = bounded_call_args_rejection_reason(&args) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "CallExpr".to_string(),
            reason,
        });
    }
    Ok(ClangExprSkeleton::Call {
        callee,
        args,
        ty: expr_type(expr)?,
    })
}

#[cfg(feature = "typed-ir")]
fn memory_destination_arg_skeleton_from_ast(
    arg: &Value,
    callee: &str,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(arg, "kind").as_deref() != Some("ImplicitCastExpr")
        || string_field(arg, "castKind").as_deref() != Some("BitCast")
    {
        return expr_skeleton_from_ast_with_options(arg, true);
    }

    let target = expr_type(arg)?;
    if !clang_type_is_mutable_void_pointer(&target) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "{callee} destination BitCast target {} is not mutable void *",
                target.spelled
            ),
        });
    }

    let operand = inner(arg).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_clang_expr".to_string(),
        message: "ImplicitCastExpr BitCast is missing operand".to_string(),
    })?;
    let operand = expr_skeleton_from_ast_with_options(operand, true)?;
    match &operand {
        ClangExprSkeleton::DeclRef { ty, .. }
            if clang_type_is_mutable_unsigned_8_bit_pointer(ty) =>
        {
            Ok(operand)
        }
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "{callee} destination BitCast operand {} is not mutable unsigned 8-bit pointer",
                ty.spelled
            ),
        }),
        ClangExprSkeleton::Unsupported { node, reason } => Ok(ClangExprSkeleton::Unsupported {
            node: node.clone(),
            reason: reason.clone(),
        }),
        _ => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "{callee} destination BitCast operand must be a direct pointer parameter"
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn memcpy_source_arg_skeleton_from_ast(
    arg: &Value,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    if string_field(arg, "kind").as_deref() != Some("ImplicitCastExpr")
        || string_field(arg, "castKind").as_deref() != Some("BitCast")
    {
        return expr_skeleton_from_ast_with_options(arg, true);
    }

    let target = expr_type(arg)?;
    if !clang_type_is_const_void_pointer(&target) {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "memcpy source BitCast target {} is not const void *",
                target.spelled
            ),
        });
    }

    let operand = inner(arg).first().ok_or_else(|| ClangFrontendError {
        kind: "invalid_clang_expr".to_string(),
        message: "ImplicitCastExpr BitCast is missing operand".to_string(),
    })?;
    let operand = expr_skeleton_from_ast_with_options(operand, true)?;
    match &operand {
        ClangExprSkeleton::DeclRef { ty, .. }
            if clang_type_is_readonly_unsigned_8_bit_pointer(ty) =>
        {
            Ok(operand)
        }
        ClangExprSkeleton::DeclRef { ty, .. } => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: format!(
                "memcpy source BitCast operand {} is not readonly unsigned 8-bit pointer",
                ty.spelled
            ),
        }),
        ClangExprSkeleton::Unsupported { node, reason } => Ok(ClangExprSkeleton::Unsupported {
            node: node.clone(),
            reason: reason.clone(),
        }),
        _ => Ok(ClangExprSkeleton::Unsupported {
            node: "ImplicitCastExpr".to_string(),
            reason: "memcpy source BitCast operand must be a direct pointer parameter".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_void_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee) && matches!(&pointee.kind, ClangTypeKind::Void)
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_const_void_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if clang_type_is_const(pointee) && matches!(&pointee.kind, ClangTypeKind::Void)
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_mutable_unsigned_8_bit_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if !clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { signed: false, width: 8 })
    )
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_readonly_unsigned_8_bit_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. }
            if clang_type_is_const(pointee)
                && matches!(&pointee.kind, ClangTypeKind::Integer { signed: false, width: 8 })
    )
}

#[cfg(feature = "typed-ir")]
fn direct_call_callee_name(callee: &Value) -> Result<String, String> {
    match string_field(callee, "kind").as_deref() {
        Some("ImplicitCastExpr") => {
            match string_field(callee, "castKind").as_deref() {
                Some("FunctionToPointerDecay") | Some("NoOp") => {}
                Some(cast_kind) => {
                    return Err(format!(
                        "callee castKind {cast_kind} is not a direct function identifier"
                    ));
                }
                None => {
                    return Err(
                        "callee cast without castKind is not a direct function identifier"
                            .to_string(),
                    );
                }
            }
            let operand = inner(callee).first().ok_or_else(|| {
                "callee cast without operand is not a direct function identifier".to_string()
            })?;
            direct_call_callee_name(operand)
        }
        Some("ParenExpr") => {
            let operand = inner(callee).first().ok_or_else(|| {
                "parenthesized callee without operand is not a direct function identifier"
                    .to_string()
            })?;
            direct_call_callee_name(operand)
        }
        Some("DeclRefExpr") => {
            let referenced_decl = callee
                .get("referencedDecl")
                .ok_or_else(|| "callee is not a direct function identifier".to_string())?;
            let name = string_field(referenced_decl, "name")
                .ok_or_else(|| "callee is missing referenced function name".to_string())?;
            match string_field(referenced_decl, "kind").as_deref() {
                Some("FunctionDecl") => Ok(name),
                Some("ParmVarDecl") => {
                    let ty = expr_type(callee).map_err(|error| error.message)?;
                    if clang_type_is_function_pointer(&ty) {
                        Ok(name)
                    } else {
                        Err("callee is not a direct function identifier".to_string())
                    }
                }
                _ => Err("callee is not a direct function identifier".to_string()),
            }
        }
        Some(kind) => Err(format!(
            "callee node {kind} is not a direct function identifier"
        )),
        None => Err("callee node without kind is not a direct function identifier".to_string()),
    }
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_function_pointer(ty: &ClangTypeSkeleton) -> bool {
    matches!(
        &ty.kind,
        ClangTypeKind::Pointer { pointee, .. } if matches!(pointee.kind, ClangTypeKind::Function)
    )
}

#[cfg(feature = "typed-ir")]
fn bounded_call_args_rejection_reason(args: &[ClangExprSkeleton]) -> Option<String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, ClangExprSkeleton::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Some(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    for (index, arg) in args.iter().enumerate() {
        if let Some(reason) = bounded_call_arg_rejection_reason(arg, true) {
            return Some(format!("argument {index}: {reason}"));
        }
    }
    None
}

#[cfg(feature = "typed-ir")]
fn bounded_call_arg_rejection_reason(
    expr: &ClangExprSkeleton,
    allow_immediate_nested_call: bool,
) -> Option<String> {
    match expr {
        ClangExprSkeleton::DeclRef { .. }
        | ClangExprSkeleton::IntegerLiteral { .. }
        | ClangExprSkeleton::SizeOfType { .. }
        | ClangExprSkeleton::AlignOfType { .. } => None,
        ClangExprSkeleton::NullPtr { .. } => {
            Some("call arguments cannot use null pointer value semantics".to_string())
        }
        ClangExprSkeleton::Binary { lhs, rhs, .. } => bounded_call_arg_rejection_reason(lhs, false)
            .or_else(|| bounded_call_arg_rejection_reason(rhs, false)),
        ClangExprSkeleton::Unary { operand, .. }
        | ClangExprSkeleton::Cast { expr: operand, .. }
        | ClangExprSkeleton::LValueToRValue { expr: operand, .. } => {
            bounded_call_arg_rejection_reason(operand, false)
        }
        ClangExprSkeleton::ArrayToPointerDecay { .. } => Some(
            "call arguments cannot use array-to-pointer decay before explicit lowering evidence"
                .to_string(),
        ),
        ClangExprSkeleton::FunctionToPointerDecay { .. } => None,
        ClangExprSkeleton::Conditional { .. } => {
            Some("conditional call arguments are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            bounded_call_arg_rejection_reason(base, false)
                .or_else(|| bounded_call_arg_rejection_reason(index, false))
        }
        ClangExprSkeleton::Member { .. } => {
            Some("member access call arguments are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::ArrayLiteral { .. } => {
            Some("array initializer lists are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::Call { args, ty, .. } if allow_immediate_nested_call => {
            if !matches!(&ty.kind, ClangTypeKind::Integer { .. }) {
                return Some(format!(
                    "nested call result type {} is outside the bounded call subset",
                    ty.spelled
                ));
            }
            for (index, arg) in args.iter().enumerate() {
                if let Some(reason) = bounded_call_arg_rejection_reason(arg, false) {
                    return Some(format!("nested call argument {index}: {reason}"));
                }
            }
            None
        }
        ClangExprSkeleton::Call { .. } => {
            Some("nested call expressions are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::IncDec { .. } => {
            Some("call arguments cannot use increment/decrement value semantics".to_string())
        }
        ClangExprSkeleton::Deref { .. } => {
            Some("call arguments cannot use dereference value semantics".to_string())
        }
        ClangExprSkeleton::AddrOf { .. } => None,
        ClangExprSkeleton::Unsupported { node, reason } => {
            Some(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

#[cfg(feature = "typed-ir")]
fn is_integral_conversion_cast_expr(expr: &Value) -> bool {
    match string_field(expr, "castKind").as_deref() {
        Some("IntegralCast" | "IntegralPromotion") => true,
        Some("NoOp") => is_integer_noop_cast_expr(expr),
        _ => false,
    }
}

#[cfg(feature = "typed-ir")]
fn is_integer_noop_cast_expr(expr: &Value) -> bool {
    let Ok(target) = expr_type(expr) else {
        return false;
    };
    if !matches!(target.kind, ClangTypeKind::Integer { .. }) {
        return false;
    }
    let Some(operand) = inner(expr).first() else {
        return false;
    };
    let Ok(operand_ty) = expr_type(operand) else {
        return false;
    };
    matches!(operand_ty.kind, ClangTypeKind::Integer { .. })
}

#[cfg(feature = "typed-ir")]
fn is_integer_lvalue_to_rvalue_cast_expr(expr: &Value) -> bool {
    if string_field(expr, "castKind").as_deref() != Some("LValueToRValue") {
        return false;
    }
    let Ok(target) = expr_type(expr) else {
        return false;
    };
    if !matches!(target.kind, ClangTypeKind::Integer { .. }) {
        return false;
    }
    let Some(operand) = inner(expr).first() else {
        return false;
    };
    let Ok(operand_ty) = expr_type(operand) else {
        return false;
    };
    matches!(operand_ty.kind, ClangTypeKind::Integer { .. }) && operand_ty.kind == target.kind
}

#[cfg(feature = "typed-ir")]
fn preserves_integral_operand_casts(op: &ClangBinaryOperator) -> bool {
    matches!(
        op,
        ClangBinaryOperator::Add
            | ClangBinaryOperator::Sub
            | ClangBinaryOperator::Mul
            | ClangBinaryOperator::Div
            | ClangBinaryOperator::Mod
            | ClangBinaryOperator::BitAnd
            | ClangBinaryOperator::BitOr
            | ClangBinaryOperator::BitXor
            | ClangBinaryOperator::Shl
            | ClangBinaryOperator::Shr
            | ClangBinaryOperator::LogAnd
            | ClangBinaryOperator::LogOr
            | ClangBinaryOperator::Eq
            | ClangBinaryOperator::Neq
            | ClangBinaryOperator::Lt
            | ClangBinaryOperator::Le
            | ClangBinaryOperator::Gt
            | ClangBinaryOperator::Ge
    )
}

#[cfg(feature = "typed-ir")]
fn expr_type(expr: &Value) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    expr.get("type")
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "clang expression node is missing qualType".to_string(),
        })
        .and_then(|type_object| type_from_ast_type_object(type_object, None))
}

#[cfg(feature = "typed-ir")]
fn find_function_decl<'a>(node: &'a Value, function_name: &str) -> Option<&'a Value> {
    find_function_decl_with_body(node, function_name)
        .or_else(|| find_function_decl_any(node, function_name))
}

#[cfg(feature = "typed-ir")]
fn find_function_decl_with_body<'a>(node: &'a Value, function_name: &str) -> Option<&'a Value> {
    if is_named_function_decl(node, function_name)
        && inner(node)
            .iter()
            .any(|child| string_field(child, "kind").as_deref() == Some("CompoundStmt"))
    {
        return Some(node);
    }

    inner(node)
        .iter()
        .find_map(|child| find_function_decl_with_body(child, function_name))
}

#[cfg(feature = "typed-ir")]
fn find_function_decl_any<'a>(node: &'a Value, function_name: &str) -> Option<&'a Value> {
    if is_named_function_decl(node, function_name) {
        return Some(node);
    }

    inner(node)
        .iter()
        .find_map(|child| find_function_decl_any(child, function_name))
}

#[cfg(feature = "typed-ir")]
fn is_named_function_decl(node: &Value, function_name: &str) -> bool {
    string_field(node, "kind").as_deref() == Some("FunctionDecl")
        && string_field(node, "name").as_deref() == Some(function_name)
}

#[cfg(feature = "typed-ir")]
fn function_return_type(qual_type: &str) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let Some((return_type, _)) = qual_type.split_once('(') else {
        return Err(ClangFrontendError {
            kind: "unsupported_function_type".to_string(),
            message: format!("unsupported function qualType: {qual_type}"),
        });
    };
    type_from_qual_type(return_type.trim())
}

#[cfg(feature = "typed-ir")]
fn function_return_type_from_type_object(
    type_object: &Value,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_ast_type_object_with_parser(
        type_object,
        function_return_type,
        "invalid_function_decl",
        "FunctionDecl is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
fn type_from_ast_type_object(
    type_object: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_ast_type_object_with_parser(
        type_object,
        |qual_type| type_from_qual_type_with_target_abi(qual_type, target_abi),
        "invalid_clang_type",
        "clang type object is missing qualType",
    )
}

#[cfg(feature = "typed-ir")]
fn type_from_ast_type_object_with_parser<F>(
    type_object: &Value,
    mut parse: F,
    missing_kind: &str,
    missing_message: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError>
where
    F: FnMut(&str) -> Result<ClangTypeSkeleton, ClangFrontendError>,
{
    let candidates = clang_type_candidate_spellings(type_object);
    if candidates.is_empty() {
        return Err(ClangFrontendError {
            kind: missing_kind.to_string(),
            message: missing_message.to_string(),
        });
    }

    let mut first_unsupported = None;
    let mut first_error = None;
    for candidate in candidates {
        match parse(&candidate) {
            Ok(ty) if !matches!(ty.kind, ClangTypeKind::Unsupported { .. }) => return Ok(ty),
            Ok(ty) => {
                if first_unsupported.is_none() {
                    first_unsupported = Some(ty);
                }
            }
            Err(error) => {
                if first_error.is_none() {
                    first_error = Some(error);
                }
            }
        }
    }

    if let Some(ty) = first_unsupported {
        Ok(ty)
    } else if let Some(error) = first_error {
        Err(error)
    } else {
        Err(ClangFrontendError {
            kind: missing_kind.to_string(),
            message: missing_message.to_string(),
        })
    }
}

#[cfg(feature = "typed-ir")]
fn clang_type_candidate_spellings(type_object: &Value) -> Vec<String> {
    ["qualType", "desugaredQualType", "canonicalQualType"]
        .into_iter()
        .filter_map(|field| string_field(type_object, field))
        .collect()
}

#[cfg(feature = "typed-ir")]
/// Parses clang `qualType` spelling into the frontend's narrow type skeleton.
///
/// The mapper is intentionally conservative: pointers, `const`, arrays, record
/// names, and fixed-width integer spellings are accepted; target-dependent or
/// ambiguous C spellings fail closed so the typed IR emitter never receives a
/// type whose width or layout was inferred by string guesswork.
fn type_from_qual_type(qual_type: &str) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    type_from_qual_type_with_target_abi(qual_type, None)
}

#[cfg(feature = "typed-ir")]
fn type_from_qual_type_with_target_abi(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    if let Some(function_pointer) = split_function_pointer_qual_type(trimmed) {
        let function = function_type_skeleton(function_pointer.function.trim(), target_abi)?;
        let canonical = format!("{} *", function.canonical);
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(function),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(pointer) = split_pointer_qual_type(trimmed) {
        let pointee = type_from_qual_type_with_target_abi(pointer.pointee.trim(), target_abi)?;
        let canonical = match pointer.restrict_qualifier {
            Some(qualifier) => format!("{} *{qualifier}", pointee.canonical),
            None => format!("{} *", pointee.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(pointee),
                width: target_abi.and_then(|abi| nonzero_width(abi.pointer_width)),
            },
        });
    }
    if let Some(unqualified) = trimmed.strip_prefix("const ") {
        let unqualified = type_from_qual_type_with_target_abi(unqualified.trim(), target_abi)?;
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: unqualified.canonical,
            kind: unqualified.kind,
        });
    }
    if let Some((element, len)) = split_array_qual_type(trimmed)? {
        let element = type_from_qual_type_with_target_abi(element, target_abi)?;
        let canonical = match len {
            Some(len) => format!("{}[{len}]", element.canonical),
            None => format!("{}[]", element.canonical),
        };
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical,
            kind: ClangTypeKind::Array {
                element: Box::new(element),
                len,
            },
        });
    }
    if split_function_qual_type(trimmed).is_some() {
        return function_type_skeleton(trimmed, target_abi);
    }
    if let Some(name) = trimmed.strip_prefix("struct ") {
        let name = name.trim();
        if is_simple_c_identifier(name) {
            return Ok(ClangTypeSkeleton {
                spelled: trimmed.to_string(),
                canonical: trimmed.to_string(),
                kind: ClangTypeKind::Record {
                    name: name.to_string(),
                },
            });
        }
    }

    match trimmed {
        "void" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        }),
        "int" => Ok(profile_or_default_int_type(
            "int", "int", true, 32, target_abi,
        )),
        "signed char" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "signed char".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        }),
        "int8_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int8_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 8,
            },
        }),
        "int16_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int16_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 16,
            },
        }),
        "int32_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int32_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 32,
            },
        }),
        "int64_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "int64_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 64,
            },
        }),
        "uint16_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "uint16_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 16,
            },
        }),
        "unsigned int" => Ok(profile_or_default_int_type(
            "unsigned int",
            "unsigned int",
            false,
            32,
            target_abi,
        )),
        "uint32_t" => Ok(ClangTypeSkeleton {
            spelled: qual_type.trim().to_string(),
            canonical: "uint32_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 32,
            },
        }),
        "unsigned char" | "uint8_t" => Ok(ClangTypeSkeleton {
            spelled: qual_type.trim().to_string(),
            canonical: "uint8_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 8,
            },
        }),
        "uint64_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "uint64_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        }),
        "char" | "short" | "unsigned short" | "long" | "unsigned long" | "long long"
        | "unsigned long long" | "size_t" => Ok(target_dependent_integer_type_with_profile(
            trimmed, target_abi,
        )),
        other => Ok(ClangTypeSkeleton {
            spelled: other.to_string(),
            canonical: other.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!("{other} is outside the current type skeleton"),
            },
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn profile_or_default_int_type(
    spelling: &str,
    canonical: &str,
    signed: bool,
    default_width: u16,
    target_abi: Option<&TargetAbiProfile>,
) -> ClangTypeSkeleton {
    let width = match target_abi {
        Some(abi) => match nonzero_width(abi.int_width) {
            Some(width) => width,
            None => {
                return ClangTypeSkeleton {
                    spelled: spelling.to_string(),
                    canonical: canonical.to_string(),
                    kind: ClangTypeKind::Unsupported {
                        reason: format!(
                            "{spelling} requires an explicit target ABI int_width before typed IR lowering"
                        ),
                    },
                };
            }
        },
        None => default_width,
    };

    ClangTypeSkeleton {
        spelled: spelling.to_string(),
        canonical: canonical.to_string(),
        kind: ClangTypeKind::Integer { signed, width },
    }
}

#[cfg(feature = "typed-ir")]
fn target_dependent_integer_type_with_profile(
    spelling: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> ClangTypeSkeleton {
    if let Some((signed, width)) = target_dependent_integer_width(spelling, target_abi) {
        return ClangTypeSkeleton {
            spelled: spelling.to_string(),
            canonical: spelling.to_string(),
            kind: ClangTypeKind::Integer { signed, width },
        };
    }

    ClangTypeSkeleton {
        spelled: spelling.to_string(),
        canonical: spelling.to_string(),
        kind: ClangTypeKind::Unsupported {
            reason: if target_abi.is_some() {
                format!(
                    "{spelling} requires an explicit target ABI width field before typed IR lowering"
                )
            } else {
                format!("{spelling} requires target ABI width provenance before typed IR lowering")
            },
        },
    }
}

#[cfg(feature = "typed-ir")]
fn target_dependent_integer_width(
    spelling: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<(bool, u16)> {
    let abi = target_abi?;
    match spelling {
        "char" => {
            let width = nonzero_width(abi.char_width)?;
            let signed = abi.plain_char_signed?;
            Some((signed, width))
        }
        "short" => nonzero_width(abi.short_width).map(|width| (true, width)),
        "unsigned short" => nonzero_width(abi.short_width).map(|width| (false, width)),
        "long" => nonzero_width(abi.long_width).map(|width| (true, width)),
        "unsigned long" => nonzero_width(abi.long_width).map(|width| (false, width)),
        "long long" => nonzero_width(abi.long_long_width).map(|width| (true, width)),
        "unsigned long long" => nonzero_width(abi.long_long_width).map(|width| (false, width)),
        "size_t" => nonzero_width(abi.pointer_width).map(|width| (false, width)),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn target_dependent_integer_alignment(
    spelling: &str,
    target_abi: &TargetAbiProfile,
) -> Option<u16> {
    match spelling {
        "char" | "signed char" | "unsigned char" => nonzero_width(target_abi.char_align),
        "short" | "unsigned short" => nonzero_width(target_abi.short_align),
        "int" | "unsigned int" => nonzero_width(target_abi.int_align),
        "long" | "unsigned long" => nonzero_width(target_abi.long_align),
        "long long" | "unsigned long long" => nonzero_width(target_abi.long_long_align),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn target_abi_alignment_bits_for_type(
    ty: &ClangTypeSkeleton,
    target_abi: &TargetAbiProfile,
) -> Option<u16> {
    match &ty.kind {
        ClangTypeKind::Integer { .. } => {
            target_dependent_integer_alignment(&ty.canonical, target_abi)
                .or_else(|| target_dependent_integer_alignment(&ty.spelled, target_abi))
        }
        ClangTypeKind::Pointer { .. } => nonzero_width(target_abi.pointer_align),
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn nonzero_width(width: u16) -> Option<u16> {
    if width == 0 {
        None
    } else {
        Some(width)
    }
}

#[cfg(feature = "typed-ir")]
fn bind_target_abi_to_function_skeleton(
    function: &mut ClangFunctionSkeleton,
    target_abi: &TargetAbiProfile,
) {
    bind_target_abi_to_type(&mut function.return_type, target_abi);
    for param in &mut function.params {
        bind_target_abi_to_type(&mut param.ty, target_abi);
    }
    bind_target_abi_to_stmts(&mut function.body, target_abi);
}

#[cfg(feature = "typed-ir")]
fn bind_target_abi_to_stmts(statements: &mut [ClangStmtSkeleton], target_abi: &TargetAbiProfile) {
    for statement in statements {
        bind_target_abi_to_stmt(statement, target_abi);
    }
}

#[cfg(feature = "typed-ir")]
fn bind_target_abi_to_stmt(statement: &mut ClangStmtSkeleton, target_abi: &TargetAbiProfile) {
    match statement {
        ClangStmtSkeleton::Decl { ty, init, .. } => {
            bind_target_abi_to_type(ty, target_abi);
            if let Some(init) = init {
                bind_target_abi_to_expr(init, target_abi);
            }
        }
        ClangStmtSkeleton::Assign { target, value } => {
            bind_target_abi_to_expr(target, target_abi);
            bind_target_abi_to_expr(value, target_abi);
        }
        ClangStmtSkeleton::CompoundAssign {
            target,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            ..
        } => {
            bind_target_abi_to_expr(target, target_abi);
            bind_target_abi_to_expr(value, target_abi);
            bind_target_abi_to_type(result_ty, target_abi);
            bind_target_abi_to_type(compute_lhs_ty, target_abi);
            bind_target_abi_to_type(compute_result_ty, target_abi);
        }
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => {
            bind_target_abi_to_expr(condition, target_abi);
            bind_target_abi_to_stmts(then_body, target_abi);
            bind_target_abi_to_stmts(else_body, target_abi);
        }
        ClangStmtSkeleton::While { condition, body } => {
            bind_target_abi_to_expr(condition, target_abi);
            bind_target_abi_to_stmts(body, target_abi);
        }
        ClangStmtSkeleton::DoWhile { body, condition } => {
            bind_target_abi_to_stmts(body, target_abi);
            bind_target_abi_to_expr(condition, target_abi);
        }
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => {
            bind_target_abi_to_stmts(init, target_abi);
            if let Some(condition) = condition {
                bind_target_abi_to_expr(condition, target_abi);
            }
            if let Some(step) = step {
                bind_target_abi_to_stmt(step, target_abi);
            }
            bind_target_abi_to_stmts(body, target_abi);
        }
        ClangStmtSkeleton::Return { value } => {
            if let Some(value) = value {
                bind_target_abi_to_expr(value, target_abi);
            }
        }
        ClangStmtSkeleton::Expr { expr } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangStmtSkeleton::Break
        | ClangStmtSkeleton::Continue
        | ClangStmtSkeleton::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn bind_target_abi_to_expr(expr: &mut ClangExprSkeleton, target_abi: &TargetAbiProfile) {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. }
        | ClangExprSkeleton::AlignOfType { ty, .. }
        | ClangExprSkeleton::NullPtr { ty }
        | ClangExprSkeleton::Binary { ty, .. }
        | ClangExprSkeleton::Unary { ty, .. }
        | ClangExprSkeleton::Conditional { ty, .. }
        | ClangExprSkeleton::IncDec { ty, .. }
        | ClangExprSkeleton::Deref { ty, .. }
        | ClangExprSkeleton::AddrOf { ty, .. }
        | ClangExprSkeleton::Index { ty, .. }
        | ClangExprSkeleton::ArrayLiteral { ty, .. }
        | ClangExprSkeleton::Call { ty, .. }
        | ClangExprSkeleton::Member { ty, .. } => {
            bind_target_abi_to_type(ty, target_abi);
        }
        ClangExprSkeleton::Cast { target, .. }
        | ClangExprSkeleton::LValueToRValue { target, .. }
        | ClangExprSkeleton::ArrayToPointerDecay { target, .. }
        | ClangExprSkeleton::FunctionToPointerDecay { target, .. } => {
            bind_target_abi_to_type(target, target_abi);
        }
        ClangExprSkeleton::Unsupported { .. } => {}
    }

    match expr {
        ClangExprSkeleton::Binary { lhs, rhs, .. } => {
            bind_target_abi_to_expr(lhs, target_abi);
            bind_target_abi_to_expr(rhs, target_abi);
        }
        ClangExprSkeleton::Unary { operand, .. } => {
            bind_target_abi_to_expr(operand, target_abi);
        }
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            bind_target_abi_to_expr(condition, target_abi);
            bind_target_abi_to_expr(then_expr, target_abi);
            bind_target_abi_to_expr(else_expr, target_abi);
        }
        ClangExprSkeleton::IncDec { target, .. } => {
            bind_target_abi_to_expr(target, target_abi);
        }
        ClangExprSkeleton::Deref { ptr, .. } => {
            bind_target_abi_to_expr(ptr, target_abi);
        }
        ClangExprSkeleton::AddrOf { operand, .. } => {
            bind_target_abi_to_expr(operand, target_abi);
        }
        ClangExprSkeleton::Cast { expr, .. } | ClangExprSkeleton::LValueToRValue { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::ArrayToPointerDecay { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::FunctionToPointerDecay { expr, .. } => {
            bind_target_abi_to_expr(expr, target_abi);
        }
        ClangExprSkeleton::SizeOfType { arg_type, .. } => {
            bind_target_abi_to_type(arg_type, target_abi);
        }
        ClangExprSkeleton::AlignOfType {
            arg_type,
            alignment_bits,
            ..
        } => {
            bind_target_abi_to_type(arg_type, target_abi);
            *alignment_bits = target_abi_alignment_bits_for_type(arg_type, target_abi);
        }
        ClangExprSkeleton::Index { base, index, .. } => {
            bind_target_abi_to_expr(base, target_abi);
            bind_target_abi_to_expr(index, target_abi);
        }
        ClangExprSkeleton::ArrayLiteral { elements, .. } => {
            for element in elements {
                bind_target_abi_to_expr(element, target_abi);
            }
        }
        ClangExprSkeleton::Call { args, .. } => {
            for arg in args {
                bind_target_abi_to_expr(arg, target_abi);
            }
        }
        ClangExprSkeleton::Member { base, .. } => {
            bind_target_abi_to_expr(base, target_abi);
        }
        ClangExprSkeleton::DeclRef { .. }
        | ClangExprSkeleton::IntegerLiteral { .. }
        | ClangExprSkeleton::NullPtr { .. }
        | ClangExprSkeleton::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn bind_target_abi_to_type(ty: &mut ClangTypeSkeleton, target_abi: &TargetAbiProfile) {
    if let Ok(bound) = type_from_qual_type_with_target_abi(&ty.spelled, Some(target_abi)) {
        if !matches!(bound.kind, ClangTypeKind::Unsupported { .. }) {
            *ty = bound;
        }
    }
    match &mut ty.kind {
        ClangTypeKind::Pointer { pointee, .. } => bind_target_abi_to_type(pointee, target_abi),
        ClangTypeKind::Array { element, .. } => bind_target_abi_to_type(element, target_abi),
        _ => {}
    }
}

#[cfg(feature = "typed-ir")]
struct PointerQualType<'a> {
    pointee: &'a str,
    restrict_qualifier: Option<&'static str>,
}

#[cfg(feature = "typed-ir")]
struct FunctionPointerQualType<'a> {
    function: String,
    _source: &'a str,
}

#[cfg(feature = "typed-ir")]
fn split_function_pointer_qual_type(qual_type: &str) -> Option<FunctionPointerQualType<'_>> {
    let trimmed = qual_type.trim();
    let marker = "(*";
    let marker_index = trimmed.find(marker)?;
    let suffix = &trimmed[marker_index + marker.len()..];
    let close_pointer = suffix.find(')')?;
    if !suffix[..close_pointer].trim().is_empty() {
        return None;
    }
    let params = suffix[close_pointer + 1..].trim();
    if !params.starts_with('(') || !params.ends_with(')') {
        return None;
    }
    let return_type = trimmed[..marker_index].trim();
    if return_type.is_empty() || return_type.contains('(') || return_type.contains(')') {
        return None;
    }
    Some(FunctionPointerQualType {
        function: format!("{return_type} {params}"),
        _source: trimmed,
    })
}

#[cfg(feature = "typed-ir")]
fn split_function_qual_type(qual_type: &str) -> Option<(&str, &str)> {
    let trimmed = qual_type.trim();
    let open = trimmed.find('(')?;
    if !trimmed.ends_with(')') {
        return None;
    }
    let return_type = trimmed[..open].trim();
    let params = trimmed[open + 1..trimmed.len() - 1].trim();
    if return_type.is_empty() {
        return None;
    }
    Some((return_type, params))
}

#[cfg(feature = "typed-ir")]
fn function_type_skeleton(
    qual_type: &str,
    target_abi: Option<&TargetAbiProfile>,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    let Some((return_type, _params)) = split_function_qual_type(trimmed) else {
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!("{trimmed} is outside the current function type skeleton"),
            },
        });
    };
    let return_type = type_from_qual_type_with_target_abi(return_type, target_abi)?;
    if matches!(return_type.kind, ClangTypeKind::Unsupported { .. }) {
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Unsupported {
                reason: format!(
                    "function return type {} is outside the current type skeleton",
                    return_type.spelled
                ),
            },
        });
    }
    Ok(ClangTypeSkeleton {
        spelled: trimmed.to_string(),
        canonical: trimmed.to_string(),
        kind: ClangTypeKind::Function,
    })
}

#[cfg(feature = "typed-ir")]
fn split_pointer_qual_type(qual_type: &str) -> Option<PointerQualType<'_>> {
    let trimmed = qual_type.trim();
    if let Some(pointee) = trimmed.strip_suffix('*') {
        return Some(PointerQualType {
            pointee: pointee.trim_end(),
            restrict_qualifier: None,
        });
    }

    for qualifier in ["__restrict__", "__restrict", "restrict"] {
        let Some(prefix) = trimmed.strip_suffix(qualifier) else {
            continue;
        };
        let Some(pointee) = prefix.trim_end().strip_suffix('*') else {
            continue;
        };
        return Some(PointerQualType {
            pointee: pointee.trim_end(),
            restrict_qualifier: Some(qualifier),
        });
    }

    None
}

#[cfg(feature = "typed-ir")]
fn split_array_qual_type(
    qual_type: &str,
) -> Result<Option<(&str, Option<usize>)>, ClangFrontendError> {
    let Some(prefix) = qual_type.strip_suffix(']') else {
        return Ok(None);
    };
    let Some(open_index) = prefix.rfind('[') else {
        return Ok(None);
    };
    let element = prefix[..open_index].trim();
    if element.is_empty() {
        return Ok(None);
    }
    let len_spelling = prefix[open_index + 1..].trim();
    let len = if len_spelling.is_empty() {
        None
    } else {
        Some(
            len_spelling
                .parse::<usize>()
                .map_err(|error| ClangFrontendError {
                    kind: "invalid_array_type".to_string(),
                    message: format!("array length is not usize: {error}"),
                })?,
        )
    };
    Ok(Some((element, len)))
}

#[cfg(feature = "typed-ir")]
/// Lowers an accepted statement skeleton into typed IR without choosing Rust.
///
/// Unsupported skeletons become `unsupported_clang_stmt` errors, and every
/// nested expression or body is lowered through the same fail-closed path. This
/// keeps frontend semantics separate from the later Rust emitter.
fn lower_stmt(stmt: &ClangStmtSkeleton) -> Result<IrStmt, ClangFrontendError> {
    match stmt {
        ClangStmtSkeleton::Decl { name, ty, init } => Ok(IrStmt::Decl {
            name: name.clone(),
            ty: lower_type(ty)?,
            init: init.as_ref().map(lower_expr).transpose()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Assign { target, value } => Ok(IrStmt::Assign {
            target: lower_expr(target)?,
            value: lower_expr(value)?,
            source_span: None,
        }),
        ClangStmtSkeleton::CompoundAssign {
            target,
            op,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
        } => lower_compound_assign_stmt(
            target,
            op,
            value,
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
        ),
        ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } => Ok(IrStmt::If {
            condition: lower_expr(condition)?,
            then_body: then_body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            else_body: else_body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            source_span: None,
        }),
        ClangStmtSkeleton::While { condition, body } => Ok(IrStmt::While {
            condition: lower_expr(condition)?,
            body: body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            source_span: None,
        }),
        ClangStmtSkeleton::DoWhile { body, condition } => Ok(IrStmt::DoWhile {
            body: body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            condition: lower_expr(condition)?,
            source_span: None,
        }),
        ClangStmtSkeleton::For {
            init,
            condition,
            step,
            body,
        } => Ok(IrStmt::For {
            init: init
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            condition: condition.as_ref().map(lower_expr).transpose()?,
            step: step.as_deref().map(lower_stmt).transpose()?.map(Box::new),
            body: body
                .iter()
                .map(lower_stmt)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Return { value } => Ok(IrStmt::Return {
            value: value.as_ref().map(lower_expr).transpose()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Break => Ok(IrStmt::Break { source_span: None }),
        ClangStmtSkeleton::Continue => Ok(IrStmt::Continue { source_span: None }),
        ClangStmtSkeleton::Expr { expr } => Ok(IrStmt::Expr {
            expr: lower_expr(expr)?,
            source_span: None,
        }),
        ClangStmtSkeleton::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_stmt".to_string(),
            message: reason.clone(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_compound_assign_stmt(
    target: &ClangExprSkeleton,
    op: &ClangBinaryOperator,
    value: &ClangExprSkeleton,
    result_ty: &ClangTypeSkeleton,
    compute_lhs_ty: &ClangTypeSkeleton,
    compute_result_ty: &ClangTypeSkeleton,
) -> Result<IrStmt, ClangFrontendError> {
    let target_ty = compound_assignment_target_type(target)
        .map_err(|reason| ClangFrontendError {
            kind: "unsupported_compound_assignment_target".to_string(),
            message: reason,
        })
        .and_then(lower_type)?;
    let result_ty = lower_type(result_ty)?;
    let compute_lhs_ty = lower_type(compute_lhs_ty)?;
    let compute_result_ty = lower_type(compute_result_ty)?;
    if !ir_types_match_for_clang(&target_ty, &result_ty) {
        return Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_type".to_string(),
            message: format!(
                "compound assignment result type must match target type: target={}, result={}",
                target_ty.canonical, result_ty.canonical
            ),
        });
    }
    if !ir_types_match_for_clang(&compute_lhs_ty, &compute_result_ty) {
        return Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_type".to_string(),
            message: format!(
                "compound assignment compute lhs/result types must match: compute_lhs={}, compute_result={}",
                compute_lhs_ty.canonical, compute_result_ty.canonical
            ),
        });
    }
    if compound_assignment_target_is_direct_record_field(target) {
        if let Some(reason) = record_field_compound_assignment_value_rejection_reason(value) {
            return Err(ClangFrontendError {
                kind: "unsupported_compound_assignment_value".to_string(),
                message: reason,
            });
        }
    }
    let target = lower_expr(target)?;
    let lhs = cast_ir_expr_to_type_if_needed(target.clone(), &compute_lhs_ty);
    let rhs = cast_ir_expr_to_type_if_needed(lower_expr(value)?, &compute_lhs_ty);
    let binary = IrExpr::Binary {
        op: lower_binary_operator(op),
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty: compute_lhs_ty,
        source_span: None,
    };
    let value = cast_ir_expr_to_type_if_needed(binary, &target_ty);

    Ok(IrStmt::Assign {
        target,
        value,
        source_span: None,
    })
}

#[cfg(feature = "typed-ir")]
fn cast_ir_expr_to_type_if_needed(expr: IrExpr, target: &IrType) -> IrExpr {
    if ir_expr_type_matches(&expr, target) {
        expr
    } else {
        IrExpr::Cast {
            target: target.clone(),
            expr: Box::new(expr),
            implicit: true,
            source_span: None,
        }
    }
}

#[cfg(feature = "typed-ir")]
fn ir_types_match_for_clang(lhs: &IrType, rhs: &IrType) -> bool {
    lhs.canonical == rhs.canonical && lhs.kind == rhs.kind && lhs.is_const == rhs.is_const
}

#[cfg(feature = "typed-ir")]
fn ir_expr_type_matches(expr: &IrExpr, expected: &IrType) -> bool {
    match expr {
        IrExpr::Var { ty, .. }
        | IrExpr::LitInt { ty, .. }
        | IrExpr::NullPtr { ty, .. }
        | IrExpr::Binary { ty, .. }
        | IrExpr::Unary { ty, .. }
        | IrExpr::Conditional { ty, .. }
        | IrExpr::IncDec { ty, .. }
        | IrExpr::Deref { ty, .. }
        | IrExpr::Index { ty, .. }
        | IrExpr::ArrayLiteral { ty, .. }
        | IrExpr::Call { ty, .. }
        | IrExpr::Member { ty, .. }
        | IrExpr::AddrOf { ty, .. } => ir_types_match_for_clang(ty, expected),
        IrExpr::Cast { target, .. }
        | IrExpr::LValueToRValue { target, .. }
        | IrExpr::ArrayToPointerDecay { target, .. }
        | IrExpr::FunctionToPointerDecay { target, .. } => {
            ir_types_match_for_clang(target, expected)
        }
        IrExpr::Unsupported { .. } => false,
    }
}

#[cfg(feature = "typed-ir")]
/// Lowers an accepted expression skeleton into typed IR with clang-derived type data.
///
/// The conversion preserves casts, pointer/member/index structure, and source
/// type boundaries for the emitter and validators. Unknown expression nodes are
/// rejected here rather than represented as best-effort Rust.
fn lower_expr(expr: &ClangExprSkeleton) -> Result<IrExpr, ClangFrontendError> {
    match expr {
        ClangExprSkeleton::DeclRef { name, ty } => Ok(IrExpr::Var {
            name: name.clone(),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::IntegerLiteral {
            value,
            spelling,
            ty,
        } => Ok(IrExpr::LitInt {
            value: *value,
            spelling: spelling.clone(),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::SizeOfType { arg_type, ty } => {
            let value = sizeof_type_bytes(arg_type)?;
            validate_sizeof_result_fits_type(value, ty)?;
            Ok(IrExpr::LitInt {
                value,
                spelling: value.to_string(),
                ty: lower_type(ty)?,
                source_span: None,
            })
        }
        ClangExprSkeleton::AlignOfType {
            arg_type,
            ty,
            alignment_bits,
        } => {
            let value = alignof_type_bytes(arg_type, *alignment_bits)?;
            validate_alignof_result_fits_type(value, ty)?;
            Ok(IrExpr::LitInt {
                value,
                spelling: value.to_string(),
                ty: lower_type(ty)?,
                source_span: None,
            })
        }
        ClangExprSkeleton::NullPtr { ty } => Ok(IrExpr::NullPtr {
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Binary { op, lhs, rhs, ty } => Ok(IrExpr::Binary {
            op: lower_binary_operator(op),
            lhs: Box::new(lower_expr(lhs)?),
            rhs: Box::new(lower_expr(rhs)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Unary { op, operand, ty } => Ok(IrExpr::Unary {
            op: lower_unary_operator(op),
            operand: Box::new(lower_expr(operand)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } => Ok(IrExpr::Conditional {
            condition: Box::new(lower_expr(condition)?),
            then_expr: Box::new(lower_expr(then_expr)?),
            else_expr: Box::new(lower_expr(else_expr)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::IncDec {
            target,
            op,
            prefix,
            ty,
        } => Ok(IrExpr::IncDec {
            target: Box::new(lower_expr(target)?),
            op: lower_inc_dec_operator(op),
            prefix: *prefix,
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Deref { ptr, ty } => {
            if let Some(expr) = lower_array_decay_deref_expr(ptr, ty)? {
                return Ok(expr);
            }
            Ok(IrExpr::Deref {
                ptr: Box::new(lower_expr(ptr)?),
                ty: lower_type(ty)?,
                source_span: None,
            })
        }
        ClangExprSkeleton::AddrOf { operand, ty } => Ok(IrExpr::AddrOf {
            operand: Box::new(lower_expr(operand)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } => Ok(IrExpr::Cast {
            target: lower_type(target)?,
            expr: Box::new(lower_expr(expr)?),
            implicit: *implicit,
            source_span: None,
        }),
        ClangExprSkeleton::LValueToRValue { target, expr } => Ok(IrExpr::LValueToRValue {
            target: lower_type(target)?,
            expr: Box::new(lower_expr(expr)?),
            source_span: None,
        }),
        ClangExprSkeleton::ArrayToPointerDecay { target, expr } => {
            Ok(IrExpr::ArrayToPointerDecay {
                target: lower_type(target)?,
                expr: Box::new(lower_expr(expr)?),
                source_span: None,
            })
        }
        ClangExprSkeleton::FunctionToPointerDecay { target, expr } => {
            Ok(IrExpr::FunctionToPointerDecay {
                target: lower_type(target)?,
                expr: Box::new(lower_expr(expr)?),
                source_span: None,
            })
        }
        ClangExprSkeleton::Index { base, index, ty } => Ok(IrExpr::Index {
            base: Box::new(lower_expr(base)?),
            index: Box::new(lower_expr(index)?),
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::ArrayLiteral { elements, ty } => Ok(IrExpr::ArrayLiteral {
            elements: elements
                .iter()
                .map(lower_expr)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Call { callee, args, ty } => Ok(IrExpr::Call {
            callee: callee.clone(),
            args: args
                .iter()
                .map(lower_expr)
                .collect::<Result<Vec<_>, ClangFrontendError>>()?,
            ty: lower_type(ty)?,
            source_span: None,
        }),
        ClangExprSkeleton::Member {
            base,
            field,
            ty,
            is_arrow,
        } => Ok(IrExpr::Member {
            base: Box::new(lower_expr(base)?),
            field: field.clone(),
            ty: lower_type(ty)?,
            is_arrow: *is_arrow,
            source_span: None,
        }),
        ClangExprSkeleton::Unsupported { node, reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!("{node}: {reason}"),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_array_decay_deref_expr(
    ptr: &ClangExprSkeleton,
    ty: &ClangTypeSkeleton,
) -> Result<Option<IrExpr>, ClangFrontendError> {
    if let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = ptr {
        return lower_array_decay_deref_to_index(expr, target, ty, int_zero_literal_expr());
    }

    let ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Add,
        lhs,
        rhs,
        ty: binary_ty,
    } = ptr
    else {
        return Ok(None);
    };

    let Some((target, expr, index)) = array_decay_pointer_add_parts(lhs, rhs) else {
        return Ok(None);
    };
    let index_ty = clang_expr_skeleton_type(index).ok_or_else(|| ClangFrontendError {
        kind: "unsupported_clang_expr".to_string(),
        message: "ArrayToPointerDecay pointer-add deref requires a typed integer index expression"
            .to_string(),
    })?;
    if !matches!(index_ty.kind, ClangTypeKind::Integer { .. }) {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay pointer-add deref requires integer index, got {}",
                index_ty.spelled
            ),
        });
    }

    let ClangTypeKind::Pointer { pointee, .. } = &binary_ty.kind else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay pointer-add result {} is not a pointer type",
                binary_ty.spelled
            ),
        });
    };
    let result_ty = lower_type(ty)?;
    let pointee_ty = lower_type(pointee)?;
    if result_ty != pointee_ty {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: "ArrayToPointerDecay pointer-add deref requires matching pointer pointee and result types".to_string(),
        });
    }

    lower_array_decay_deref_to_index(expr, target, ty, lower_expr(index)?)
}

#[cfg(feature = "typed-ir")]
fn array_decay_pointer_add_parts<'a>(
    lhs: &'a ClangExprSkeleton,
    rhs: &'a ClangExprSkeleton,
) -> Option<(
    &'a ClangTypeSkeleton,
    &'a ClangExprSkeleton,
    &'a ClangExprSkeleton,
)> {
    match (lhs, rhs) {
        (ClangExprSkeleton::ArrayToPointerDecay { target, expr }, index)
        | (index, ClangExprSkeleton::ArrayToPointerDecay { target, expr }) => {
            Some((target, expr, index))
        }
        _ => None,
    }
}

#[cfg(feature = "typed-ir")]
fn clang_expr_skeleton_type(expr: &ClangExprSkeleton) -> Option<&ClangTypeSkeleton> {
    match expr {
        ClangExprSkeleton::DeclRef { ty, .. }
        | ClangExprSkeleton::IntegerLiteral { ty, .. }
        | ClangExprSkeleton::SizeOfType { ty, .. }
        | ClangExprSkeleton::AlignOfType { ty, .. }
        | ClangExprSkeleton::NullPtr { ty }
        | ClangExprSkeleton::Binary { ty, .. }
        | ClangExprSkeleton::Unary { ty, .. }
        | ClangExprSkeleton::Conditional { ty, .. }
        | ClangExprSkeleton::IncDec { ty, .. }
        | ClangExprSkeleton::Deref { ty, .. }
        | ClangExprSkeleton::AddrOf { ty, .. }
        | ClangExprSkeleton::Index { ty, .. }
        | ClangExprSkeleton::ArrayLiteral { ty, .. }
        | ClangExprSkeleton::Call { ty, .. }
        | ClangExprSkeleton::Member { ty, .. } => Some(ty),
        ClangExprSkeleton::Cast { target, .. }
        | ClangExprSkeleton::LValueToRValue { target, .. }
        | ClangExprSkeleton::ArrayToPointerDecay { target, .. }
        | ClangExprSkeleton::FunctionToPointerDecay { target, .. } => Some(target),
        ClangExprSkeleton::Unsupported { .. } => None,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_array_decay_deref_to_index(
    expr: &ClangExprSkeleton,
    target: &ClangTypeSkeleton,
    ty: &ClangTypeSkeleton,
    index: IrExpr,
) -> Result<Option<IrExpr>, ClangFrontendError> {
    let ClangTypeKind::Pointer { pointee, .. } = &target.kind else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay target {} is not a pointer type",
                target.spelled
            ),
        });
    };
    let ClangExprSkeleton::DeclRef { ty: array_ty, .. } = expr else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: "ArrayToPointerDecay deref currently requires a direct fixed array DeclRef"
                .to_string(),
        });
    };
    let ClangTypeKind::Array {
        element,
        len: Some(_),
    } = &array_ty.kind
    else {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!(
                "ArrayToPointerDecay deref source {} is not a complete fixed array",
                array_ty.spelled
            ),
        });
    };
    let element_ty = lower_type(element)?;
    let pointer_pointee_ty = lower_type(pointee)?;
    let result_ty = lower_type(ty)?;
    if element_ty != pointer_pointee_ty || element_ty != result_ty {
        return Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: "ArrayToPointerDecay deref requires matching array element, pointer pointee, and result types".to_string(),
        });
    }
    Ok(Some(IrExpr::Index {
        base: Box::new(lower_expr(expr)?),
        index: Box::new(index),
        ty: result_ty,
        source_span: None,
    }))
}

#[cfg(feature = "typed-ir")]
fn int_zero_literal_expr() -> IrExpr {
    IrExpr::LitInt {
        value: 0,
        spelling: "0".to_string(),
        ty: IrType {
            spelled: "int".to_string(),
            canonical: "int".to_string(),
            kind: IrTypeKind::Integer {
                signed: true,
                width: 32,
            },
            is_const: false,
            width_bits: Some(32),
            source_span: None,
        },
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn validate_sizeof_result_fits_type(
    value: u64,
    ty: &ClangTypeSkeleton,
) -> Result<(), ClangFrontendError> {
    let ClangTypeKind::Integer {
        signed: false,
        width,
    } = ty.kind
    else {
        return Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof result type {} must be an ABI-bound unsigned integer before typed IR lowering",
                ty.spelled
            ),
        });
    };
    if width >= 64 || value < (1u64 << width) {
        Ok(())
    } else {
        Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof result {value} does not fit target result type {} width {width}",
                ty.spelled
            ),
        })
    }
}

#[cfg(feature = "typed-ir")]
fn validate_alignof_result_fits_type(
    value: u64,
    ty: &ClangTypeSkeleton,
) -> Result<(), ClangFrontendError> {
    let ClangTypeKind::Integer {
        signed: false,
        width,
    } = ty.kind
    else {
        return Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof result type {} must be an ABI-bound unsigned integer before typed IR lowering",
                ty.spelled
            ),
        });
    };
    if width >= 64 || value < (1u64 << width) {
        Ok(())
    } else {
        Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof result {value} does not fit target result type {} width {width}",
                ty.spelled
            ),
        })
    }
}

#[cfg(feature = "typed-ir")]
fn sizeof_type_bytes(ty: &ClangTypeSkeleton) -> Result<u64, ClangFrontendError> {
    match &ty.kind {
        ClangTypeKind::Integer { width, .. } if *width > 0 && *width % 8 == 0 => {
            Ok(u64::from(*width / 8))
        }
        ClangTypeKind::Integer { width, .. } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) has non-byte-addressable width {width}; typed IR lowering requires explicit target ABI provenance",
                ty.spelled
            ),
        }),
        ClangTypeKind::Array { element, len } => {
            let len = len.ok_or_else(|| ClangFrontendError {
                kind: "unsupported_sizeof_type".to_string(),
                message: format!(
                    "sizeof({}) requires a complete array bound before typed IR lowering",
                    ty.spelled
                ),
            })?;
            let len = u64::try_from(len).map_err(|_| ClangFrontendError {
                kind: "unsupported_sizeof_type".to_string(),
                message: format!(
                    "sizeof({}) array bound exceeds the current typed IR byte-size representation",
                    ty.spelled
                ),
            })?;
            let element_size = sizeof_type_bytes(element)?;
            element_size
                .checked_mul(len)
                .ok_or_else(|| ClangFrontendError {
                    kind: "unsupported_sizeof_type".to_string(),
                    message: format!(
                        "sizeof({}) overflows the current typed IR byte-size representation",
                        ty.spelled
                    ),
                })
        }
        ClangTypeKind::Pointer {
            width: Some(width), ..
        } if *width > 0 && *width % 8 == 0 => Ok(u64::from(*width / 8)),
        ClangTypeKind::Pointer {
            width: Some(width), ..
        } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) has non-byte-addressable pointer width {width}; typed IR lowering requires explicit target ABI provenance",
                ty.spelled
            ),
        }),
        ClangTypeKind::Pointer { width: None, .. } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) requires target ABI pointer-width provenance before typed IR lowering",
                ty.spelled
            ),
        }),
        ClangTypeKind::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) requires target ABI width provenance before typed IR lowering: {reason}",
                ty.spelled
            ),
        }),
        _ => Err(ClangFrontendError {
            kind: "unsupported_sizeof_type".to_string(),
            message: format!(
                "sizeof({}) requires explicit C layout/ABI provenance before typed IR lowering",
                ty.spelled
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn alignof_type_bytes(
    ty: &ClangTypeSkeleton,
    alignment_bits: Option<u16>,
) -> Result<u64, ClangFrontendError> {
    match alignment_bits {
        Some(bits) if bits > 0 && bits % 8 == 0 => Ok(u64::from(bits / 8)),
        Some(bits) => Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof({}) has non-byte-addressable alignment {bits}; typed IR lowering requires explicit target alignment provenance",
                ty.spelled
            ),
        }),
        None => Err(ClangFrontendError {
            kind: "unsupported_alignof_type".to_string(),
            message: format!(
                "_Alignof({}) requires target ABI alignment profile before typed IR lowering",
                ty.spelled
            ),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_operator_from_opcode(
    opcode: Option<&str>,
) -> Result<ClangBinaryOperator, ClangFrontendError> {
    match opcode {
        Some("+=") => Ok(ClangBinaryOperator::Add),
        Some("-=") => Ok(ClangBinaryOperator::Sub),
        Some("*=") => Ok(ClangBinaryOperator::Mul),
        Some("/=") => Ok(ClangBinaryOperator::Div),
        Some("%=") => Ok(ClangBinaryOperator::Mod),
        Some("&=") => Ok(ClangBinaryOperator::BitAnd),
        Some("|=") => Ok(ClangBinaryOperator::BitOr),
        Some("^=") => Ok(ClangBinaryOperator::BitXor),
        Some("<<=") => Ok(ClangBinaryOperator::Shl),
        Some(">>=") => Ok(ClangBinaryOperator::Shr),
        Some(opcode) => Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_operator".to_string(),
            message: format!("compound assignment opcode {opcode} is outside the current skeleton"),
        }),
        None => Err(ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: "CompoundAssignOperator is missing opcode".to_string(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_binary_operator(op: &ClangBinaryOperator) -> IrBinOp {
    match op {
        ClangBinaryOperator::Add => IrBinOp::Add,
        ClangBinaryOperator::Sub => IrBinOp::Sub,
        ClangBinaryOperator::Mul => IrBinOp::Mul,
        ClangBinaryOperator::Div => IrBinOp::Div,
        ClangBinaryOperator::Mod => IrBinOp::Mod,
        ClangBinaryOperator::BitAnd => IrBinOp::BitAnd,
        ClangBinaryOperator::BitOr => IrBinOp::BitOr,
        ClangBinaryOperator::BitXor => IrBinOp::BitXor,
        ClangBinaryOperator::Shl => IrBinOp::Shl,
        ClangBinaryOperator::Shr => IrBinOp::Shr,
        ClangBinaryOperator::LogAnd => IrBinOp::LogAnd,
        ClangBinaryOperator::LogOr => IrBinOp::LogOr,
        ClangBinaryOperator::Eq => IrBinOp::Eq,
        ClangBinaryOperator::Neq => IrBinOp::Neq,
        ClangBinaryOperator::Lt => IrBinOp::Lt,
        ClangBinaryOperator::Le => IrBinOp::Le,
        ClangBinaryOperator::Gt => IrBinOp::Gt,
        ClangBinaryOperator::Ge => IrBinOp::Ge,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_unary_operator(op: &ClangUnaryOperator) -> IrUnOp {
    match op {
        ClangUnaryOperator::Neg => IrUnOp::Neg,
        ClangUnaryOperator::Not => IrUnOp::Not,
        ClangUnaryOperator::BitNot => IrUnOp::BitNot,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_inc_dec_operator(op: &ClangIncDecOperator) -> IrIncDecOp {
    match op {
        ClangIncDecOperator::Inc => IrIncDecOp::Inc,
        ClangIncDecOperator::Dec => IrIncDecOp::Dec,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_type(ty: &ClangTypeSkeleton) -> Result<IrType, ClangFrontendError> {
    match &ty.kind {
        ClangTypeKind::Void => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Void,
            is_const: clang_type_is_const(ty),
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Integer { signed, width } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Integer {
                signed: *signed,
                width: *width,
            },
            is_const: clang_type_is_const(ty),
            width_bits: Some(*width),
            source_span: None,
        }),
        ClangTypeKind::Pointer { pointee, .. } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Pointer {
                pointee: Box::new(lower_type(pointee)?),
            },
            is_const: false,
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Array { element, len } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Array {
                element: Box::new(lower_type(element)?),
                len: *len,
            },
            is_const: clang_type_is_const(ty),
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Record { name } => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Record {
                name: name.clone(),
                fields: None,
            },
            is_const: clang_type_is_const(ty),
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Function => Ok(IrType {
            spelled: ty.spelled.clone(),
            canonical: ty.canonical.clone(),
            kind: IrTypeKind::Function,
            is_const: false,
            width_bits: None,
            source_span: None,
        }),
        ClangTypeKind::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_type".to_string(),
            message: reason.clone(),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn clang_type_is_const(ty: &ClangTypeSkeleton) -> bool {
    ty.spelled.trim_start().starts_with("const ")
}

#[cfg(feature = "typed-ir")]
fn is_simple_c_identifier(text: &str) -> bool {
    let mut chars = text.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|character| character == '_' || character.is_ascii_alphanumeric())
}

#[cfg(feature = "typed-ir")]
fn inner(node: &Value) -> &[Value] {
    node.get("inner")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

#[cfg(feature = "typed-ir")]
fn array_filler(node: &Value) -> Option<&[Value]> {
    node.get("array_filler")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
}

#[cfg(feature = "typed-ir")]
fn record_inventory_from_ast_with_target_abi(
    ast: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> BTreeMap<String, Vec<IrRecordField>> {
    let mut records = BTreeMap::new();
    collect_record_inventory_from_ast(ast, target_abi, &mut records);
    records
        .into_iter()
        .filter_map(|(name, fields)| fields.map(|fields| (name, fields)))
        .collect()
}

#[cfg(feature = "typed-ir")]
fn collect_record_inventory_from_ast(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
    records: &mut BTreeMap<String, Option<Vec<IrRecordField>>>,
) {
    if let Some((name, fields)) = record_inventory_entry_from_record_decl(node, target_abi) {
        match records.entry(name) {
            std::collections::btree_map::Entry::Vacant(entry) => {
                entry.insert(fields);
            }
            std::collections::btree_map::Entry::Occupied(mut entry) => {
                entry.insert(None);
            }
        }
    }
    for child in inner(node) {
        collect_record_inventory_from_ast(child, target_abi, records);
    }
}

#[cfg(feature = "typed-ir")]
fn record_inventory_entry_from_record_decl(
    node: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<(String, Option<Vec<IrRecordField>>)> {
    if string_field(node, "kind").as_deref() != Some("RecordDecl")
        || string_field(node, "tagUsed").as_deref() != Some("struct")
        || node.get("completeDefinition").and_then(Value::as_bool) != Some(true)
        || node.get("isImplicit").and_then(Value::as_bool) == Some(true)
    {
        return None;
    }
    let name = string_field(node, "name")?;
    if !is_simple_c_identifier(&name) {
        return None;
    }
    if inner(node)
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("PackedAttr"))
    {
        return Some((name, None));
    }

    let mut fields = Vec::new();
    for child in inner(node) {
        match string_field(child, "kind").as_deref() {
            Some("FieldDecl") => {
                let Some(field) = record_field_from_field_decl(child, target_abi) else {
                    return Some((name, None));
                };
                fields.push(field);
            }
            Some("RecordDecl") => return Some((name, None)),
            _ => {}
        }
    }
    if fields.is_empty() {
        return Some((name, None));
    }
    Some((name, Some(fields)))
}

#[cfg(feature = "typed-ir")]
fn record_field_from_field_decl(
    field: &Value,
    target_abi: Option<&TargetAbiProfile>,
) -> Option<IrRecordField> {
    if field.get("isBitfield").and_then(Value::as_bool) == Some(true) {
        return None;
    }
    if inner(field)
        .iter()
        .any(|child| string_field(child, "kind").as_deref() == Some("PackedAttr"))
    {
        return None;
    }
    let name = string_field(field, "name")?;
    if !is_simple_c_identifier(&name) {
        return None;
    }
    let type_object = field.get("type")?;
    let spellings = clang_type_candidate_spellings(type_object);
    if spellings
        .iter()
        .any(|qual_type| qual_type.split_whitespace().any(|part| part == "volatile"))
    {
        return None;
    }
    let clang_ty = type_from_ast_type_object(type_object, target_abi).ok()?;
    let ty = lower_type(&clang_ty).ok()?;
    if !matches!(ty.kind, IrTypeKind::Integer { .. }) && !is_opaque_void_pointer_ir_type(&ty) {
        return None;
    }
    Some(IrRecordField { name, ty })
}

#[cfg(feature = "typed-ir")]
fn is_opaque_void_pointer_ir_type(ty: &IrType) -> bool {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return false;
    };
    matches!(pointee.kind, IrTypeKind::Void)
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_function(
    function: &mut IrFunction,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    attach_record_inventory_to_type(&mut function.return_type, inventory);
    for param in &mut function.params {
        attach_record_inventory_to_type(&mut param.ty, inventory);
    }
    for stmt in &mut function.body {
        attach_record_inventory_to_stmt(stmt, inventory);
    }
}

#[cfg(feature = "typed-ir")]
/// Recursively attaches discovered record fields to statement-local IR types.
///
/// Clang skeleton lowering may initially carry only a record name; this pass
/// enriches matching types from the translation-unit inventory before emission.
/// It does not infer missing layouts, so absent inventory remains a later
/// fail-closed type or member-access error.
fn attach_record_inventory_to_stmt(
    stmt: &mut IrStmt,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match stmt {
        IrStmt::Decl { ty, init, .. } => {
            attach_record_inventory_to_type(ty, inventory);
            if let Some(init) = init {
                attach_record_inventory_to_expr(init, inventory);
            }
        }
        IrStmt::Assign { target, value, .. } => {
            attach_record_inventory_to_expr(target, inventory);
            attach_record_inventory_to_expr(value, inventory);
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            for stmt in then_body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
            for stmt in else_body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::While {
            condition, body, ..
        }
        | IrStmt::DoWhile {
            condition, body, ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            for stmt in body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            for stmt in init {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
            if let Some(condition) = condition {
                attach_record_inventory_to_expr(condition, inventory);
            }
            if let Some(step) = step {
                attach_record_inventory_to_stmt(step, inventory);
            }
            for stmt in body {
                attach_record_inventory_to_stmt(stmt, inventory);
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                attach_record_inventory_to_expr(value, inventory);
            }
        }
        IrStmt::Expr { expr, .. } => attach_record_inventory_to_expr(expr, inventory),
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_expr(
    expr: &mut IrExpr,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match expr {
        IrExpr::LitInt { ty, .. }
        | IrExpr::NullPtr { ty, .. }
        | IrExpr::Var { ty, .. }
        | IrExpr::Binary { ty, .. }
        | IrExpr::Unary { ty, .. }
        | IrExpr::Conditional { ty, .. }
        | IrExpr::Index { ty, .. }
        | IrExpr::ArrayLiteral { ty, .. }
        | IrExpr::Call { ty, .. }
        | IrExpr::Member { ty, .. }
        | IrExpr::IncDec { ty, .. }
        | IrExpr::Deref { ty, .. }
        | IrExpr::AddrOf { ty, .. } => attach_record_inventory_to_type(ty, inventory),
        IrExpr::Cast { target, .. }
        | IrExpr::LValueToRValue { target, .. }
        | IrExpr::ArrayToPointerDecay { target, .. }
        | IrExpr::FunctionToPointerDecay { target, .. } => {
            attach_record_inventory_to_type(target, inventory)
        }
        IrExpr::Unsupported { .. } => {}
    }

    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            attach_record_inventory_to_expr(lhs, inventory);
            attach_record_inventory_to_expr(rhs, inventory);
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::LValueToRValue { expr: operand, .. }
        | IrExpr::ArrayToPointerDecay { expr: operand, .. }
        | IrExpr::FunctionToPointerDecay { expr: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => attach_record_inventory_to_expr(operand, inventory),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            attach_record_inventory_to_expr(condition, inventory);
            attach_record_inventory_to_expr(then_expr, inventory);
            attach_record_inventory_to_expr(else_expr, inventory);
        }
        IrExpr::Index { base, index, .. } => {
            attach_record_inventory_to_expr(base, inventory);
            attach_record_inventory_to_expr(index, inventory);
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                attach_record_inventory_to_expr(element, inventory);
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                attach_record_inventory_to_expr(arg, inventory);
            }
        }
        IrExpr::Member { base, .. } => attach_record_inventory_to_expr(base, inventory),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn attach_record_inventory_to_type(
    ty: &mut IrType,
    inventory: &BTreeMap<String, Vec<IrRecordField>>,
) {
    match &mut ty.kind {
        IrTypeKind::Pointer { pointee } => attach_record_inventory_to_type(pointee, inventory),
        IrTypeKind::Array { element, .. } => attach_record_inventory_to_type(element, inventory),
        IrTypeKind::Record { name, fields } => {
            if fields.is_none() {
                if let Some(record_fields) = inventory.get(name) {
                    *fields = Some(record_fields.clone());
                }
            }
        }
        IrTypeKind::Void
        | IrTypeKind::Integer { .. }
        | IrTypeKind::Function
        | IrTypeKind::Unsupported { .. } => {}
    }
}

#[cfg(feature = "typed-ir")]
fn string_field(node: &Value, field: &str) -> Option<String> {
    node.get(field)
        .and_then(Value::as_str)
        .map(ToString::to_string)
}

#[cfg(feature = "typed-ir")]
fn integer_field(node: &Value, field: &str) -> Option<i64> {
    node.get(field).and_then(Value::as_i64)
}

#[cfg(feature = "typed-ir")]
fn normalized_report_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn normalized_path(path: &Path) -> String {
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

#[cfg(all(test, feature = "typed-ir"))]
mod tests {
    use super::*;

    fn integral_cast_condition_ast() -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralCast",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        })
    }

    fn integral_promotion_condition_ast() -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralPromotion",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "signed char" },
                    "referencedDecl": { "name": "small" }
                }
            ]
        })
    }

    fn floating_to_integral_condition_ast() -> Value {
        serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FloatingToIntegral",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "float" },
                    "referencedDecl": { "name": "flag" }
                }
            ]
        })
    }

    fn return_one_stmt_ast() -> Value {
        serde_json::json!({
            "kind": "ReturnStmt",
            "inner": [
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        })
    }

    #[test]
    fn clang_source_range_summary_falls_back_to_loc_when_range_is_missing() {
        let node = serde_json::json!({
            "kind": "GotoStmt",
            "loc": { "line": 20, "col": 7 }
        });

        assert_eq!(
            clang_source_range_summary(&node),
            Some("20:7-20:7".to_string())
        );
    }

    fn assert_unsigned_integral_condition_cast(condition: ClangExprSkeleton) {
        assert!(matches!(
            condition,
            ClangExprSkeleton::Cast {
                implicit: true,
                target: ClangTypeSkeleton {
                    kind: ClangTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    fn assert_signed_integral_condition_cast(condition: ClangExprSkeleton) {
        assert!(matches!(
            condition,
            ClangExprSkeleton::Cast {
                implicit: true,
                target: ClangTypeSkeleton {
                    kind: ClangTypeKind::Integer {
                        signed: true,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    fn assert_lvalue_to_rvalue_decl_ref(
        expr: &ClangExprSkeleton,
        expected_name: &str,
        signed: bool,
        width: u16,
    ) {
        let ClangExprSkeleton::LValueToRValue {
            target,
            expr: operand,
        } = expr
        else {
            panic!("expected LValueToRValue read of {expected_name}, got {expr:?}");
        };
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: actual_signed,
                width: actual_width
            } if actual_signed == signed && actual_width == width
        ));
        assert!(matches!(
            operand.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == expected_name
        ));
    }

    fn assert_ir_lvalue_to_rvalue_var(
        expr: &IrExpr,
        expected_name: &str,
        signed: bool,
        width: u16,
    ) {
        let IrExpr::LValueToRValue {
            target,
            expr: operand,
            ..
        } = expr
        else {
            panic!("expected LValueToRValue read of {expected_name}, got {expr:?}");
        };
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: actual_signed,
                width: actual_width
            } if actual_signed == signed && actual_width == width
        ));
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == expected_name
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_maps_comparison_opcodes() {
        let cases = [
            ("==", ClangBinaryOperator::Eq),
            ("!=", ClangBinaryOperator::Neq),
            ("<", ClangBinaryOperator::Lt),
            ("<=", ClangBinaryOperator::Le),
            (">", ClangBinaryOperator::Gt),
            (">=", ClangBinaryOperator::Ge),
        ];

        for (opcode, expected) in cases {
            let expr = serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "value" }
                    },
                    {
                        "kind": "IntegerLiteral",
                        "type": { "qualType": "int" },
                        "value": "0"
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr).expect("comparison skeleton");
            let ClangExprSkeleton::Binary { op, .. } = skeleton else {
                panic!("expected binary skeleton for {opcode}, got {skeleton:?}");
            };
            assert_eq!(op, expected);
        }
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_null_to_pointer_comparison() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "!=",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "const int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "const int *" },
                            "referencedDecl": { "name": "values" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "NullToPointer",
                    "type": { "qualType": "const int *" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "0"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("null pointer comparison skeleton");
        let ir = lower_expr(&skeleton).expect("lower null pointer comparison skeleton");

        let IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } = ir
        else {
            panic!("expected IR comparison, got {ir:?}");
        };
        assert_eq!(op, IrBinOp::Neq);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            lhs.as_ref(),
            IrExpr::Var { name, .. } if name == "values"
        ));
        assert!(matches!(
            rhs.as_ref(),
            IrExpr::NullPtr { ty, .. } if matches!(ty.kind, IrTypeKind::Pointer { .. })
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_maps_bitwise_or_and_left_shift_opcodes() {
        let cases = [
            ("|", ClangBinaryOperator::BitOr),
            ("<<", ClangBinaryOperator::Shl),
        ];

        for (opcode, expected) in cases {
            let expr = serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "unsigned int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "unsigned int" },
                        "referencedDecl": { "name": "value" }
                    },
                    {
                        "kind": "IntegerLiteral",
                        "type": { "qualType": "unsigned int" },
                        "value": "4"
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr).expect("bitwise skeleton");
            let ClangExprSkeleton::Binary { op, .. } = skeleton else {
                panic!("expected binary skeleton for {opcode}, got {skeleton:?}");
            };
            assert_eq!(op, expected);
        }
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_subtraction_integral_cast_operands() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "-",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "unsigned int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("subtraction skeleton");
        let ir = lower_expr(&skeleton).expect("lower subtraction skeleton");

        let IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } = ir
        else {
            panic!("expected IR subtraction, got {ir:?}");
        };
        assert_eq!(op, IrBinOp::Sub);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(lhs.as_ref(), "value", false, 32);
        assert!(matches!(
            rhs.as_ref(),
            IrExpr::Cast { target, .. }
                if matches!(
                    target.kind,
                    IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    }
                )
        ));
    }

    #[test]
    fn implicit_cast_with_unmodeled_cast_kind_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FloatingToIntegral",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "float" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("unmodeled implicit cast should parse as unsupported skeleton");
        let ClangExprSkeleton::Unsupported { node, reason } = &skeleton else {
            panic!("expected unsupported skeleton, got {skeleton:?}");
        };
        assert_eq!(node, "ImplicitCastExpr");
        assert!(reason.contains("FloatingToIntegral"), "{reason}");

        let error = lower_expr(&skeleton).expect_err("unsupported implicit cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("FloatingToIntegral"), "{error:?}");
    }

    #[test]
    fn implicit_cast_with_integral_to_floating_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "IntegralToFloating",
            "type": { "qualType": "float" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("non-integral implicit cast should parse as unsupported skeleton");
        let ClangExprSkeleton::Unsupported { node, reason } = &skeleton else {
            panic!("expected unsupported skeleton, got {skeleton:?}");
        };
        assert_eq!(node, "ImplicitCastExpr");
        assert!(reason.contains("IntegralToFloating"), "{reason}");

        let error = lower_expr(&skeleton).expect_err("unsupported implicit cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("IntegralToFloating"), "{error:?}");
    }

    #[test]
    fn implicit_cast_without_cast_kind_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr)
            .expect("implicit cast without castKind should parse as unsupported skeleton");
        let ClangExprSkeleton::Unsupported { node, reason } = &skeleton else {
            panic!("expected unsupported skeleton, got {skeleton:?}");
        };
        assert_eq!(node, "ImplicitCastExpr");
        assert!(reason.contains("missing castKind"), "{reason}");

        let error = lower_expr(&skeleton).expect_err("unsupported implicit cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("missing castKind"), "{error:?}");
    }

    #[test]
    fn implicit_cast_noop_preserves_operand() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "NoOp",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("NoOp cast should preserve operand");
        assert!(matches!(
            skeleton,
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
    }

    #[test]
    fn c_style_noop_integer_cast_preserves_explicit_cast_node() {
        let expr = serde_json::json!({
            "kind": "CStyleCastExpr",
            "castKind": "NoOp",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "uint32_t" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("C-style NoOp cast skeleton");
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = &skeleton
        else {
            panic!("expected explicit C-style NoOp cast, got {skeleton:?}");
        };

        assert!(!implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_assignment_rhs_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "=",
            "type": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned int" },
                    "referencedDecl": { "name": "value" }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("assignment skeleton");
        let ir = lower_stmt(&skeleton).expect("lower assignment skeleton");

        let IrStmt::Assign { value, .. } = ir else {
            panic!("expected assignment, got {ir:?}");
        };
        assert!(matches!(
            value,
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_decl_initializer_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "value",
                    "type": { "qualType": "unsigned int" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "IntegralCast",
                            "type": { "qualType": "unsigned int" },
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ir = lower_stmt(&skeleton).expect("lower decl skeleton");

        let IrStmt::Decl {
            init: Some(value), ..
        } = ir
        else {
            panic!("expected initialized decl, got {ir:?}");
        };
        assert!(matches!(
            value,
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_return_value_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "ReturnStmt",
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "unsigned int" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("return skeleton");
        let ir = lower_stmt(&skeleton).expect("lower return skeleton");

        let IrStmt::Return {
            value: Some(value), ..
        } = ir
        else {
            panic!("expected return value, got {ir:?}");
        };
        assert!(matches!(
            value,
            IrExpr::Cast {
                implicit: true,
                target: IrType {
                    kind: IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_signed_unary_minus() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "-",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("unary minus skeleton");
        let ir = lower_expr(&skeleton).expect("lower unary minus skeleton");

        let IrExpr::Unary {
            op, operand, ty, ..
        } = ir
        else {
            panic!("expected IR unary minus, got {ir:?}");
        };
        assert_eq!(op, IrUnOp::Neg);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == "value"
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_non_integer_unary_plus() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "+",
            "type": { "qualType": "float" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "float" },
                    "referencedDecl": { "name": "value" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("unary plus skeleton");

        let ClangExprSkeleton::Unsupported { node, reason } = skeleton else {
            panic!("expected non-integer unary plus to fail closed, got {skeleton:?}");
        };
        assert_eq!(node, "UnaryOperator");
        assert!(
            reason.contains("unary plus result type float is outside the integer promotion subset"),
            "{reason}"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_logical_not() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "!",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("logical not skeleton");
        let ir = lower_expr(&skeleton).expect("lower logical not skeleton");

        let IrExpr::Unary {
            op, operand, ty, ..
        } = ir
        else {
            panic!("expected IR logical not, got {ir:?}");
        };
        assert_eq!(op, IrUnOp::Not);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == "value"
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_multiplicative_integral_cast_operands() {
        for (opcode, expected_op) in [
            ("*", IrBinOp::Mul),
            ("/", IrBinOp::Div),
            ("%", IrBinOp::Mod),
        ] {
            let expr = serde_json::json!({
                "kind": "BinaryOperator",
                "opcode": opcode,
                "type": { "qualType": "unsigned int" },
                "inner": [
                    {
                        "kind": "ImplicitCastExpr",
                        "castKind": "LValueToRValue",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            {
                                "kind": "DeclRefExpr",
                                "type": { "qualType": "unsigned int" },
                                "referencedDecl": { "name": "value" }
                            }
                        ]
                    },
                    {
                        "kind": "ImplicitCastExpr",
                        "castKind": "IntegralCast",
                        "type": { "qualType": "unsigned int" },
                        "inner": [
                            {
                                "kind": "IntegerLiteral",
                                "type": { "qualType": "int" },
                                "value": "3"
                            }
                        ]
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr)
                .unwrap_or_else(|_| panic!("multiplicative skeleton for {opcode}"));
            let ir = lower_expr(&skeleton)
                .unwrap_or_else(|_| panic!("lower multiplicative skeleton for {opcode}"));

            let IrExpr::Binary {
                op, lhs, rhs, ty, ..
            } = ir
            else {
                panic!("expected IR multiplicative op for {opcode}, got {ir:?}");
            };
            assert_eq!(op, expected_op);
            assert!(matches!(
                ty.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ));
            assert_ir_lvalue_to_rvalue_var(lhs.as_ref(), "value", false, 32);
            assert!(matches!(
                rhs.as_ref(),
                IrExpr::Cast { target, .. }
                    if matches!(
                        target.kind,
                        IrTypeKind::Integer {
                            signed: false,
                            width: 32
                        }
                    )
            ));
        }
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_direct_call_expr() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "helper"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("direct call skeleton");
        let ir = lower_expr(&skeleton).expect("lower direct call skeleton");

        let IrExpr::Call {
            callee, args, ty, ..
        } = ir
        else {
            panic!("expected IR call, got {ir:?}");
        };
        assert_eq!(callee, "helper");
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        let [arg] = args.as_slice() else {
            panic!("expected one direct call argument, got {args:?}");
        };
        assert_ir_lvalue_to_rvalue_var(arg, "value", true, 32);
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_record_address_of() {
        let expr = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "&",
            "type": { "qualType": "struct fdb_blob *" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "struct fdb_blob" },
                    "referencedDecl": { "name": "blob" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("address-of skeleton");
        let ClangExprSkeleton::AddrOf { operand, ty } = &skeleton else {
            panic!("expected address-of skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "blob"
        ));
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));

        let ir = lower_expr(&skeleton).expect("lower address-of skeleton");
        let IrExpr::AddrOf { operand, ty, .. } = ir else {
            panic!("expected IR address-of expression, got {ir:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == "blob"
        ));
        let IrTypeKind::Pointer { pointee } = ty.kind else {
            panic!("expected address-of pointer type, got {ty:?}");
        };
        assert!(matches!(
            &pointee.kind,
            IrTypeKind::Record { name, .. } if name == "fdb_blob"
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_direct_call_with_record_address_arg() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(struct fdb_blob *)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (struct fdb_blob *)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "consume_blob"
                            }
                        }
                    ]
                },
                {
                    "kind": "UnaryOperator",
                    "opcode": "&",
                    "type": { "qualType": "struct fdb_blob *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct fdb_blob" },
                            "referencedDecl": { "name": "blob" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("direct address call skeleton");
        let ClangExprSkeleton::Call { callee, args, .. } = &skeleton else {
            panic!("expected direct call skeleton, got {skeleton:?}");
        };
        assert_eq!(callee, "consume_blob");
        let [ClangExprSkeleton::AddrOf { operand, .. }] = args.as_slice() else {
            panic!("expected address-of call arg, got {args:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "blob"
        ));

        let ir = lower_expr(&skeleton).expect("lower direct address call skeleton");
        let IrExpr::Call { callee, args, .. } = ir else {
            panic!("expected IR direct call, got {ir:?}");
        };
        assert_eq!(callee, "consume_blob");
        let [IrExpr::AddrOf { operand, .. }] = args.as_slice() else {
            panic!("expected IR address-of call arg, got {args:?}");
        };
        assert!(matches!(
            operand.as_ref(),
            IrExpr::Var { name, .. } if name == "blob"
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_lowers_direct_call_expr_statement() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("direct call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower direct call statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected IR expr call statement, got {ir:?}");
        };
        assert_eq!(callee, "observe");
        let [arg] = args.as_slice() else {
            panic!("expected one direct call statement argument, got {args:?}");
        };
        assert_ir_lvalue_to_rvalue_var(arg, "value", true, 32);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_direct_call_arg_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(uint32_t)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (uint32_t)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "uint8_t" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "uint8_t" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("direct call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower direct call statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected IR expr call statement, got {ir:?}");
        };
        assert_eq!(callee, "observe");
        let [IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        }] = args.as_slice()
        else {
            panic!("expected direct call argument cast, got {args:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", false, 8);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_direct_call_arg_integral_promotion() {
        let stmt = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "void" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "void (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (int)" },
                            "referencedDecl": {
                                "kind": "FunctionDecl",
                                "name": "observe"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralPromotion",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "uint8_t" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "uint8_t" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("direct call statement skeleton");
        let ir = lower_stmt(&skeleton).expect("lower direct call statement");

        let IrStmt::Expr {
            expr: IrExpr::Call { callee, args, .. },
            ..
        } = ir
        else {
            panic!("expected IR expr call statement, got {ir:?}");
        };
        assert_eq!(callee, "observe");
        let [IrExpr::Cast {
            target,
            expr,
            implicit,
            ..
        }] = args.as_slice()
        else {
            panic!("expected direct call argument promotion, got {args:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            IrTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert_ir_lvalue_to_rvalue_var(expr.as_ref(), "value", false, 8);
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_compound_assignment_integer_promotion() {
        let stmt = serde_json::json!({
            "kind": "CompoundAssignOperator",
            "opcode": "+=",
            "type": { "qualType": "unsigned char" },
            "computeLHSType": { "qualType": "int" },
            "computeResultType": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned char" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "x"
                    }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "y"
                            }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("compound assignment skeleton");

        let ClangStmtSkeleton::CompoundAssign {
            result_ty,
            compute_lhs_ty,
            compute_result_ty,
            value,
            ..
        } = skeleton
        else {
            panic!("expected promoted compound assignment skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            result_ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 8
            }
        ));
        assert!(matches!(
            compute_lhs_ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert_eq!(compute_lhs_ty, compute_result_ty);
        assert_lvalue_to_rvalue_decl_ref(&value, "y", true, 32);
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_inc_dec_statement_as_assignment() {
        for (case_name, opcode, is_postfix, expected_op) in [
            ("postfix increment", "++", true, ClangBinaryOperator::Add),
            ("prefix increment", "++", false, ClangBinaryOperator::Add),
            ("postfix decrement", "--", true, ClangBinaryOperator::Sub),
            ("prefix decrement", "--", false, ClangBinaryOperator::Sub),
        ] {
            let stmt = serde_json::json!({
                "kind": "UnaryOperator",
                "opcode": opcode,
                "isPostfix": is_postfix,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "value" }
                    }
                ]
            });

            let skeleton = stmt_skeleton_from_ast(&stmt).expect(case_name);
            let ClangStmtSkeleton::Assign { target, value } = skeleton else {
                panic!("{case_name}: expected assignment statement, got {skeleton:?}");
            };
            assert!(matches!(target, ClangExprSkeleton::DeclRef { name, .. } if name == "value"));
            let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
                panic!("{case_name}: expected binary assignment value, got {value:?}");
            };
            assert_eq!(op, expected_op);
            assert!(
                matches!(lhs.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "value")
            );
            assert!(matches!(
                rhs.as_ref(),
                ClangExprSkeleton::IntegerLiteral { value: 1, .. }
            ));
        }
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_record_field_inc_dec_statement_as_assignment() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("record field inc/dec skeleton");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected record field inc/dec assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: false, .. } if field == "x"),
            "expected dot-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_accepts_mutable_record_pointer_field_inc_dec_statement_as_assignment()
    {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("record arrow inc/dec skeleton");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected arrow field inc/dec assignment, got {skeleton:?}");
        };
        assert!(
            matches!(&target, ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field assignment target, got {target:?}"
        );
        let ClangExprSkeleton::Binary { op, lhs, rhs, .. } = value else {
            panic!("expected binary assignment value, got {value:?}");
        };
        assert_eq!(op, ClangBinaryOperator::Add);
        assert!(
            matches!(lhs.as_ref(), ClangExprSkeleton::Member { field, is_arrow: true, .. } if field == "x"),
            "expected arrow-field binary lhs, got {lhs:?}"
        );
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_const_record_pointer_field_inc_dec_statement() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "const struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("const arrow inc/dec skeleton");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected const arrow field inc/dec to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("non-const record pointer variable"));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_record_field_inc_dec_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton = inc_dec_for_step_skeleton_from_ast(&stmt).expect("record field for step");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected record field inc/dec for step to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("unsupported outside standalone statements"));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_record_pointer_field_inc_dec_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "struct point *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }
            ]
        });

        let skeleton =
            inc_dec_for_step_skeleton_from_ast(&stmt).expect("record pointer field for step");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected record pointer field inc/dec for step to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("unsupported outside standalone statements"));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_record_field_inc_dec_nested_base() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": true,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "MemberExpr",
                    "name": "x",
                    "isArrow": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "MemberExpr",
                            "name": "inner",
                            "isArrow": false,
                            "type": { "qualType": "struct inner" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "struct outer" },
                                    "referencedDecl": { "name": "p" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("nested record field inc/dec");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected nested record field inc/dec to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("must have a direct record variable base"));
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_compound_assignment_compute_type_mismatch() {
        let stmt = serde_json::json!({
            "kind": "CompoundAssignOperator",
            "opcode": "+=",
            "type": { "qualType": "unsigned char" },
            "computeLHSType": { "qualType": "int" },
            "computeResultType": { "qualType": "unsigned int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "unsigned char" },
                    "referencedDecl": {
                        "kind": "ParmVarDecl",
                        "name": "x"
                    }
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = stmt_skeleton_from_ast(&stmt).expect("compound assignment skeleton");

        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected compute-type mismatch to be unsupported, got {skeleton:?}");
        };
        assert!(reason.contains("compound assignment integer promotion types are unsupported"));
    }

    #[test]
    fn expr_skeleton_from_ast_lowers_function_pointer_direct_call_expr() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (*)(int)" },
                            "referencedDecl": {
                                "kind": "ParmVarDecl",
                                "name": "fp"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("function pointer call skeleton");
        let lowered =
            lower_expr(&skeleton).expect("function pointer direct call should lower to IR call");

        let IrExpr::Call {
            callee, args, ty, ..
        } = lowered
        else {
            panic!("expected function pointer direct call IR, got {lowered:?}");
        };
        assert_eq!(callee, "fp");
        assert_eq!(ty.spelled, "int");
        assert_eq!(args.len(), 1);
        assert!(matches!(args[0], IrExpr::LValueToRValue { .. }));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_function_to_pointer_decay_as_explicit_ir() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "FunctionToPointerDecay",
            "type": { "qualType": "int (*)(int)" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int (int)" },
                    "referencedDecl": {
                        "kind": "FunctionDecl",
                        "name": "helper"
                    }
                }
            ]
        });

        let skeleton =
            expr_skeleton_from_ast(&expr).expect("function-to-pointer decay value skeleton");

        let lowered =
            lower_expr(&skeleton).expect("function-to-pointer decay should lower to explicit IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize function-to-pointer decay IR");
        let Some(decay) = lowered_json.get("FunctionToPointerDecay") else {
            panic!("expected FunctionToPointerDecay IR node, got {lowered_json}");
        };
        assert_eq!(decay["target"]["spelled"], "int (*)(int)");
        assert_eq!(decay["expr"]["Var"]["name"], "helper");
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_call_expr_without_referenced_decl_kind() {
        let expr = serde_json::json!({
            "kind": "CallExpr",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "FunctionToPointerDecay",
                    "type": { "qualType": "int (*)(int)" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int (int)" },
                            "referencedDecl": {
                                "name": "helper"
                            }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("kindless call skeleton");
        assert!(matches!(
            skeleton,
            ClangExprSkeleton::Unsupported { ref node, .. } if node == "CallExpr"
        ));
        let error = lower_expr(&skeleton).expect_err("kindless callee must fail closed");
        assert!(error
            .message
            .contains("callee is not a direct function identifier"));
    }

    #[test]
    fn expr_skeleton_from_ast_maps_integer_conditional_operator() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "flag" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "left" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "right" }
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        } = skeleton
        else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert_lvalue_to_rvalue_decl_ref(condition.as_ref(), "flag", true, 32);
        assert_lvalue_to_rvalue_decl_ref(then_expr.as_ref(), "left", true, 32);
        assert_lvalue_to_rvalue_decl_ref(else_expr.as_ref(), "right", true, 32);
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));

        let ir = lower_expr(&ClangExprSkeleton::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
        })
        .expect("lower conditional skeleton");
        assert!(matches!(
            ir,
            IrExpr::Conditional {
                ty: IrType {
                    kind: IrTypeKind::Integer {
                        signed: true,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_conditional_branch_integral_casts() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint32_t" },
                            "referencedDecl": { "name": "flag" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint32_t" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "2"
                        }
                    ]
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { else_expr, .. } = skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            else_expr.as_ref(),
            ClangExprSkeleton::Cast {
                implicit: true,
                target: ClangTypeSkeleton {
                    kind: ClangTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_conditional_condition_integral_cast() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                integral_cast_condition_ast(),
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { condition, .. } = skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(*condition);
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_conditional_condition_integral_promotion() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                integral_promotion_condition_ast(),
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { condition, .. } = skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert_signed_integral_condition_cast(*condition);
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_conditional_condition_non_integer_implicit_cast() {
        let expr = serde_json::json!({
            "kind": "ConditionalOperator",
            "type": { "qualType": "int" },
            "inner": [
                floating_to_integral_condition_ast(),
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "0"
                }
            ]
        });

        let skeleton = value_expr_skeleton_from_ast(&expr).expect("conditional skeleton");
        let ClangExprSkeleton::Conditional { condition, .. } = &skeleton else {
            panic!("expected conditional skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            condition.as_ref(),
            ClangExprSkeleton::Unsupported { node, reason }
                if node == "ImplicitCastExpr"
                    && reason.contains("FloatingToIntegral")
        ));
        let error = lower_expr(&skeleton).expect_err("non-integer condition cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
    }

    #[test]
    fn expr_skeleton_from_ast_rejects_binary_conditional_operator() {
        let expr = serde_json::json!({
            "kind": "BinaryConditionalOperator",
            "type": { "qualType": "int" },
            "inner": []
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("binary conditional skeleton");

        assert!(matches!(
            skeleton,
            ClangExprSkeleton::Unsupported { ref node, ref reason }
                if node == "BinaryConditionalOperator"
                    && reason.contains("omitted-middle conditional")
        ));
        let error = lower_expr(&skeleton).expect_err("binary conditional must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error.message.contains("BinaryConditionalOperator"));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_implicit_casts() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": ">",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "uint32_t" },
                            "referencedDecl": { "name": "value" }
                        }
                    ]
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "0"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("comparison skeleton");
        let ClangExprSkeleton::Binary { lhs, rhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::LValueToRValue {
            target: lhs_target,
            expr: lhs_expr,
        } = lhs.as_ref()
        else {
            panic!("expected preserved lhs LValueToRValue read, got {lhs:?}");
        };
        assert!(matches!(
            lhs_target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            lhs_expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = rhs.as_ref()
        else {
            panic!("expected preserved integral cast, got {rhs:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 0, .. }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_noop_cast_in_value_context() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "+",
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "NoOp",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("binary add skeleton");
        let ClangExprSkeleton::Binary { lhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = lhs.as_ref()
        else {
            panic!("expected preserved integer NoOp cast, got {lhs:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        let ClangExprSkeleton::LValueToRValue {
            target: read_target,
            expr: read_expr,
        } = expr.as_ref()
        else {
            panic!("expected preserved integer LValueToRValue read, got {expr:?}");
        };
        assert!(matches!(
            read_target.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 32
            }
        ));
        assert!(matches!(
            read_expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "value"
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_array_to_pointer_decay_as_explicit_skeleton() {
        let expr = serde_json::json!({
            "kind": "ImplicitCastExpr",
            "castKind": "ArrayToPointerDecay",
            "type": { "qualType": "int *" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int[4]" },
                    "referencedDecl": { "name": "table" }
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("array-to-pointer decay skeleton");

        let ClangExprSkeleton::ArrayToPointerDecay { target, expr } = &skeleton else {
            panic!("expected explicit array-to-pointer decay skeleton, got {skeleton:?}");
        };
        assert!(matches!(target.kind, ClangTypeKind::Pointer { .. }));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::DeclRef { name, .. } if name == "table"
        ));
        let lowered = lower_expr(&skeleton).expect("array-to-pointer decay should lower to IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize array-to-pointer decay IR");
        let Some(decay) = lowered_json.get("ArrayToPointerDecay") else {
            panic!("expected ArrayToPointerDecay IR node, got {lowered_json}");
        };
        assert_eq!(decay["target"]["spelled"], "int *");
        assert_eq!(decay["expr"]["Var"]["name"], "table");
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_array_to_pointer_decay_in_pointer_arithmetic_ir() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "+",
            "type": { "qualType": "int *" },
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "ArrayToPointerDecay",
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int[4]" },
                            "referencedDecl": { "name": "table" }
                        }
                    ]
                },
                {
                    "kind": "IntegerLiteral",
                    "type": { "qualType": "int" },
                    "value": "1"
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("array pointer arithmetic skeleton");

        let ClangExprSkeleton::Binary { lhs, rhs, .. } = &skeleton else {
            panic!("expected pointer arithmetic skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            lhs.as_ref(),
            ClangExprSkeleton::ArrayToPointerDecay { .. }
        ));
        assert!(matches!(
            rhs.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 1, .. }
        ));
        let lowered = lower_expr(&skeleton)
            .expect("array decay pointer arithmetic should lower to explicit IR");
        let lowered_json =
            serde_json::to_value(&lowered).expect("serialize array decay pointer arithmetic IR");
        assert_eq!(
            lowered_json["Binary"]["lhs"]["ArrayToPointerDecay"]["expr"]["Var"]["name"],
            "table"
        );
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_implicit_casts_for_bitwise_operands() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "&",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "uint32_t" },
                    "referencedDecl": { "name": "crc" }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "255"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("bitand skeleton");
        let ClangExprSkeleton::Binary { rhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = rhs.as_ref()
        else {
            panic!("expected preserved bitwise integral cast, got {rhs:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 255, .. }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_preserves_integer_implicit_casts_for_bitwise_or_operands() {
        let expr = serde_json::json!({
            "kind": "BinaryOperator",
            "opcode": "|",
            "type": { "qualType": "uint32_t" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "uint32_t" },
                    "referencedDecl": { "name": "value" }
                },
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "IntegralCast",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "3"
                        }
                    ]
                }
            ]
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("bitor skeleton");
        let ClangExprSkeleton::Binary { rhs, .. } = skeleton else {
            panic!("expected binary skeleton, got {skeleton:?}");
        };
        let ClangExprSkeleton::Cast {
            target,
            expr,
            implicit,
        } = rhs.as_ref()
        else {
            panic!("expected preserved bitwise-or integral cast, got {rhs:?}");
        };
        assert!(*implicit);
        assert!(matches!(
            target.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert!(matches!(
            expr.as_ref(),
            ClangExprSkeleton::IntegerLiteral { value: 3, .. }
        ));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_maps_scalar_initializer() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "next",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "uint32_t" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "uint32_t" },
                                    "referencedDecl": { "name": "crc" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            name,
            ty,
            init: Some(init),
        } = skeleton
        else {
            panic!("expected initialized decl skeleton, got {skeleton:?}");
        };
        assert_eq!(name, "next");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
        assert_lvalue_to_rvalue_decl_ref(&init, "crc", false, 32);
    }

    #[test]
    fn compound_body_skeleton_from_ast_expands_multi_var_decl_stmt() {
        let body = serde_json::json!({
            "kind": "CompoundStmt",
            "inner": [
                {
                    "kind": "DeclStmt",
                    "inner": [
                        {
                            "kind": "VarDecl",
                            "name": "a",
                            "type": { "qualType": "int" },
                            "init": "c",
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "value": "1",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        },
                        {
                            "kind": "VarDecl",
                            "name": "b",
                            "type": { "qualType": "int" },
                            "init": "c",
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "value": "2",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "ReturnStmt",
                    "inner": [
                        {
                            "kind": "BinaryOperator",
                            "opcode": "+",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "kind": "VarDecl",
                                        "name": "a",
                                        "type": { "qualType": "int" }
                                    }
                                },
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "kind": "VarDecl",
                                        "name": "b",
                                        "type": { "qualType": "int" }
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = compound_body_skeleton_from_ast(&body).expect("compound body skeleton");
        let [ClangStmtSkeleton::Decl {
            name: a_name,
            init: Some(ClangExprSkeleton::IntegerLiteral { value: a_value, .. }),
            ..
        }, ClangStmtSkeleton::Decl {
            name: b_name,
            init: Some(ClangExprSkeleton::IntegerLiteral { value: b_value, .. }),
            ..
        }, ClangStmtSkeleton::Return { value: Some(_), .. }] = skeleton.as_slice()
        else {
            panic!("expected two declarations followed by return, got {skeleton:?}");
        };

        assert_eq!(a_name, "a");
        assert_eq!(*a_value, 1);
        assert_eq!(b_name, "b");
        assert_eq!(*b_value, 2);
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_maps_fixed_array_initializer_list() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "uint32_t[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "uint32_t[3]" },
                            "inner": [
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "IntegralCast",
                                    "type": { "qualType": "uint32_t" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "1"
                                        }
                                    ]
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "3"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            name,
            ty,
            init: Some(init),
        } = skeleton
        else {
            panic!("expected initialized array decl skeleton, got {skeleton:?}");
        };
        assert_eq!(name, "table");
        assert!(matches!(ty.kind, ClangTypeKind::Array { len: Some(3), .. }));
        let ClangExprSkeleton::ArrayLiteral { elements, ty } = init else {
            panic!("expected array literal initializer, got {init:?}");
        };
        assert!(matches!(ty.kind, ClangTypeKind::Array { len: Some(3), .. }));
        assert!(matches!(
            &elements[0],
            ClangExprSkeleton::Cast {
                target,
                expr,
                implicit: true
            } if matches!(
                target.kind,
                ClangTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ) && matches!(
                expr.as_ref(),
                ClangExprSkeleton::IntegerLiteral { value: 1, .. }
            )
        ));
        assert!(matches!(
            &elements[1],
            ClangExprSkeleton::IntegerLiteral { value: 2, .. }
        ));
        assert!(matches!(
            &elements[2],
            ClangExprSkeleton::IntegerLiteral { value: 3, .. }
        ));

        let ir = lower_expr(&ClangExprSkeleton::ArrayLiteral { elements, ty })
            .expect("lower array literal initializer");
        let IrExpr::ArrayLiteral { elements, .. } = ir else {
            panic!("expected lowered IR array literal, got {ir:?}");
        };
        assert!(matches!(
            &elements[0],
            IrExpr::Cast {
                target,
                expr,
                implicit: true,
                ..
            } if matches!(
                target.kind,
                IrTypeKind::Integer {
                    signed: false,
                    width: 32
                }
            ) && matches!(
                expr.as_ref(),
                IrExpr::LitInt { value: 1, .. }
            )
        ));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_maps_sparse_array_filler_initializer() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "int" }
                                },
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "7"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            name,
            init: Some(ClangExprSkeleton::ArrayLiteral { elements, ty }),
            ..
        } = skeleton
        else {
            panic!("expected sparse array literal initializer, got {skeleton:?}");
        };
        assert_eq!(name, "table");
        assert!(matches!(ty.kind, ClangTypeKind::Array { len: Some(3), .. }));
        assert!(matches!(
            &elements[0],
            ClangExprSkeleton::IntegerLiteral { value: 0, .. }
        ));
        assert!(matches!(
            &elements[1],
            ClangExprSkeleton::IntegerLiteral { value: 7, .. }
        ));
        assert!(matches!(
            &elements[2],
            ClangExprSkeleton::IntegerLiteral { value: 0, .. }
        ));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_fixed_array_initializer_count_mismatch() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "uint32_t[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "uint32_t[3]" },
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "1"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            init: Some(ClangExprSkeleton::Unsupported { node, reason, .. }),
            ..
        } = skeleton
        else {
            panic!("expected unsupported array initializer, got {skeleton:?}");
        };
        assert_eq!(node, "InitListExpr");
        assert!(reason.contains("initializer element count 2 does not match array length 3"));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_fixed_array_initializer_call_element() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "type": { "qualType": "uint32_t[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "uint32_t[3]" },
                            "inner": [
                                {
                                    "kind": "CallExpr",
                                    "type": { "qualType": "uint32_t" },
                                    "inner": [
                                        {
                                            "kind": "ImplicitCastExpr",
                                            "castKind": "FunctionToPointerDecay",
                                            "type": { "qualType": "uint32_t (*)(void)" },
                                            "inner": [
                                                {
                                                    "kind": "DeclRefExpr",
                                                    "type": { "qualType": "uint32_t (void)" },
                                                    "referencedDecl": {
                                                        "kind": "FunctionDecl",
                                                        "name": "helper"
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "3"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Decl {
            init: Some(ClangExprSkeleton::Unsupported { node, reason, .. }),
            ..
        } = skeleton
        else {
            panic!("expected unsupported array initializer, got {skeleton:?}");
        };
        assert_eq!(node, "InitListExpr");
        assert!(reason.contains("initializer element 0"));
        assert!(reason.contains("only pure integer literal elements"));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_multiple_initializer_children() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "next",
                    "type": { "qualType": "uint32_t" },
                    "inner": [
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "1"
                        },
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "2"
                        }
                    ]
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected unsupported decl skeleton, got {skeleton:?}");
        };
        assert!(reason.contains("VarDecl with 2 initializer children"));
    }

    #[test]
    fn decl_stmt_skeleton_from_ast_rejects_init_marker_without_initializer_child() {
        let stmt = serde_json::json!({
            "kind": "DeclStmt",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "next",
                    "type": { "qualType": "uint32_t" },
                    "init": "c"
                }
            ]
        });

        let skeleton = decl_stmt_skeleton_from_ast(&stmt).expect("decl skeleton");
        let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
            panic!("expected unsupported decl skeleton, got {skeleton:?}");
        };
        assert!(reason.contains("VarDecl initializer marker without initializer child"));
    }

    #[test]
    fn if_stmt_skeleton_from_ast_maps_single_statement_bodies() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                {
                    "kind": "ImplicitCastExpr",
                    "castKind": "LValueToRValue",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "flag" }
                        }
                    ]
                },
                {
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        },
                        {
                            "kind": "BinaryOperator",
                            "opcode": "+",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "LValueToRValue",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "DeclRefExpr",
                                            "type": { "qualType": "int" },
                                            "referencedDecl": { "name": "value" }
                                        }
                                    ]
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        },
                        {
                            "kind": "BinaryOperator",
                            "opcode": "+",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "LValueToRValue",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "DeclRefExpr",
                                            "type": { "qualType": "int" },
                                            "referencedDecl": { "name": "value" }
                                        }
                                    ]
                                },
                                {
                                    "kind": "UnaryOperator",
                                    "opcode": "~",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "0"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If {
            condition,
            then_body,
            else_body,
        } = skeleton
        else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert_lvalue_to_rvalue_decl_ref(&condition, "flag", true, 32);
        assert!(matches!(
            then_body.as_slice(),
            [ClangStmtSkeleton::Assign { .. }]
        ));
        assert!(matches!(
            else_body.as_slice(),
            [ClangStmtSkeleton::Assign { .. }]
        ));
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_if_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                integral_cast_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If { condition, .. } = skeleton else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_if_condition_integral_promotion() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                integral_promotion_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If { condition, .. } = skeleton else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert_signed_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_rejects_if_condition_non_integer_implicit_cast() {
        let stmt = serde_json::json!({
            "kind": "IfStmt",
            "inner": [
                floating_to_integral_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = if_stmt_skeleton_from_ast(&stmt).expect("if skeleton");
        let ClangStmtSkeleton::If { condition, .. } = &skeleton else {
            panic!("expected if skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            condition,
            ClangExprSkeleton::Unsupported { node, reason }
                if node == "ImplicitCastExpr"
                    && reason.contains("FloatingToIntegral")
        ));
        let error =
            lower_stmt(&skeleton).expect_err("non-integer if condition cast must fail closed");
        assert_eq!(error.kind, "unsupported_clang_expr");
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_while_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "WhileStmt",
            "inner": [
                integral_cast_condition_ast(),
                return_one_stmt_ast()
            ]
        });

        let skeleton = while_stmt_skeleton_from_ast(&stmt).expect("while skeleton");
        let ClangStmtSkeleton::While { condition, .. } = skeleton else {
            panic!("expected while skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_do_while_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "DoStmt",
            "inner": [
                return_one_stmt_ast(),
                integral_cast_condition_ast()
            ]
        });

        let skeleton = do_stmt_skeleton_from_ast(&stmt).expect("do-while skeleton");
        let ClangStmtSkeleton::DoWhile { condition, .. } = skeleton else {
            panic!("expected do-while skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn stmt_skeleton_from_ast_preserves_for_condition_integral_cast() {
        let stmt = serde_json::json!({
            "kind": "ForStmt",
            "inner": [
                {
                    "kind": "DeclStmt",
                    "inner": [
                        {
                            "kind": "VarDecl",
                            "name": "i",
                            "type": { "qualType": "int" },
                            "init": "c",
                            "inner": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                },
                {},
                integral_cast_condition_ast(),
                {
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": true,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                },
                return_one_stmt_ast()
            ]
        });

        let skeleton = for_stmt_skeleton_from_ast(&stmt).expect("for skeleton");
        let ClangStmtSkeleton::For {
            condition: Some(condition),
            ..
        } = skeleton
        else {
            panic!("expected for skeleton, got {skeleton:?}");
        };
        assert_unsigned_integral_condition_cast(condition);
    }

    #[test]
    fn while_stmt_skeleton_from_ast_maps_single_statement_body() {
        let stmt = serde_json::json!({
            "kind": "WhileStmt",
            "inner": [
                {
                    "kind": "BinaryOperator",
                    "opcode": ">",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": { "name": "value" }
                                }
                            ]
                        },
                        {
                            "kind": "IntegerLiteral",
                            "type": { "qualType": "int" },
                            "value": "0"
                        }
                    ]
                },
                {
                    "kind": "BinaryOperator",
                    "opcode": "=",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "value" }
                        },
                        {
                            "kind": "BinaryOperator",
                            "opcode": "+",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "LValueToRValue",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "DeclRefExpr",
                                            "type": { "qualType": "int" },
                                            "referencedDecl": { "name": "value" }
                                        }
                                    ]
                                },
                                {
                                    "kind": "UnaryOperator",
                                    "opcode": "~",
                                    "type": { "qualType": "int" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "0"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let skeleton = while_stmt_skeleton_from_ast(&stmt).expect("while skeleton");
        let ClangStmtSkeleton::While { condition, body } = skeleton else {
            panic!("expected while skeleton, got {skeleton:?}");
        };
        assert!(matches!(
            condition,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Gt,
                ..
            }
        ));
        assert!(matches!(
            body.as_slice(),
            [ClangStmtSkeleton::Assign { .. }]
        ));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_accepts_prefix_increment_as_statement_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "++",
            "isPostfix": false,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "i" }
                }
            ]
        });

        let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect("prefix increment step");

        let ClangStmtSkeleton::Assign { target, value } = skeleton else {
            panic!("expected assignment step, got {skeleton:?}");
        };
        assert!(matches!(target, ClangExprSkeleton::DeclRef { name, .. } if name == "i"));
        assert!(matches!(
            value,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Add,
                ..
            }
        ));
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_accepts_prefix_decrement_as_statement_step() {
        let stmt = serde_json::json!({
            "kind": "UnaryOperator",
            "opcode": "--",
            "isPostfix": false,
            "type": { "qualType": "int" },
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "type": { "qualType": "int" },
                    "referencedDecl": { "name": "i" }
                }
            ]
        });

        let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect("prefix decrement step");

        let ClangStmtSkeleton::Assign { value, .. } = skeleton else {
            panic!("expected assignment step, got {skeleton:?}");
        };
        assert!(matches!(
            value,
            ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::Sub,
                ..
            }
        ));
    }

    #[test]
    fn expr_skeleton_from_ast_still_rejects_value_position_prefix_inc_dec() {
        for opcode in ["++", "--"] {
            let expr = serde_json::json!({
                "kind": "UnaryOperator",
                "opcode": opcode,
                "isPostfix": false,
                "type": { "qualType": "int" },
                "inner": [
                    {
                        "kind": "DeclRefExpr",
                        "type": { "qualType": "int" },
                        "referencedDecl": { "name": "i" }
                    }
                ]
            });

            let skeleton = expr_skeleton_from_ast(&expr).expect("prefix inc/dec skeleton");

            let ClangExprSkeleton::Unsupported { reason, .. } = skeleton else {
                panic!("expected unsupported prefix {opcode}, got {skeleton:?}");
            };
            assert!(
                reason.contains("prefix opcode"),
                "unexpected reason for {opcode}: {reason}"
            );
        }
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_prefix_inc_dec_non_scalar_targets() {
        let cases = [
            (
                "prefix deref target",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "UnaryOperator",
                            "opcode": "*",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int *" },
                                    "referencedDecl": { "name": "p" }
                                }
                            ]
                        }
                    ]
                }),
                "simple variable",
            ),
            (
                "prefix pointer target",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": false,
                    "type": { "qualType": "int *" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int *" },
                            "referencedDecl": { "name": "p" }
                        }
                    ]
                }),
                "unsupported",
            ),
        ];

        for (label, stmt, expected_reason) in cases {
            let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect(label);

            let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
                panic!("expected unsupported {label}, got {skeleton:?}");
            };
            assert!(
                reason.contains(expected_reason),
                "unexpected reason for {label}: {reason}"
            );
        }
    }

    #[test]
    fn for_step_stmt_skeleton_from_ast_rejects_inc_dec_without_explicit_bool_postfix_flag() {
        let cases = [
            (
                "missing postfix flag",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }),
            ),
            (
                "string postfix flag",
                serde_json::json!({
                    "kind": "UnaryOperator",
                    "opcode": "++",
                    "isPostfix": "false",
                    "type": { "qualType": "int" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "int" },
                            "referencedDecl": { "name": "i" }
                        }
                    ]
                }),
            ),
        ];

        for (label, stmt) in cases {
            let skeleton = for_step_stmt_skeleton_from_ast(&stmt).expect(label);

            let ClangStmtSkeleton::Unsupported { reason } = skeleton else {
                panic!("expected unsupported {label}, got {skeleton:?}");
            };
            assert!(
                reason.contains("explicit isPostfix flag"),
                "unexpected reason for {label}: {reason}"
            );
        }
    }

    #[test]
    fn type_from_qual_type_maps_fixed_width_integer_scalars() {
        let cases = [
            ("int8_t", "int8_t", true, 8),
            ("int16_t", "int16_t", true, 16),
            ("uint16_t", "uint16_t", false, 16),
            ("int32_t", "int32_t", true, 32),
            ("int64_t", "int64_t", true, 64),
            ("uint64_t", "uint64_t", false, 64),
        ];

        for (spelling, expected_canonical, expected_signed, expected_width) in cases {
            let ty = type_from_qual_type(spelling).expect("fixed-width integer type");

            assert_eq!(ty.spelled, spelling);
            assert_eq!(ty.canonical, expected_canonical);
            assert!(matches!(
                &ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if *signed == expected_signed && *width == expected_width
            ));
        }
    }

    #[test]
    fn type_from_ast_type_object_keeps_supported_qual_type_before_fallbacks() {
        let type_object = serde_json::json!({
            "qualType": "uint32_t",
            "desugaredQualType": "unsigned int",
            "canonicalQualType": "unsigned int"
        });

        let ty = type_from_ast_type_object(&type_object, None).expect("type skeleton");

        assert_eq!(ty.spelled, "uint32_t");
        assert_eq!(ty.canonical, "uint32_t");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn type_from_ast_type_object_falls_back_to_desugared_qual_type() {
        let type_object = serde_json::json!({
            "qualType": "fdb_blob_t",
            "desugaredQualType": "struct fdb_blob *",
            "canonicalQualType": "struct fdb_blob *"
        });

        let ty = type_from_ast_type_object(&type_object, None).expect("type skeleton");

        assert_eq!(ty.spelled, "struct fdb_blob *");
        assert_eq!(ty.canonical, "struct fdb_blob *");
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));
    }

    #[test]
    fn function_return_type_from_type_object_falls_back_to_desugared_signature() {
        let type_object = serde_json::json!({
            "qualType": "fdb_blob_t (fdb_blob_t)",
            "desugaredQualType": "struct fdb_blob *(struct fdb_blob *)",
            "canonicalQualType": "struct fdb_blob *(struct fdb_blob *)"
        });

        let ty = function_return_type_from_type_object(&type_object).expect("return type");

        assert_eq!(ty.spelled, "struct fdb_blob *");
        assert!(matches!(ty.kind, ClangTypeKind::Pointer { .. }));
    }

    #[test]
    fn type_from_qual_type_maps_signed_char_scalar() {
        let ty = type_from_qual_type("signed char").expect("signed char type");

        assert_eq!(ty.spelled, "signed char");
        assert_eq!(ty.canonical, "signed char");
        assert!(matches!(
            ty.kind,
            ClangTypeKind::Integer {
                signed: true,
                width: 8
            }
        ));
    }

    #[test]
    fn type_from_qual_type_keeps_target_dependent_integer_spellings_unsupported() {
        for spelling in [
            "char",
            "short",
            "unsigned short",
            "long",
            "unsigned long",
            "long long",
            "unsigned long long",
            "size_t",
        ] {
            let ty = type_from_qual_type(spelling).expect("type skeleton");

            assert!(matches!(
                ty.kind,
                ClangTypeKind::Unsupported { ref reason }
                    if reason.contains("requires target ABI width provenance")
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_lp64_integer_widths() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        for (spelling, expected_signed, expected_width) in [
            ("char", true, 8),
            ("short", true, 16),
            ("unsigned short", false, 16),
            ("long", true, 64),
            ("unsigned long", false, 64),
            ("long long", true, 64),
            ("unsigned long long", false, 64),
            ("size_t", false, 64),
        ] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert_eq!(ty.spelled, spelling);
            assert!(matches!(
                ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if signed == expected_signed && width == expected_width
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_int_width() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        for (spelling, expected_signed) in [("int", true), ("unsigned int", false)] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert_eq!(ty.spelled, spelling);
            assert!(matches!(
                ty.kind,
                ClangTypeKind::Integer { signed, width }
                    if signed == expected_signed && width == 16
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_target_abi_binds_pointer_width() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        let ty = type_from_qual_type_with_target_abi("const int *", Some(&abi))
            .expect("pointer type skeleton");

        assert_eq!(ty.spelled, "const int *");
        let ClangTypeKind::Pointer { pointee, width } = ty.kind else {
            panic!("expected pointer type, got {:?}", ty.kind);
        };
        assert_eq!(width, Some(64));
        assert_eq!(pointee.canonical, "int");
    }

    #[test]
    fn type_from_qual_type_maps_function_pointer_with_function_pointer_param() {
        let ty = type_from_qual_type("int (*)(int (*)(int), int)")
            .expect("function pointer type skeleton");

        let ClangTypeKind::Pointer { pointee, .. } = ty.kind else {
            panic!("expected function pointer type, got {:?}", ty.kind);
        };
        assert_eq!(ty.spelled, "int (*)(int (*)(int), int)");
        assert_eq!(pointee.spelled, "int (int (*)(int), int)");
        assert!(matches!(pointee.kind, ClangTypeKind::Function));
    }

    #[test]
    fn type_from_qual_type_with_target_abi_keeps_unproven_integer_widths_unsupported() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 0,
            plain_char_signed: None,
            short_width: 0,
            long_width: 64,
            long_long_width: 0,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };

        for spelling in [
            "char",
            "short",
            "unsigned short",
            "long long",
            "unsigned long long",
        ] {
            let ty =
                type_from_qual_type_with_target_abi(spelling, Some(&abi)).expect("type skeleton");

            assert!(matches!(
                ty.kind,
                ClangTypeKind::Unsupported { ref reason }
                    if reason.contains("requires an explicit target ABI width field")
            ));
        }
    }

    #[test]
    fn type_from_qual_type_with_unrecognized_target_abi_stays_fail_closed() {
        let ty = type_from_qual_type_with_target_abi("size_t", None).expect("type skeleton");

        assert!(matches!(
            ty.kind,
            ClangTypeKind::Unsupported { ref reason }
                if reason.contains("requires target ABI width provenance")
        ));
    }

    #[test]
    fn sizeof_integer_type_lowers_to_profile_bound_size_t_literal() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof integer skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof integer should lower");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert_eq!(ty.spelled, "size_t");
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));
    }

    #[test]
    fn sizeof_int_lowers_from_target_int_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(int) should lower with ABI profile");

        let IrExpr::LitInt { value, .. } = ir else {
            panic!("expected sizeof(int) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 2);
    }

    #[test]
    fn sizeof_size_t_lowers_from_target_pointer_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "size_t"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof size_t skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof size_t should lower");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(size_t) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 8);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_pointer_type_lowers_from_target_pointer_width_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "const int *"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof pointer skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof pointer should lower with ABI profile");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(pointer) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 8);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_pointer_type_stays_fail_closed_without_pointer_width_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "const int *"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof pointer skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof pointer requires target profile");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("pointer-width provenance"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_long_lowers_from_target_long_width_profile() {
        for (abi_name, long_width, expected_size) in [
            ("x86_64-unknown-linux-gnu", 64, 8),
            ("x86_64-pc-windows-msvc", 32, 4),
        ] {
            let abi = TargetAbiProfile {
                triple_or_abi: abi_name.to_string(),
                endianness: Some("little".to_string()),
                int_width: 32,
                char_width: 8,
                plain_char_signed: Some(true),
                short_width: 16,
                long_width,
                long_long_width: 64,
                pointer_width: 64,
                ..TargetAbiProfile::default()
            };
            let expr = serde_json::json!({
                "kind": "UnaryExprOrTypeTraitExpr",
                "type": {"qualType": "size_t"},
                "valueCategory": "prvalue",
                "name": "sizeof",
                "argType": {"qualType": "long"}
            });

            let mut skeleton =
                expr_skeleton_from_ast(&expr).expect("sizeof(long) skeleton should parse");
            bind_target_abi_to_expr(&mut skeleton, &abi);
            let ir = lower_expr(&skeleton).expect("sizeof(long) should lower with ABI profile");

            let IrExpr::LitInt { value, ty, .. } = ir else {
                panic!("expected sizeof(long) to lower to LitInt, got {ir:?}");
            };
            assert_eq!(value, expected_size, "{abi_name}");
            assert_eq!(ty.spelled, "size_t");
        }
    }

    #[test]
    fn sizeof_fixed_integer_array_type_lowers_to_total_byte_size() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-int-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[3]"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int[3]) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(int[3]) should lower with ABI profile");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(int[3]) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 6);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_incomplete_array_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[]"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof(int[]) skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof incomplete array must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("complete array bound"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_vla_like_array_type_stays_fail_closed() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[n]"}
        });

        let error = expr_skeleton_from_ast(&expr).expect_err("VLA-like sizeof must fail closed");

        assert_eq!(error.kind, "invalid_array_type");
        assert!(
            error.message.contains("array length is not usize"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_array_result_exceeding_target_size_t_stays_fail_closed() {
        let abi = TargetAbiProfile {
            triple_or_abi: "small-size-t-test-abi".to_string(),
            endianness: Some("little".to_string()),
            int_width: 16,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 32,
            long_long_width: 64,
            pointer_width: 16,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int[40000]"}
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof(int[40000]) skeleton should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let error = lower_expr(&skeleton).expect_err("oversized sizeof result must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error.message.contains("does not fit target result type"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_target_dependent_integer_stays_fail_closed_without_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "long"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("sizeof(long) skeleton should parse");
        let error = lower_expr(&skeleton).expect_err("sizeof(long) without ABI must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_type");
        assert!(
            error
                .message
                .contains("requires target ABI width provenance"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_expression_operand_stays_fail_closed_without_arg_type() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "referencedDecl": {
                        "kind": "VarDecl",
                        "name": "value"
                    },
                    "type": {"qualType": "int"}
                }
            ]
        });

        let error =
            expr_skeleton_from_ast(&expr).expect_err("sizeof expression operand must fail closed");

        assert_eq!(error.kind, "unsupported_sizeof_operand");
        assert!(
            error.message.contains("expression operand"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn sizeof_expression_operand_lowers_with_arg_type_profile() {
        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "int"},
            "inner": [
                {
                    "kind": "DeclRefExpr",
                    "referencedDecl": {
                        "kind": "VarDecl",
                        "name": "value"
                    },
                    "type": {"qualType": "int"}
                }
            ]
        });

        let mut skeleton =
            expr_skeleton_from_ast(&expr).expect("sizeof expression argType should parse");
        bind_target_abi_to_expr(&mut skeleton, &abi);
        let ir = lower_expr(&skeleton).expect("sizeof(value) should lower through argType");

        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected sizeof(value) to lower to LitInt, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert_eq!(ty.spelled, "size_t");
    }

    #[test]
    fn sizeof_record_type_stays_fail_closed_without_layout_provenance() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "sizeof",
            "argType": {"qualType": "struct point"}
        });

        let error = expr_skeleton_from_ast(&expr).expect_err("record sizeof must fail closed");

        assert!(
            error.message.contains("sizeof") && error.message.contains("layout"),
            "unexpected error: {error:?}"
        );
    }

    #[test]
    fn alignof_type_trait_lowers_only_with_alignment_profile() {
        let expr = serde_json::json!({
            "kind": "UnaryExprOrTypeTraitExpr",
            "type": {"qualType": "size_t"},
            "valueCategory": "prvalue",
            "name": "_Alignof",
            "argType": {"qualType": "int"}
        });

        let skeleton = expr_skeleton_from_ast(&expr).expect("_Alignof skeleton should parse");
        let ClangExprSkeleton::AlignOfType {
            arg_type,
            alignment_bits,
            ..
        } = &skeleton
        else {
            panic!("expected _Alignof type skeleton, got {skeleton:?}");
        };
        assert_eq!(arg_type.spelled, "int");
        assert_eq!(*alignment_bits, None);

        let error = lower_expr(&skeleton).expect_err("_Alignof must fail closed");
        assert_eq!(error.kind, "unsupported_alignof_type");
        assert!(
            error.message.contains("_Alignof") && error.message.contains("alignment"),
            "unexpected error: {error:?}"
        );

        let mut bound = skeleton.clone();
        let target_abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            int_align: 32,
            long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        bind_target_abi_to_expr(&mut bound, &target_abi);

        let ir = lower_expr(&bound).expect("_Alignof(int) lowers with target alignment profile");
        let IrExpr::LitInt { value, ty, .. } = ir else {
            panic!("expected literal _Alignof result, got {ir:?}");
        };
        assert_eq!(value, 4);
        assert!(matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        ));
    }

    #[test]
    fn type_from_qual_type_maps_fixed_array() {
        let ty = type_from_qual_type("uint32_t[256]").expect("array type");

        assert_eq!(ty.spelled, "uint32_t[256]");
        assert_eq!(ty.canonical, "uint32_t[256]");
        let ClangTypeKind::Array { element, len } = ty.kind else {
            panic!("expected array type, got {:?}", ty.kind);
        };
        assert_eq!(len, Some(256));
        assert!(matches!(
            element.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn type_from_qual_type_maps_const_fixed_array() {
        let ty = type_from_qual_type("const uint32_t[256]").expect("const array type");

        assert_eq!(ty.spelled, "const uint32_t[256]");
        assert_eq!(ty.canonical, "uint32_t[256]");
        assert!(clang_type_is_const(&ty));
        let ClangTypeKind::Array { element, len } = ty.kind else {
            panic!("expected array type, got {:?}", ty.kind);
        };
        assert_eq!(len, Some(256));
        assert!(matches!(
            element.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn type_from_qual_type_maps_incomplete_array() {
        let ty = type_from_qual_type("uint32_t[]").expect("incomplete array type");

        assert_eq!(ty.spelled, "uint32_t[]");
        assert_eq!(ty.canonical, "uint32_t[]");
        let ClangTypeKind::Array { element, len } = ty.kind else {
            panic!("expected array type, got {:?}", ty.kind);
        };
        assert_eq!(len, None);
        assert!(matches!(
            element.kind,
            ClangTypeKind::Integer {
                signed: false,
                width: 32
            }
        ));
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_integer_array_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const uint32_t[4]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const uint32_t[4]" },
                            "inner": [
                                {
                                    "kind": "ImplicitCastExpr",
                                    "castKind": "IntegralCast",
                                    "type": { "qualType": "uint32_t" },
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "1"
                                        }
                                    ]
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "3988292384"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "unsigned int" },
                                    "value": "4"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        let global = &globals[0];
        assert_eq!(global.name, "table");
        assert!(global.ty.is_const);
        assert!(matches!(
            global.ty.kind,
            IrTypeKind::Array { len: Some(4), .. }
        ));
        assert_eq!(
            global.init,
            IrGlobalInit::IntegerArray(vec![1, 2, 0xEDB8_8320, 4])
        );
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_sparse_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "7"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        let global = &globals[0];
        assert_eq!(global.name, "table");
        assert!(global.ty.is_const);
        assert!(matches!(
            global.ty.kind,
            IrTypeKind::Array { len: Some(3), .. }
        ));
        assert_eq!(global.init, IrGlobalInit::IntegerArray(vec![0, 7, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_all_zero_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].name, "table");
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![0, 0, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_rejects_malformed_static_const_array_filler_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_sentinel",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_length",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "1"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "2"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "3"
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "4"
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "bad_filler_side_effect",
                    "storageClass": "static",
                    "type": { "qualType": "const int[3]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[3]" },
                            "array_filler": [
                                {
                                    "kind": "ImplicitValueInitExpr",
                                    "type": { "qualType": "const int" }
                                },
                                {
                                    "kind": "CallExpr",
                                    "type": { "qualType": "int" }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert!(
            globals.is_empty(),
            "malformed array_filler globals must stay fail-closed: {globals:?}"
        );
    }

    #[test]
    fn readonly_globals_from_ast_maps_static_const_integer_array_enum_constant_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "EnumDecl",
                    "name": "status",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "id": "0x1001",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_OK",
                            "type": { "qualType": "int" },
                            "inner": [
                                {
                                    "kind": "ConstantExpr",
                                    "type": { "qualType": "int" },
                                    "value": "7",
                                    "inner": [
                                        {
                                            "kind": "IntegerLiteral",
                                            "type": { "qualType": "int" },
                                            "value": "7"
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[2]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[2]" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "id": "0x1001",
                                        "kind": "EnumConstantDecl",
                                        "name": "STATUS_OK"
                                    }
                                },
                                {
                                    "kind": "IntegerLiteral",
                                    "type": { "qualType": "int" },
                                    "value": "0"
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert_eq!(globals.len(), 1);
        assert_eq!(globals[0].name, "table");
        assert_eq!(globals[0].init, IrGlobalInit::IntegerArray(vec![7, 0]));
    }

    #[test]
    fn readonly_globals_from_ast_rejects_implicit_enum_constant_initializer() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "EnumDecl",
                    "name": "status",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "id": "0x1001",
                            "kind": "EnumConstantDecl",
                            "name": "STATUS_PENDING",
                            "type": { "qualType": "int" }
                        }
                    ]
                },
                {
                    "kind": "VarDecl",
                    "name": "table",
                    "storageClass": "static",
                    "type": { "qualType": "const int[1]" },
                    "init": "c",
                    "inner": [
                        {
                            "kind": "InitListExpr",
                            "type": { "qualType": "const int[1]" },
                            "inner": [
                                {
                                    "kind": "DeclRefExpr",
                                    "type": { "qualType": "int" },
                                    "referencedDecl": {
                                        "id": "0x1001",
                                        "kind": "EnumConstantDecl",
                                        "name": "STATUS_PENDING"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        });

        let globals = readonly_globals_from_ast(&ast).expect("readonly globals");

        assert!(
            globals.is_empty(),
            "implicit enum global initializer must stay fail-closed: {globals:?}"
        );
    }

    #[test]
    fn record_inventory_from_ast_maps_opaque_void_pointer_fields() {
        let ast = serde_json::json!({
            "kind": "TranslationUnitDecl",
            "inner": [
                {
                    "kind": "RecordDecl",
                    "tagUsed": "struct",
                    "name": "blob",
                    "completeDefinition": true,
                    "inner": [
                        {
                            "kind": "FieldDecl",
                            "name": "buf",
                            "type": { "qualType": "void *" }
                        },
                        {
                            "kind": "FieldDecl",
                            "name": "readonly",
                            "type": { "qualType": "const void *" }
                        },
                        {
                            "kind": "FieldDecl",
                            "name": "size",
                            "type": { "qualType": "size_t" }
                        }
                    ]
                }
            ]
        });

        let abi = TargetAbiProfile {
            triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
            endianness: Some("little".to_string()),
            int_width: 32,
            char_width: 8,
            plain_char_signed: Some(true),
            short_width: 16,
            long_width: 64,
            long_long_width: 64,
            pointer_width: 64,
            ..TargetAbiProfile::default()
        };
        let inventory = record_inventory_from_ast_with_target_abi(&ast, Some(&abi));
        let fields = inventory.get("blob").expect("blob record inventory");

        assert_eq!(fields.len(), 3);
        assert_eq!(fields[0].name, "buf");
        assert!(matches!(fields[0].ty.kind, IrTypeKind::Pointer { .. }));
        assert_eq!(fields[1].name, "readonly");
        let IrTypeKind::Pointer { pointee } = &fields[1].ty.kind else {
            panic!("expected const void pointer field, got {:?}", fields[1].ty);
        };
        assert!(pointee.is_const);
        assert_eq!(fields[2].name, "size");
        assert_eq!(fields[2].ty.spelled, "size_t");
        assert_eq!(fields[2].ty.width_bits, Some(64));
    }
}
