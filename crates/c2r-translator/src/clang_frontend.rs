use std::{collections::BTreeMap, env, error::Error, fmt, path::PathBuf};
#[cfg(feature = "typed-ir")]
use std::{path::Path, process::Command};

use serde::{Deserialize, Serialize};
#[cfg(feature = "typed-ir")]
use serde_json::Value;

#[cfg(feature = "typed-ir")]
use crate::typed_ir::{IrBinOp, IrExpr, IrFunction, IrParam, IrStmt, IrType, IrTypeKind, IrUnOp};
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
    Integer { signed: bool, width: u16 },
    Pointer { pointee: Box<ClangTypeSkeleton> },
    Unsupported { reason: String },
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
    Return {
        value: Option<ClangExprSkeleton>,
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
    Cast {
        target: ClangTypeSkeleton,
        expr: Box<ClangExprSkeleton>,
        implicit: bool,
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
    BitXor,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClangUnaryOperator {
    BitNot,
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
    let function = find_function_decl(&ast, function_name).ok_or_else(|| ClangFrontendError {
        kind: "missing_function_decl".to_string(),
        message: format!("clang AST JSON does not contain FunctionDecl named {function_name}"),
    })?;
    let skeleton = function_skeleton_from_ast(function)?;

    lower_function_skeleton(&skeleton)
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
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(&source_file)),
        parse_spec.function_name.clone(),
        Some(clang_path.to_string()),
        arguments.clone(),
        environment,
        lower_function_from_clang_ast_dump_with_arguments(
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
        };
    };

    report_from_lowering_result(
        Some(normalized_report_path(source_file)),
        function_name.to_string(),
        Some(clang_path.to_string()),
        arguments,
        environment,
        lower_function_from_clang_ast_dump(&PathBuf::from(clang_path), source_file, function_name),
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
        lower_function_skeleton(function),
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
    result: Result<IrFunction, ClangFrontendError>,
) -> ClangLoweringReport {
    match result {
        Ok(function_ir) => ClangLoweringReport {
            status: "lowered".to_string(),
            frontend: "clang".to_string(),
            source_file,
            function_name,
            clang_path,
            arguments,
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics: Vec::new(),
            errors: Vec::new(),
            function_ir: Some(function_ir),
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
    let body = inner(compound)
        .iter()
        .map(stmt_skeleton_from_ast)
        .collect::<Result<Vec<_>, ClangFrontendError>>()?;

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
        Some("ReturnStmt") => {
            let value = inner(stmt)
                .first()
                .map(expr_skeleton_from_ast)
                .transpose()?;
            Ok(ClangStmtSkeleton::Return { value })
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
        value: expr_skeleton_from_ast(value)?,
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
    let var_decls = inner(stmt)
        .iter()
        .filter(|child| string_field(child, "kind").as_deref() == Some("VarDecl"))
        .collect::<Vec<_>>();
    let [var_decl] = var_decls.as_slice() else {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: format!(
                "DeclStmt with {} VarDecl children is outside the current clang lowering skeleton",
                var_decls.len()
            ),
        });
    };
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
    if var_decl.get("init").is_some() || !inner(var_decl).is_empty() {
        return Ok(ClangStmtSkeleton::Unsupported {
            reason: "VarDecl initializer is outside the current clang lowering skeleton"
                .to_string(),
        });
    }

    Ok(ClangStmtSkeleton::Decl {
        name,
        ty,
        init: None,
    })
}

#[cfg(feature = "typed-ir")]
fn expr_skeleton_from_ast(expr: &Value) -> Result<ClangExprSkeleton, ClangFrontendError> {
    match string_field(expr, "kind").as_deref() {
        Some("ImplicitCastExpr") | Some("ParenExpr") => inner(expr)
            .first()
            .ok_or_else(|| ClangFrontendError {
                kind: "invalid_clang_expr".to_string(),
                message: format!(
                    "{} is missing operand",
                    string_field(expr, "kind").unwrap_or_else(|| "clang expression".to_string())
                ),
            })
            .and_then(expr_skeleton_from_ast),
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
                Some("^") => ClangBinaryOperator::BitXor,
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
            Ok(ClangExprSkeleton::Binary {
                op,
                lhs: Box::new(expr_skeleton_from_ast(lhs)?),
                rhs: Box::new(expr_skeleton_from_ast(rhs)?),
                ty: expr_type(expr)?,
            })
        }
        Some("UnaryOperator") => {
            let op = match string_field(expr, "opcode").as_deref() {
                Some("~") => ClangUnaryOperator::BitNot,
                Some(opcode) => {
                    return Ok(ClangExprSkeleton::Unsupported {
                        node: "UnaryOperator".to_string(),
                        reason: format!("opcode {opcode} is outside the current skeleton"),
                    });
                }
                None => {
                    return Err(ClangFrontendError {
                        kind: "invalid_unary_operator".to_string(),
                        message: "UnaryOperator is missing opcode".to_string(),
                    });
                }
            };
            let operand = inner(expr).first().ok_or_else(|| ClangFrontendError {
                kind: "invalid_unary_operator".to_string(),
                message: "UnaryOperator is missing operand".to_string(),
            })?;
            Ok(ClangExprSkeleton::Unary {
                op,
                operand: Box::new(expr_skeleton_from_ast(operand)?),
                ty: expr_type(expr)?,
            })
        }
        Some("CStyleCastExpr") => {
            if string_field(expr, "castKind").as_deref() != Some("BitCast") {
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
                expr: Box::new(expr_skeleton_from_ast(operand)?),
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
        "size_t" => Ok(ClangTypeSkeleton {
            spelled: trimmed.to_string(),
            canonical: "size_t".to_string(),
            kind: ClangTypeKind::Integer {
                signed: false,
                width: 64,
            },
        }),
        "unsigned long" | "unsigned long long" => Ok(ClangTypeSkeleton {
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
        ClangStmtSkeleton::Return { value } => Ok(IrStmt::Return {
            value: value.as_ref().map(lower_expr).transpose()?,
            source_span: None,
        }),
        ClangStmtSkeleton::Unsupported { reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_stmt".to_string(),
            message: reason.clone(),
        }),
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
        ClangExprSkeleton::Unsupported { node, reason } => Err(ClangFrontendError {
            kind: "unsupported_clang_expr".to_string(),
            message: format!("{node}: {reason}"),
        }),
    }
}

#[cfg(feature = "typed-ir")]
fn lower_binary_operator(op: &ClangBinaryOperator) -> IrBinOp {
    match op {
        ClangBinaryOperator::Add => IrBinOp::Add,
        ClangBinaryOperator::BitXor => IrBinOp::BitXor,
    }
}

#[cfg(feature = "typed-ir")]
fn lower_unary_operator(op: &ClangUnaryOperator) -> IrUnOp {
    match op {
        ClangUnaryOperator::BitNot => IrUnOp::BitNot,
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
