use serde::{Deserialize, Serialize};

use super::{ClangEnvironment, ClangFrontendError};
use crate::typed_ir::{IrFunction, IrGlobal};
use crate::TargetAbiProfile;

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
        record_layout: Option<ClangRecordLayoutBinding>,
        target_abi: Option<TargetAbiProfile>,
    },
    AlignOfType {
        arg_type: ClangTypeSkeleton,
        ty: ClangTypeSkeleton,
        alignment_bits: Option<u16>,
        alignment_type_spellings: Vec<String>,
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
    MutableVoidPointerAddress {
        operand: Box<ClangExprSkeleton>,
        source_pointer: ClangTypeSkeleton,
        target: ClangTypeSkeleton,
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub record_layout_evidence: Option<ClangRecordLayoutEvidence>,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangRecordLayout {
    pub record_type: String,
    pub size_bytes: u64,
    pub align_bytes: u64,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangRecordLayoutEvidence {
    pub status: String,
    pub dump_sha256: Option<String>,
    pub diagnostics_sha256: Option<String>,
    pub compile_arguments_sha256: Option<String>,
    pub compile_database_sha256: Option<String>,
    pub target_abi: Option<TargetAbiProfile>,
    pub arguments: Vec<String>,
    pub used_layouts: Vec<ClangRecordLayoutBinding>,
    pub ambiguous_records: Vec<String>,
    pub error: Option<String>,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ClangRecordLayoutBinding {
    pub record_type: String,
    pub size_bytes: u64,
    pub align_bytes: u64,
    pub dump_sha256: String,
    pub diagnostics_sha256: String,
    pub compile_arguments_sha256: String,
    pub compile_database_sha256: String,
    pub target_abi: TargetAbiProfile,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LoweredFunctionWithGlobals {
    pub function_ir: IrFunction,
    pub globals: Vec<IrGlobal>,
}
