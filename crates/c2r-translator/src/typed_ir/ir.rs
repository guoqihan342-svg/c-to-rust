use crate::TargetAbiProfile;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SourceSpan {
    pub file: Option<String>,
    pub line: Option<u32>,
    pub column: Option<u32>,
    pub text: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrFunction {
    pub name: String,
    pub return_type: IrType,
    pub params: Vec<IrParam>,
    pub body: Vec<IrStmt>,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrParam {
    pub name: String,
    pub ty: IrType,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrGlobal {
    pub name: String,
    pub ty: IrType,
    pub init: IrGlobalInit,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrGlobalInit {
    IntegerArray(Vec<u64>),
    Zeroed,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrType {
    pub spelled: String,
    pub canonical: String,
    pub kind: IrTypeKind,
    pub is_const: bool,
    pub width_bits: Option<u16>,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrRecordField {
    pub name: String,
    pub ty: IrType,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrRecordLayoutBinding {
    pub record_type: String,
    pub size_bytes: u64,
    pub align_bytes: u64,
    pub dump_sha256: String,
    pub diagnostics_sha256: String,
    pub compile_arguments_sha256: String,
    pub compile_database_sha256: String,
    pub target_abi: TargetAbiProfile,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrTypeKind {
    Void,
    Integer {
        signed: bool,
        width: u16,
    },
    Pointer {
        pointee: Box<IrType>,
    },
    Array {
        element: Box<IrType>,
        len: Option<usize>,
    },
    Record {
        name: String,
        fields: Option<Vec<IrRecordField>>,
    },
    Function,
    Unsupported {
        reason: String,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrExpr {
    LitInt {
        value: u64,
        spelling: String,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    NullPtr {
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Var {
        name: String,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Binary {
        op: IrBinOp,
        lhs: Box<IrExpr>,
        rhs: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Unary {
        op: IrUnOp,
        operand: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Conditional {
        condition: Box<IrExpr>,
        then_expr: Box<IrExpr>,
        else_expr: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Cast {
        target: IrType,
        expr: Box<IrExpr>,
        implicit: bool,
        source_span: Option<SourceSpan>,
    },
    LValueToRValue {
        target: IrType,
        expr: Box<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    ArrayToPointerDecay {
        target: IrType,
        expr: Box<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    FunctionToPointerDecay {
        target: IrType,
        expr: Box<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    Index {
        base: Box<IrExpr>,
        index: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    ArrayLiteral {
        elements: Vec<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Call {
        callee: String,
        args: Vec<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Member {
        base: Box<IrExpr>,
        field: String,
        ty: IrType,
        is_arrow: bool,
        source_span: Option<SourceSpan>,
    },
    IncDec {
        target: Box<IrExpr>,
        op: IrIncDecOp,
        prefix: bool,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Deref {
        ptr: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    AddrOf {
        operand: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    MutableVoidPointerAddress {
        operand: Box<IrExpr>,
        source_pointer: IrType,
        target: IrType,
        source_span: Option<SourceSpan>,
    },
    Unsupported {
        node: String,
        reason: String,
        source_span: Option<SourceSpan>,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrStmt {
    Decl {
        name: String,
        ty: IrType,
        init: Option<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    Assign {
        target: IrExpr,
        value: IrExpr,
        source_span: Option<SourceSpan>,
    },
    If {
        condition: IrExpr,
        then_body: Vec<IrStmt>,
        else_body: Vec<IrStmt>,
        source_span: Option<SourceSpan>,
    },
    While {
        condition: IrExpr,
        body: Vec<IrStmt>,
        source_span: Option<SourceSpan>,
    },
    DoWhile {
        body: Vec<IrStmt>,
        condition: IrExpr,
        source_span: Option<SourceSpan>,
    },
    For {
        init: Vec<IrStmt>,
        condition: Option<IrExpr>,
        step: Option<Box<IrStmt>>,
        body: Vec<IrStmt>,
        source_span: Option<SourceSpan>,
    },
    Return {
        value: Option<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    Break {
        source_span: Option<SourceSpan>,
    },
    Continue {
        source_span: Option<SourceSpan>,
    },
    Expr {
        expr: IrExpr,
        source_span: Option<SourceSpan>,
    },
    RecordMemset {
        destination: IrExpr,
        byte: u8,
        write_len_bytes: u64,
        layout: IrRecordLayoutBinding,
        source_span: Option<SourceSpan>,
    },
    Unsupported {
        node: String,
        reason: String,
        source_span: Option<SourceSpan>,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrBinOp {
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
    Eq,
    Neq,
    Lt,
    Le,
    Gt,
    Ge,
    LogAnd,
    LogOr,
    Assign,
    Comma,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrUnOp {
    Neg,
    Not,
    BitNot,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrIncDecOp {
    Inc,
    Dec,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IrEmitError {
    pub reason: String,
    pub route: crate::translation_route::CandidateRouteDecision,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum SignedRightShiftPolicy {
    #[default]
    FailClosed,
    ImplementationDefinedArithmetic,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct EmitPolicy {
    pub signed_right_shift: SignedRightShiftPolicy,
    pub noalias_param_pairs: Vec<NoAliasParamPair>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NoAliasParamPair {
    pub readonly_param: String,
    pub mutable_param: String,
}
