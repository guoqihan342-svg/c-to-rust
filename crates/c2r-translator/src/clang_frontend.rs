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
    IrBinOp, IrExpr, IrFunction, IrGlobal, IrGlobalInit, IrIncDecOp, IrParam, IrStmt, IrType,
    IrTypeKind, IrUnOp,
};
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
    pub libclang_path: Option<String>,
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
                status: "configured".to_string(),
                source: Some("LIBCLANG_PATH".to_string()),
                libclang_path: Some(libclang_path.to_string()),
                diagnostics: vec![
                    "LIBCLANG_PATH is configured but real libclang parsing remains disabled in this dry-run skeleton"
                        .to_string(),
                ],
            };
        }

        Self {
            status: "not_configured".to_string(),
            source: None,
            libclang_path: None,
            diagnostics: vec![
                "LIBCLANG_PATH is not set; real libclang parsing remains disabled in this dry-run skeleton"
                    .to_string(),
            ],
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangDryRun {
    pub status: String,
    pub source_root: String,
    pub source_file: String,
    pub function_name: String,
    pub arguments: Vec<String>,
    pub compile_commands: Option<String>,
    pub environment: ClangEnvironment,
    pub diagnostics: Vec<String>,
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
    },
    Array {
        element: Box<ClangTypeSkeleton>,
        len: Option<usize>,
    },
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
    Cast {
        target: ClangTypeSkeleton,
        expr: Box<ClangExprSkeleton>,
        implicit: bool,
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
struct LoweredFunctionWithGlobals {
    function_ir: IrFunction,
    globals: Vec<IrGlobal>,
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
        self.dry_run_with_environment(&env::vars().collect())
    }

    pub fn dry_run_with_environment(&self, environment: &BTreeMap<String, String>) -> ClangDryRun {
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
    let function = find_function_decl(&ast, function_name).ok_or_else(|| ClangFrontendError {
        kind: "missing_function_decl".to_string(),
        message: format!("clang AST JSON does not contain FunctionDecl named {function_name}"),
    })?;
    let skeleton = function_skeleton_from_ast(function)?;
    let function_ir = lower_function_skeleton(&skeleton)?;
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
    let Some(clang_path) = environment
        .get("CLANG_PATH")
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    else {
        return ClangLoweringReport {
            status: "unavailable".to_string(),
            frontend: "clang".to_string(),
            source_file: Some(normalized_report_path(&source_file)),
            function_name: parse_spec.function_name.clone(),
            clang_path: None,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![
                "CLANG_PATH is not set; clang AST lowering is unavailable".to_string()
            ],
            errors: vec![ClangFrontendError {
                kind: "missing_clang_path".to_string(),
                message: "clang AST lowering requires CLANG_PATH".to_string(),
            }],
            function_ir: None,
            globals: Vec::new(),
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(&source_file)),
        parse_spec.function_name.clone(),
        Some(clang_path.to_string()),
        arguments.clone(),
        environment,
        lower_function_and_globals_from_clang_ast_dump_with_arguments(
            &PathBuf::from(clang_path),
            &arguments,
            &parse_spec.function_name,
        ),
    )
}

#[cfg(feature = "typed-ir")]
pub fn lower_function_from_clang_ast_dump_report(
    environment: &BTreeMap<String, String>,
    source_file: &Path,
    function_name: &str,
) -> ClangLoweringReport {
    let arguments = clang_ast_dump_arguments(source_file);
    let Some(clang_path) = environment
        .get("CLANG_PATH")
        .map(|value| value.trim())
        .filter(|value| !value.is_empty())
    else {
        return ClangLoweringReport {
            status: "unavailable".to_string(),
            frontend: "clang".to_string(),
            source_file: Some(normalized_report_path(source_file)),
            function_name: function_name.to_string(),
            clang_path: None,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: vec![
                "CLANG_PATH is not set; clang AST lowering is unavailable".to_string()
            ],
            errors: vec![ClangFrontendError {
                kind: "missing_clang_path".to_string(),
                message: "clang AST lowering requires CLANG_PATH".to_string(),
            }],
            function_ir: None,
            globals: Vec::new(),
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(source_file)),
        function_name.to_string(),
        Some(clang_path.to_string()),
        arguments.clone(),
        environment,
        lower_function_and_globals_from_clang_ast_dump_with_arguments(
            &PathBuf::from(clang_path),
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
    inner(ast)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("VarDecl"))
        .filter_map(readonly_global_from_toplevel_var_decl)
        .collect()
}

#[cfg(feature = "typed-ir")]
fn readonly_global_from_toplevel_var_decl(
    var_decl: &Value,
) -> Option<Result<IrGlobal, ClangFrontendError>> {
    if string_field(var_decl, "storageClass").as_deref() != Some("static") {
        return None;
    }

    let name = string_field(var_decl, "name")?;
    let qual_type = var_decl
        .get("type")
        .and_then(|value| string_field(value, "qualType"))?;
    let clang_ty = type_from_qual_type(&qual_type).ok()?;
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

    let values = integer_literal_init_list_values(initializer)?;
    if Some(values.len()) != *len {
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
fn integer_literal_init_list_values(init_list: &Value) -> Option<Vec<u64>> {
    inner(init_list)
        .iter()
        .map(integer_literal_init_value)
        .collect()
}

#[cfg(feature = "typed-ir")]
fn integer_literal_init_value(item: &Value) -> Option<u64> {
    match string_field(item, "kind").as_deref() {
        Some("IntegerLiteral") => string_field(item, "value")?.parse::<u64>().ok(),
        Some("ImplicitCastExpr" | "ParenExpr") => {
            let [operand] = inner(item) else {
                return None;
            };
            integer_literal_init_value(operand)
        }
        _ => None,
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
    let function_type = function
        .get("type")
        .and_then(|value| string_field(value, "qualType"))
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_function_decl".to_string(),
            message: format!("FunctionDecl {name} is missing qualType"),
        })?;
    let return_type = function_return_type(&function_type)?;
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
        .and_then(|value| string_field(value, "qualType"))
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_param_decl".to_string(),
            message: format!("ParmVarDecl {name} is missing qualType"),
        })
        .and_then(|qual_type| type_from_qual_type(&qual_type))?;

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
        Some("CallExpr") => Ok(ClangStmtSkeleton::Expr {
            expr: expr_skeleton_from_ast(stmt)?,
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
        condition: Some(expr_skeleton_from_ast(condition)?),
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
    let step = inc_dec_expr_skeleton_from_ast(stmt, true, false)?;
    let ClangExprSkeleton::IncDec { target, op, ty, .. } = step else {
        let reason = match step {
            ClangExprSkeleton::Unsupported { reason, .. } => reason,
            _ => "ForStmt step must be an increment/decrement expression".to_string(),
        };
        return Ok(ClangStmtSkeleton::Unsupported { reason });
    };
    let ClangExprSkeleton::DeclRef {
        name: target_name,
        ty: target_ty,
    } = target.as_ref()
    else {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "ForStmt step inc/dec target must be a simple variable".to_string(),
        });
    };
    if !matches!(&target_ty.kind, ClangTypeKind::Integer { .. })
        || !compound_assignment_types_match(target_ty, &ty)
    {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "ForStmt step inc/dec target type {} is unsupported",
                target_ty.canonical
            ),
        });
    }
    let bin_op = match op {
        ClangIncDecOperator::Inc => ClangBinaryOperator::Add,
        ClangIncDecOperator::Dec => ClangBinaryOperator::Sub,
    };
    Ok(ClangStmtSkeleton::Assign {
        target: ClangExprSkeleton::DeclRef {
            name: target_name.clone(),
            ty: target_ty.clone(),
        },
        value: ClangExprSkeleton::Binary {
            op: bin_op,
            lhs: Box::new(ClangExprSkeleton::DeclRef {
                name: target_name.clone(),
                ty: target_ty.clone(),
            }),
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
    let ClangExprSkeleton::DeclRef { ty: target_ty, .. } = &target else {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "compound assignment target must be a simple variable".to_string(),
        });
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

    Ok(ClangStmtSkeleton::CompoundAssign {
        target,
        op,
        value: expr_skeleton_from_ast_with_options(value, preserve_integral_casts)?,
        result_ty,
        compute_lhs_ty,
        compute_result_ty,
    })
}

#[cfg(feature = "typed-ir")]
fn compound_assignment_type_field(
    stmt: &Value,
    field: &str,
) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    stmt.get(field)
        .and_then(|value| string_field(value, "qualType"))
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_compound_assignment_operator".to_string(),
            message: format!("CompoundAssignOperator is missing {field}.qualType"),
        })
        .and_then(|qual_type| type_from_qual_type(&qual_type))
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
        condition: expr_skeleton_from_ast(condition)?,
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
        condition: expr_skeleton_from_ast(condition)?,
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
        condition: expr_skeleton_from_ast(condition)?,
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
        .and_then(|value| string_field(value, "qualType"))
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_var_decl".to_string(),
            message: format!("VarDecl {name} is missing qualType"),
        })
        .and_then(|qual_type| type_from_qual_type(&qual_type))?;
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
fn expr_skeleton_from_ast_with_options(
    expr: &Value,
    preserve_integral_casts: bool,
) -> Result<ClangExprSkeleton, ClangFrontendError> {
    match string_field(expr, "kind").as_deref() {
        Some("ImplicitCastExpr") => {
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_clang_expr".to_string(),
                message: "ImplicitCastExpr is missing operand".to_string(),
            })?;
            let operand = expr_skeleton_from_ast_with_options(operand, preserve_integral_casts)?;
            if string_field(expr, "castKind").as_deref() == Some("NullToPointer") {
                return null_pointer_skeleton_from_cast(expr, &operand, "ImplicitCastExpr");
            }
            if preserve_integral_casts && is_integral_conversion_cast_expr(expr) {
                return Ok(ClangExprSkeleton::Cast {
                    target: expr_type(expr)?,
                    expr: Box::new(operand),
                    implicit: true,
                });
            }
            Ok(operand)
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
                condition: Box::new(expr_skeleton_from_ast_with_options(condition, false)?),
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
                base: Box::new(expr_skeleton_from_ast_with_options(
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
        Some("InitListExpr") => init_list_expr_skeleton_from_ast(expr),
        Some("CallExpr") => call_expr_skeleton_from_ast(expr, preserve_integral_casts),
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
                Some("BitCast" | "IntegralCast" | "IntegralPromotion")
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
    if init_children.len() != *len {
        return Ok(ClangExprSkeleton::Unsupported {
            node: "InitListExpr".to_string(),
            reason: format!(
                "initializer element count {} does not match array length {len}",
                init_children.len()
            ),
        });
    }
    let elements = init_children
        .iter()
        .map(|element| expr_skeleton_from_ast_with_options(element, true))
        .collect::<Result<Vec<_>, ClangFrontendError>>()?;
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
fn call_expr_skeleton_from_ast(
    expr: &Value,
    preserve_integral_casts: bool,
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
        let arg = expr_skeleton_from_ast_with_options(arg_node, preserve_integral_casts)?;
        if let Some(reason) = bounded_call_arg_rejection_reason(&arg) {
            return Ok(ClangExprSkeleton::Unsupported {
                node: "CallExpr".to_string(),
                reason: format!("argument {index}: {reason}"),
            });
        }
        args.push(arg);
    }
    Ok(ClangExprSkeleton::Call {
        callee,
        args,
        ty: expr_type(expr)?,
    })
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
fn bounded_call_arg_rejection_reason(expr: &ClangExprSkeleton) -> Option<String> {
    match expr {
        ClangExprSkeleton::DeclRef { .. } | ClangExprSkeleton::IntegerLiteral { .. } => None,
        ClangExprSkeleton::NullPtr { .. } => {
            Some("call arguments cannot use null pointer value semantics".to_string())
        }
        ClangExprSkeleton::Binary { lhs, rhs, .. } => bounded_call_arg_rejection_reason(lhs)
            .or_else(|| bounded_call_arg_rejection_reason(rhs)),
        ClangExprSkeleton::Unary { operand, .. }
        | ClangExprSkeleton::Cast { expr: operand, .. } => {
            bounded_call_arg_rejection_reason(operand)
        }
        ClangExprSkeleton::Conditional { .. } => {
            Some("conditional call arguments are outside the bounded call subset".to_string())
        }
        ClangExprSkeleton::Index { base, index, .. } => bounded_call_arg_rejection_reason(base)
            .or_else(|| bounded_call_arg_rejection_reason(index)),
        ClangExprSkeleton::ArrayLiteral { .. } => {
            Some("array initializer lists are outside the bounded call subset".to_string())
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
        ClangExprSkeleton::Unsupported { node, reason } => {
            Some(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

#[cfg(feature = "typed-ir")]
fn is_integral_conversion_cast_expr(expr: &Value) -> bool {
    matches!(
        string_field(expr, "castKind").as_deref(),
        Some("IntegralCast" | "IntegralPromotion")
    )
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
        .and_then(|value| string_field(value, "qualType"))
        .ok_or_else(|| ClangFrontendError {
            kind: "invalid_clang_expr".to_string(),
            message: "clang expression node is missing qualType".to_string(),
        })
        .and_then(|qual_type| type_from_qual_type(&qual_type))
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
fn type_from_qual_type(qual_type: &str) -> Result<ClangTypeSkeleton, ClangFrontendError> {
    let trimmed = qual_type.trim();
    if let Some(pointee) = trimmed.strip_suffix('*') {
        let pointee = type_from_qual_type(pointee.trim())?;
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: format!("{} *", pointee.canonical),
            kind: ClangTypeKind::Pointer {
                pointee: Box::new(pointee),
            },
        });
    }
    if let Some(unqualified) = trimmed.strip_prefix("const ") {
        let unqualified = type_from_qual_type(unqualified.trim())?;
        return Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: unqualified.canonical,
            kind: unqualified.kind,
        });
    }
    if let Some((element, len)) = split_array_qual_type(trimmed)? {
        let element = type_from_qual_type(element)?;
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

    match trimmed {
        "void" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "void".to_string(),
            kind: ClangTypeKind::Void,
        }),
        "int" => Ok(ClangTypeSkeleton {
            spelled: "int".to_string(),
            canonical: "int".to_string(),
            kind: ClangTypeKind::Integer {
                signed: true,
                width: 32,
            },
        }),
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
        "unsigned int" | "uint32_t" => Ok(ClangTypeSkeleton {
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
        "size_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "size_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        }),
        "unsigned long" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: trimmed.to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        }),
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
    let ClangExprSkeleton::DeclRef { name, ty } = target else {
        return Err(ClangFrontendError {
            kind: "unsupported_compound_assignment_target".to_string(),
            message: "compound assignment target must be a simple variable".to_string(),
        });
    };
    let target_ty = lower_type(ty)?;
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
    let target = IrExpr::Var {
        name: name.clone(),
        ty: target_ty.clone(),
        source_span: None,
    };
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
        | IrExpr::AddrOf { ty, .. } => ir_types_match_for_clang(ty, expected),
        IrExpr::Cast { target, .. } => ir_types_match_for_clang(target, expected),
        IrExpr::Unsupported { .. } => false,
    }
}

#[cfg(feature = "typed-ir")]
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
        ClangExprSkeleton::Deref { ptr, ty } => Ok(IrExpr::Deref {
            ptr: Box::new(lower_expr(ptr)?),
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
        ClangExprSkeleton::Unsupported { node, reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!("{node}: {reason}"),
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
        ClangTypeKind::Pointer { pointee } => Ok(IrType {
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
fn inner(node: &Value) -> &[Value] {
    node.get("inner")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[])
}

#[cfg(feature = "typed-ir")]
fn string_field(node: &Value, field: &str) -> Option<String> {
    node.get(field)
        .and_then(Value::as_str)
        .map(ToString::to_string)
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
        assert!(matches!(
            lhs.as_ref(),
            IrExpr::Var { name, .. } if name == "value"
        ));
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
            assert!(matches!(
                lhs.as_ref(),
                IrExpr::Var { name, .. } if name == "value"
            ));
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
        assert!(matches!(
            args.as_slice(),
            [IrExpr::Var { name, .. }] if name == "value"
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
        assert!(matches!(
            args.as_slice(),
            [IrExpr::Var { name, .. }] if name == "value"
        ));
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
        assert!(matches!(value, ClangExprSkeleton::DeclRef { name, .. } if name == "y"));
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
    fn expr_skeleton_from_ast_rejects_function_pointer_call_expr() {
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
                                "kind": "VarDecl",
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
        let error = lower_expr(&skeleton).expect_err("function pointer call must fail closed");

        assert_eq!(error.kind, "unsupported_clang_expr");
        assert!(error
            .message
            .contains("callee is not a direct function identifier"));
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
        assert!(
            matches!(condition.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "flag")
        );
        assert!(
            matches!(then_expr.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "left")
        );
        assert!(
            matches!(else_expr.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "right")
        );
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
        assert!(matches!(lhs.as_ref(), ClangExprSkeleton::DeclRef { name, .. } if name == "value"));
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
        assert!(matches!(
            init,
            ClangExprSkeleton::DeclRef { name, .. } if name == "crc"
        ));
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
        assert!(matches!(condition, ClangExprSkeleton::DeclRef { name, .. } if name == "flag"));
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
        for spelling in ["short", "unsigned short", "long long", "unsigned long long"] {
            let ty = type_from_qual_type(spelling).expect("type skeleton");

            assert!(matches!(ty.kind, ClangTypeKind::Unsupported { .. }));
        }
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
}
