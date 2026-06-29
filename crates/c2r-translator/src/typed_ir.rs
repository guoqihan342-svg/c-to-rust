//! Typed IR: intermediate representation for C semantics and a generic Rust emitter.
//!
//! # IR Layering (Target Architecture)
//!
//! The long-term goal is a three-layer IR that separates concerns:
//!
//! **Layer 1: Semantic IR (most important)** — preserves C semantics. Does not do Rust
//! inference. Does not produce candidates. Only answers: "what does this C code do in
//! the C abstract machine?" All implicit conversions, pointer arithmetic, and UB markers
//! are preserved here.
//!
//! **Layer 2: Control IR** — if/loop/goto/switch with explicit CFG. Every control flow
//! edge carries an explicit condition. `break`/`continue` are CFG edges, not ad-hoc
//! handling. A relooper can recover structured control flow from arbitrary CFG.
//!
//! **Layer 3: Typed Value IR** — integer/pointer/struct/array with explicit casts only.
//! All implicit conversions from Layer 1 become explicit `Cast` nodes here. Pointer
//! arithmetic is decomposed into element access. Array-to-pointer decay is explicit.
//!
//! **Lowering layer** (not yet a separate module): converts from Semantic IR to a Rust
//! candidate. Every lowering rule must be provable. When lowering fails, the reason is
//! recorded fail-closed. IR must not "decide how Rust should be written", only "describe
//! what C is".
//!
//! # Current State
//!
//! The current typed IR combines aspects of all three layers. `IrExpr` and `IrStmt`
//! represent a mix of C-level semantics (e.g., `Cast { implicit }`) and Rust-level
//! lowering decisions (e.g., `const void *` mapped directly to `&[u8]` in certain
//! contexts). This is acceptable for P0 but will be separated into distinct layers
//! in future phases.
//!
//! # Generic Emitter Boundaries
//!
//! The `emit_*` family of functions in this module implements a conservative,
//! narrow-subset generic Rust emitter. Key boundaries:
//!
//! - Only integer scalar types are fully supported (i8/u8/i16/u16/i32/u32/i64/u64/usize).
//! - Floating-point, enum, union, function pointer, and general pointer types fail closed.
//! - Control flow: `if`/`while`/`for`/`do-while`/`break`/`continue` with narrow conditions.
//!   `switch`/`goto` fail closed.
//! - Declarations: scalar locals with optional init; local fixed arrays; multi-decl.
//! - Expressions: arithmetic, bitwise, comparison, logical-not, short-circuit, conditional,
//!   direct calls, narrow deref/index/member reads, narrow mutable pointer writes.
//! - See `docs/c2rust-migration-agent/COVERAGE.md` for the complete supported/unsupported inventory.
//!
//! # Fail-Closed Principle
//!
//! When the emitter encounters an IR node it cannot safely emit, it returns `IrEmitError`
//! with a specific reason. It never guesses or silently falls back. The old crc32 canned
//! matcher and template have been deleted; projects like FlashDB crc32 must go through
//! clang-lowered typed IR + readonly globals + generic emitter.

use crate::translation_route::{generic_typed_ir_route, unsupported_route, EmittedRust};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::hash::Hash;

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

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SignedRightShiftPolicy {
    FailClosed,
    ImplementationDefinedArithmetic,
}

impl Default for SignedRightShiftPolicy {
    fn default() -> Self {
        Self::FailClosed
    }
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

#[derive(Clone, Debug, Default)]
struct EmitContext {
    policy: EmitPolicy,
    assigned_vars: HashSet<String>,
    byte_slice_params: HashSet<String>,
    byte_cursor_sources: HashMap<String, String>,
    nullable_pointer_params: HashSet<String>,
    readonly_pointer_read_params: HashSet<String>,
    readonly_pointer_mentioned_params: HashSet<String>,
    mutable_record_pointer_write_params: HashSet<String>,
    opaque_record_pointer_field_value_params: HashSet<String>,
    mutable_record_pointer_read_fields: HashSet<MutableRecordPointerFieldKey>,
    readonly_globals: HashMap<String, IrGlobal>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct EmittedExpr {
    prelude: String,
    expr: String,
}

#[derive(Clone, Debug)]
struct RecordFieldUse<'a> {
    name: &'a str,
    ty: &'a IrType,
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
struct MutableRecordPointerFieldKey {
    base: String,
    field: String,
}

#[derive(Clone, Debug, Default)]
struct ReadonlyPointerParamUses {
    read_params: HashSet<String>,
    mentioned_params: HashSet<String>,
}

#[derive(Clone, Debug, Default)]
struct DefiniteAssignmentState {
    declared: HashSet<String>,
    initialized: HashSet<String>,
    mutable_record_pointer_write_params: HashSet<String>,
    mutable_record_pointer_fields: HashSet<MutableRecordPointerFieldKey>,
    validated_mutable_record_pointer_read_fields: HashSet<MutableRecordPointerFieldKey>,
}

impl DefiniteAssignmentState {
    fn from_function_and_globals(
        function: &IrFunction,
        globals: &[IrGlobal],
        context: &EmitContext,
    ) -> Self {
        let mut state = Self::default();
        state.mutable_record_pointer_write_params =
            context.mutable_record_pointer_write_params.clone();
        for param in &function.params {
            state.declared.insert(param.name.clone());
            state.initialized.insert(param.name.clone());
        }
        for global in globals {
            state.declared.insert(global.name.clone());
            state.initialized.insert(global.name.clone());
        }
        state
    }

    fn declare(&mut self, name: &str, initialized: bool) -> Result<(), String> {
        if self.declared.contains(name) {
            return Err(format!("decl {name} duplicates an existing symbol"));
        }
        self.declared.insert(name.to_string());
        if initialized {
            self.initialized.insert(name.to_string());
        }
        Ok(())
    }

    fn assign(&mut self, name: &str) -> Result<(), String> {
        if !self.declared.contains(name) {
            return Err(format!("assign target {name} is not declared"));
        }
        self.initialized.insert(name.to_string());
        Ok(())
    }

    fn require_initialized(&self, name: &str) -> Result<(), String> {
        if !self.declared.contains(name) {
            return Err(format!("var {name} is not declared"));
        }
        if !self.initialized.contains(name) {
            return Err(format!("var {name} is read before assignment"));
        }
        Ok(())
    }

    fn assign_mutable_record_pointer_field(&mut self, key: MutableRecordPointerFieldKey) {
        self.mutable_record_pointer_fields.insert(key);
    }

    fn require_mutable_record_pointer_field_initialized(
        &mut self,
        key: &MutableRecordPointerFieldKey,
    ) -> Result<(), String> {
        if !self.mutable_record_pointer_fields.contains(key) {
            return Err(format!(
                "mutable record pointer field {}.{} is read before definite assignment",
                key.base, key.field
            ));
        }
        self.validated_mutable_record_pointer_read_fields
            .insert(key.clone());
        Ok(())
    }
}

impl EmitContext {
    fn from_function_and_globals_and_policy(
        function: &IrFunction,
        globals: &[IrGlobal],
        policy: EmitPolicy,
    ) -> Result<Self, String> {
        let assigned_vars = collect_assigned_vars(&function.body);
        let byte_cursor_sources = collect_byte_cursor_sources(&function.body);
        let mut byte_slice_params = HashSet::new();
        for source in byte_cursor_sources.values() {
            if function
                .params
                .iter()
                .any(|param| param.name == *source && is_const_void_pointer(&param.ty))
            {
                byte_slice_params.insert(source.clone());
            }
        }
        let nullable_pointer_params =
            collect_nullable_pointer_params(&function.body, &function.params)?;
        let readonly_pointer_uses =
            collect_readonly_pointer_param_uses(&function.body, &function.params)?;
        validate_readonly_pointer_slice_lowering_evidence(
            &function.params,
            &byte_slice_params,
            &nullable_pointer_params,
            &readonly_pointer_uses.read_params,
            &readonly_pointer_uses.mentioned_params,
        )?;
        validate_mutable_pointer_write_alias_boundary(&function.body, &function.params, &policy)?;
        let mutable_record_pointer_write_params =
            collect_mutable_record_pointer_write_params(&function.body, &function.params)?;
        let opaque_record_pointer_field_value_params =
            collect_opaque_record_pointer_field_value_params(
                &function.body,
                &function.params,
                &mutable_record_pointer_write_params,
            )?;
        let mut readonly_globals = HashMap::new();
        for global in globals {
            if readonly_globals
                .insert(global.name.clone(), global.clone())
                .is_some()
            {
                return Err(format!(
                    "global {} duplicates an existing global",
                    global.name
                ));
            }
        }
        Ok(Self {
            policy,
            assigned_vars,
            byte_slice_params,
            byte_cursor_sources,
            nullable_pointer_params,
            readonly_pointer_read_params: readonly_pointer_uses.read_params,
            readonly_pointer_mentioned_params: readonly_pointer_uses.mentioned_params,
            mutable_record_pointer_write_params,
            opaque_record_pointer_field_value_params,
            mutable_record_pointer_read_fields: HashSet::new(),
            readonly_globals,
        })
    }

    fn is_assigned_var(&self, name: &str) -> bool {
        self.assigned_vars.contains(name)
    }

    fn byte_cursor_source(&self, cursor: &str) -> Option<&str> {
        self.byte_cursor_sources.get(cursor).map(String::as_str)
    }

    fn is_byte_slice_param(&self, name: &str) -> bool {
        self.byte_slice_params.contains(name)
    }

    fn is_nullable_pointer_param(&self, name: &str) -> bool {
        self.nullable_pointer_params.contains(name)
    }

    fn is_readonly_pointer_read_param(&self, name: &str) -> bool {
        self.readonly_pointer_read_params.contains(name)
    }

    fn is_readonly_pointer_mentioned_param(&self, name: &str) -> bool {
        self.readonly_pointer_mentioned_params.contains(name)
    }

    fn is_mutable_record_pointer_write_param(&self, name: &str) -> bool {
        self.mutable_record_pointer_write_params.contains(name)
    }

    fn is_opaque_record_pointer_field_value_param(&self, name: &str) -> bool {
        self.opaque_record_pointer_field_value_params.contains(name)
    }

    fn is_mutable_record_pointer_read_field(&self, name: &str, field: &str) -> bool {
        self.mutable_record_pointer_read_fields
            .contains(&MutableRecordPointerFieldKey {
                base: name.to_string(),
                field: field.to_string(),
            })
    }

    fn readonly_global(&self, name: &str) -> Option<&IrGlobal> {
        self.readonly_globals.get(name)
    }

    fn global_rust_name(&self, name: &str) -> Result<String, String> {
        emit_global_const_identifier(name)
    }
}

#[allow(clippy::result_large_err)]
pub fn emit_rust_from_ir(function: &IrFunction) -> Result<EmittedRust, IrEmitError> {
    emit_scalar_rust_from_ir(function)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}

#[allow(clippy::result_large_err)]
/// Emits Rust for typed IR with readonly globals, preserving fail-closed errors.
///
/// This is the public typed-IR generation boundary used by clang-lowered
/// translation. Unsupported IR does not fall back to legacy templates; it is
/// returned as an `IrEmitError` with the same route metadata used by evidence
/// gates.
pub fn emit_rust_from_ir_with_globals(
    function: &IrFunction,
    globals: &[IrGlobal],
) -> Result<EmittedRust, IrEmitError> {
    emit_rust_from_ir_with_globals_and_policy(function, globals, EmitPolicy::default())
}

#[allow(clippy::result_large_err)]
pub fn emit_rust_from_ir_with_globals_and_policy(
    function: &IrFunction,
    globals: &[IrGlobal],
    policy: EmitPolicy,
) -> Result<EmittedRust, IrEmitError> {
    emit_scalar_rust_from_ir_with_globals_and_policy(function, globals, policy)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}

fn emit_scalar_rust_from_ir(function: &IrFunction) -> Result<String, String> {
    emit_scalar_rust_from_ir_with_globals(function, &[])
}

fn emit_scalar_rust_from_ir_with_globals(
    function: &IrFunction,
    globals: &[IrGlobal],
) -> Result<String, String> {
    emit_scalar_rust_from_ir_with_globals_and_policy(function, globals, EmitPolicy::default())
}

/// Lowers the supported scalar subset into one Rust function plus constants.
///
/// The function first builds the semantic emission context and runs
/// fail-closed validation, then emits globals, record definitions, parameters,
/// and statements. Anything outside the current typed IR contract returns a
/// path-rich error before a partial Rust candidate can escape.
fn emit_scalar_rust_from_ir_with_globals_and_policy(
    function: &IrFunction,
    globals: &[IrGlobal],
    policy: EmitPolicy,
) -> Result<String, String> {
    let return_type = emit_return_type(&function.return_type)?;
    if return_type.is_some() && !ends_with_return_value(&function.body) {
        return Err("non-void function must end with a return value".to_string());
    }
    let mut context = EmitContext::from_function_and_globals_and_policy(function, globals, policy)?;
    context.mutable_record_pointer_read_fields =
        validate_definite_assignment(function, globals, &context)?;
    let function_name = emit_identifier(&function.name, "function")?;
    let params = function
        .params
        .iter()
        .map(|param| emit_param(param, &context.assigned_vars, &context))
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    let mut symbols = collect_param_symbols(&function.params)?;

    let mut rust = String::new();
    for global in globals {
        rust.push_str(&emit_global_const(global)?);
    }
    if !globals.is_empty() {
        rust.push('\n');
    }
    let record_definitions = emit_record_definitions(function)?;
    for definition in &record_definitions {
        rust.push_str(definition);
    }
    if !record_definitions.is_empty() {
        rust.push('\n');
    }
    rust.push_str(&format!("pub fn {function_name}({params})"));
    if let Some(return_type) = return_type {
        rust.push_str(&format!(" -> {}", return_type));
    }
    rust.push_str(" {\n");
    for (index, stmt) in function.body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            &function.return_type,
            1,
            &mut symbols,
            &context,
            LoopContext::None,
        )
        .map_err(|detail| format!("stmt[{index}].{detail}"))?;
        rust.push_str(&line);
    }
    rust.push_str("}\n");
    Ok(rust)
}

fn emit_param(
    param: &IrParam,
    assigned_vars: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let ty = if context.is_nullable_pointer_param(&param.name) {
        emit_nullable_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if context.is_mutable_record_pointer_write_param(&param.name) {
        emit_mutable_record_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if context.is_byte_slice_param(&param.name) {
        "&[u8]".to_string()
    } else if context.is_opaque_record_pointer_field_value_param(&param.name) {
        emit_opaque_void_pointer_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else if readonly_pointer_slice_element_type(&param.ty).is_some()
        && !context.is_readonly_pointer_read_param(&param.name)
        && !context.is_readonly_pointer_mentioned_param(&param.name)
    {
        return Err(format!(
            "param {} requires pointer-to-slice lowering evidence before lowering {} to &[T]",
            param.name,
            type_label(&param.ty)
        ));
    } else if assigned_vars.contains(&param.name) {
        emit_assigned_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    } else {
        emit_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    };
    let name = emit_identifier(&param.name, "param")?;
    let mut_prefix = if assigned_vars.contains(&param.name) {
        "mut "
    } else {
        ""
    };
    Ok(format!("{mut_prefix}{name}: {ty}"))
}

fn emit_assigned_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(element_ty) = mutable_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("&mut [{element_ty}]"));
    }
    emit_param_type(ty)
}

fn emit_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(element_ty) = readonly_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("&[{element_ty}]"));
    }
    if let Some(pointee) = readonly_record_pointer_pointee_type(ty) {
        return emit_value_type(pointee).map(|ty| format!("&{ty}"));
    }
    emit_value_type(ty)
}

fn emit_value_type(ty: &IrType) -> Result<String, String> {
    if let IrTypeKind::Record { name, .. } = &ty.kind {
        return emit_record_type_name(name);
    }
    emit_scalar_type(ty)
}

fn emit_opaque_void_pointer_param_type(ty: &IrType) -> Result<String, String> {
    emit_opaque_void_pointer_type(ty).ok_or_else(|| {
        format!(
            "opaque record pointer field value param type {} is unsupported",
            type_label(ty)
        )
    })
}

fn emit_record_field_type(ty: &IrType) -> Result<String, String> {
    if let Some(pointer_ty) = emit_opaque_void_pointer_type(ty) {
        return Ok(pointer_ty);
    }
    emit_scalar_type(ty)
}

fn emit_opaque_void_pointer_type(ty: &IrType) -> Option<String> {
    let IrTypeKind::Pointer { pointee } = &ty.kind else {
        return None;
    };
    if !matches!(pointee.kind, IrTypeKind::Void) {
        return None;
    }
    let mutability = if pointee.is_const { "const" } else { "mut" };
    Some(format!("*{mutability} core::ffi::c_void"))
}

fn emit_nullable_pointer_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(element_ty) = readonly_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("Option<&[{element_ty}]>"));
    }
    if let Some(pointee) = readonly_record_pointer_pointee_type(ty) {
        let pointee = emit_value_type(pointee)?;
        return Ok(format!("Option<&{pointee}>"));
    }
    Err(format!(
        "nullable pointer param type {} is unsupported",
        type_label(ty)
    ))
}

fn emit_mutable_record_pointer_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(pointee) = mutable_record_pointer_pointee_type(ty) {
        let pointee = emit_value_type(pointee)?;
        return Ok(format!("&mut {pointee}"));
    }
    Err(format!(
        "mutable record pointer param type {} is unsupported",
        type_label(ty)
    ))
}

fn emit_record_definitions(function: &IrFunction) -> Result<Vec<String>, String> {
    let mut records: Vec<(&str, Vec<RecordFieldUse<'_>>)> = Vec::new();
    add_record_type_inventory(&mut records, &function.return_type)?;
    for param in &function.params {
        if let IrTypeKind::Record { name, .. } = &param.ty.kind {
            ensure_record_entry(&mut records, name);
        }
        if let Some(pointee) = readonly_record_pointer_pointee_type(&param.ty) {
            add_record_type_inventory(&mut records, pointee)?;
            if let IrTypeKind::Record { name, .. } = &pointee.kind {
                ensure_record_entry(&mut records, name);
            }
        }
        if let Some(pointee) = mutable_record_pointer_pointee_type(&param.ty) {
            add_record_type_inventory(&mut records, pointee)?;
            if let IrTypeKind::Record { name, .. } = &pointee.kind {
                ensure_record_entry(&mut records, name);
            }
        }
    }
    for stmt in &function.body {
        collect_record_field_uses_from_stmt(stmt, &mut records)?;
    }

    records
        .into_iter()
        .map(|(name, fields)| emit_record_definition(name, &fields))
        .collect()
}

fn ensure_record_entry<'a>(records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>, name: &'a str) {
    if records.iter().any(|(record_name, _)| *record_name == name) {
        return;
    }
    records.push((name, Vec::new()));
}

fn add_record_type_inventory<'a>(
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
    ty: &'a IrType,
) -> Result<(), String> {
    let IrTypeKind::Record {
        name,
        fields: Some(fields),
    } = &ty.kind
    else {
        return Ok(());
    };
    for field in fields {
        add_record_field_use(records, name, &field.name, &field.ty)?;
    }
    Ok(())
}

fn add_record_field_use<'a>(
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
    record_name: &'a str,
    field_name: &'a str,
    field_ty: &'a IrType,
) -> Result<(), String> {
    ensure_record_entry(records, record_name);
    let Some((_, fields)) = records.iter_mut().find(|(name, _)| *name == record_name) else {
        return Err(format!("record {record_name} was not registered"));
    };
    if let Some(existing) = fields.iter().find(|field| field.name == field_name) {
        if record_field_types_match(existing.ty, field_ty) {
            return Ok(());
        }
        return Err(format!(
            "record {record_name} field {field_name} has inconsistent types {} and {}",
            type_label(existing.ty),
            type_label(field_ty)
        ));
    }
    fields.push(RecordFieldUse {
        name: field_name,
        ty: field_ty,
    });
    Ok(())
}

fn record_field_types_match(lhs: &IrType, rhs: &IrType) -> bool {
    lhs == rhs
        || (is_integer_type(lhs)
            && is_integer_type(rhs)
            && lhs.canonical == rhs.canonical
            && lhs.kind == rhs.kind
            && lhs.width_bits == rhs.width_bits)
}

fn emit_record_definition(name: &str, fields: &[RecordFieldUse<'_>]) -> Result<String, String> {
    if fields.is_empty() {
        return Err(format!("record {name} has no modeled fields"));
    }
    let rust_name = emit_record_type_name(name)?;
    let mut definition = String::new();
    definition.push_str("#[derive(Clone, Copy, Debug, Eq, PartialEq)]\n");
    definition.push_str(&format!("pub struct {rust_name} {{\n"));
    for field in fields {
        let field_name = emit_identifier(field.name, "record field")?;
        let field_ty = emit_record_field_type(field.ty)
            .map_err(|detail| format!("record {name} field {} has {detail}", field.name))?;
        definition.push_str(&format!("    pub {field_name}: {field_ty},\n"));
    }
    definition.push_str("}\n");
    Ok(definition)
}

fn collect_record_field_uses_from_stmt<'a>(
    stmt: &'a IrStmt,
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                collect_record_field_uses_from_expr(init, records)?;
            }
        }
        IrStmt::Assign { target, value, .. } => {
            collect_record_field_uses_from_expr(target, records)?;
            collect_record_field_uses_from_expr(value, records)?;
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            collect_record_field_uses_from_expr(condition, records)?;
            for stmt in then_body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
            for stmt in else_body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
        }
        IrStmt::While {
            condition, body, ..
        }
        | IrStmt::DoWhile {
            condition, body, ..
        } => {
            collect_record_field_uses_from_expr(condition, records)?;
            for stmt in body {
                collect_record_field_uses_from_stmt(stmt, records)?;
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
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
            if let Some(condition) = condition {
                collect_record_field_uses_from_expr(condition, records)?;
            }
            if let Some(step) = step {
                collect_record_field_uses_from_stmt(step, records)?;
            }
            for stmt in body {
                collect_record_field_uses_from_stmt(stmt, records)?;
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                collect_record_field_uses_from_expr(value, records)?;
            }
        }
        IrStmt::Expr { expr, .. } => collect_record_field_uses_from_expr(expr, records)?,
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
    Ok(())
}

fn collect_record_field_uses_from_expr<'a>(
    expr: &'a IrExpr,
    records: &mut Vec<(&'a str, Vec<RecordFieldUse<'a>>)>,
) -> Result<(), String> {
    match expr {
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => {
            let IrExpr::Var { ty: base_ty, .. } = base.as_ref() else {
                return Err("member expression base must be a record variable".to_string());
            };
            let record_ty = if *is_arrow {
                record_pointer_pointee_type(base_ty).ok_or_else(|| {
                    format!(
                        "arrow member expression base has unsupported type {}",
                        type_label(base_ty)
                    )
                })?
            } else {
                base_ty
            };
            let IrTypeKind::Record { name, .. } = &record_ty.kind else {
                return Err(format!(
                    "member expression base has unsupported type {}",
                    type_label(record_ty)
                ));
            };
            add_record_field_use(records, name, field, ty)?;
            collect_record_field_uses_from_expr(base, records)?;
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_record_field_uses_from_expr(lhs, records)?;
            collect_record_field_uses_from_expr(rhs, records)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => {
            collect_record_field_uses_from_expr(operand, records)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_record_field_uses_from_expr(condition, records)?;
            collect_record_field_uses_from_expr(then_expr, records)?;
            collect_record_field_uses_from_expr(else_expr, records)?;
        }
        IrExpr::Index { base, index, .. } => {
            collect_record_field_uses_from_expr(base, records)?;
            collect_record_field_uses_from_expr(index, records)?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_record_field_uses_from_expr(element, records)?;
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_record_field_uses_from_expr(arg, records)?;
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

fn emit_global_const(global: &IrGlobal) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &global.ty.kind else {
        return Err(format!(
            "global {} has non-array type {}",
            global.name,
            type_label(&global.ty)
        ));
    };
    if !global.ty.is_const {
        return Err(format!("global {} is not readonly const", global.name));
    }
    let Some(len) = len else {
        return Err(format!("global {} array length is unknown", global.name));
    };
    let element_ty = emit_scalar_type(element)
        .map_err(|detail| format!("global {} element has {detail}", global.name))?;
    let values = match &global.init {
        IrGlobalInit::IntegerArray(values) => {
            if values.len() != *len {
                return Err(format!(
                    "global {} initializer length {} does not match array length {len}",
                    global.name,
                    values.len()
                ));
            }
            values
                .iter()
                .map(|value| emit_integer_literal(*value, element))
                .collect::<Result<Vec<_>, _>>()?
                .join(", ")
        }
        IrGlobalInit::Zeroed => {
            let zero = emit_integer_literal(0, element)?;
            return Ok(format!(
                "const {}: [{element_ty}; {len}] = [{zero}; {len}];\n",
                emit_global_const_identifier(&global.name)?
            ));
        }
    };
    Ok(format!(
        "const {}: [{element_ty}; {len}] = [{values}];\n",
        emit_global_const_identifier(&global.name)?
    ))
}

fn emit_return_type(ty: &IrType) -> Result<Option<String>, String> {
    if is_void_type(ty) {
        Ok(None)
    } else if let Some(pointee) = mutable_record_pointer_pointee_type(ty) {
        emit_value_type(pointee).map(|ty| Some(format!("&mut {ty}")))
    } else if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        Err(format!(
            "pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ))
    } else if let IrTypeKind::Record {
        fields: Some(_), ..
    } = &ty.kind
    {
        emit_value_type(ty).map(Some)
    } else {
        emit_scalar_type(ty).map(Some)
    }
}

fn emit_scalar_type(ty: &IrType) -> Result<String, String> {
    match &ty.kind {
        IrTypeKind::Integer { signed, width } => {
            if is_size_t_type(ty) {
                return Ok("usize".to_string());
            }
            match (*signed, *width) {
                (true, 8) => Ok("i8".to_string()),
                (true, 16) => Ok("i16".to_string()),
                (true, 32) => Ok("i32".to_string()),
                (true, 64) => Ok("i64".to_string()),
                (false, 8) => Ok("u8".to_string()),
                (false, 16) => Ok("u16".to_string()),
                (false, 32) => Ok("u32".to_string()),
                (false, 64) => Ok("u64".to_string()),
                _ => Err(format!("integer type {} is unsupported", type_label(ty))),
            }
        }
        IrTypeKind::Void => Err("void type is only supported as a return type".to_string()),
        IrTypeKind::Pointer { .. } => {
            Err(format!("pointer type {} is unsupported", type_label(ty)))
        }
        IrTypeKind::Array { .. } => Err(format!("array type {} is unsupported", type_label(ty))),
        IrTypeKind::Record { name, .. } => Err(format!("record type {name} is unsupported")),
        IrTypeKind::Function => Err(format!("function type {} is unsupported", type_label(ty))),
        IrTypeKind::Unsupported { reason } => {
            Err(format!("unsupported type {}: {reason}", type_label(ty)))
        }
    }
}

fn emit_fixed_array_type(ty: &IrType) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &ty.kind else {
        return Err(format!("type {} is not an array", type_label(ty)));
    };
    let Some(len) = len else {
        return Err(format!("array type {} has unknown length", type_label(ty)));
    };
    let element_ty =
        emit_scalar_type(element).map_err(|detail| format!("array element has {detail}"))?;
    Ok(format!("[{element_ty}; {len}]"))
}

fn emit_array_literal(
    elements: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &ty.kind else {
        return Err(format!("{path} type {} is not an array", type_label(ty)));
    };
    let Some(len) = len else {
        return Err(format!("{path} array length is unknown"));
    };
    if elements.len() != *len {
        return Err(format!(
            "{path} element count {} does not match array length {len}",
            elements.len()
        ));
    }
    emit_scalar_type(element).map_err(|detail| format!("{path} element has {detail}"))?;
    let emitted = elements
        .iter()
        .enumerate()
        .map(|(index, element_expr)| {
            validate_expr_matches_type(element_expr, element, &format!("{path} element[{index}]"))?;
            let emitted = emit_expr(element_expr, symbols, context)
                .map_err(|detail| format!("{path} element[{index}] {detail}"))?;
            Ok(emitted)
        })
        .collect::<Result<Vec<_>, String>>()?
        .join(", ");
    Ok(format!("[{emitted}]"))
}

#[derive(Clone, Copy, Debug)]
enum LoopContext<'a> {
    None,
    While,
    DoWhile { condition: &'a IrExpr },
    For { step: &'a IrStmt },
}

/// Emits one statement while enforcing symbol, type, and loop-context rules.
///
/// This is the statement-level semantic boundary for the generic emitter.
/// Every arm either proves the local lowering rule it needs or returns a
/// specific error; the caller prefixes those errors with the statement index so
/// evidence can point back to the rejected IR node.
fn emit_stmt(
    stmt: &IrStmt,
    return_type: &IrType,
    indent_level: usize,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    loop_context: LoopContext<'_>,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    match stmt {
        IrStmt::Decl { name, ty, init, .. } => {
            let decl_name = emit_identifier(name, "decl")?;
            if symbols.contains(name) {
                return Err(format!("decl {name} duplicates an existing symbol"));
            }
            if init.is_none() && context.byte_cursor_source(name).is_some() && is_u8_pointer(ty) {
                symbols.insert(name.clone());
                return Ok(format!("{indent}let mut {decl_name}: usize = 0;\n"));
            }
            if matches!(ty.kind, IrTypeKind::Array { .. }) {
                let decl_ty = emit_fixed_array_type(ty)
                    .map_err(|detail| format!("decl {name} has {detail}"))?;
                let Some(IrExpr::ArrayLiteral {
                    elements,
                    ty: literal_ty,
                    ..
                }) = init
                else {
                    return Err(format!(
                        "decl {name} array initializer must be an array literal"
                    ));
                };
                if literal_ty != ty {
                    return Err(format!(
                        "decl {name} array literal type {} does not match declared type {}",
                        type_label(literal_ty),
                        type_label(ty)
                    ));
                }
                let init = emit_array_literal(
                    elements,
                    ty,
                    symbols,
                    context,
                    &format!("decl {name} initializer"),
                )?;
                symbols.insert(name.clone());
                let mut_prefix = if context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            if matches!(ty.kind, IrTypeKind::Record { .. }) {
                let decl_ty =
                    emit_value_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
                let Some(init) = init else {
                    return Err(format!("decl {name} record initializer is required"));
                };
                validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                let init = emit_expr(init, symbols, context)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
                symbols.insert(name.clone());
                let mut_prefix = if context.is_assigned_var(name) {
                    "mut "
                } else {
                    ""
                };
                return Ok(format!(
                    "{indent}let {mut_prefix}{decl_name}: {decl_ty} = {init};\n"
                ));
            }
            let decl_ty =
                emit_scalar_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
            if let Some(init) = init {
                validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                let init = emit_expr(init, symbols, context)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
                symbols.insert(name.clone());
                Ok(format!(
                    "{indent}let mut {decl_name}: {decl_ty} = {init};\n"
                ))
            } else {
                symbols.insert(name.clone());
                Ok(format!("{indent}let mut {decl_name}: {decl_ty};\n"))
            }
        }
        IrStmt::Assign { target, value, .. } => {
            if is_byte_cursor_cast_assignment(target, value, symbols, context)? {
                return Ok(String::new());
            }
            let (target_name, target_ty) = emit_assignment_target(target, symbols, context)?;
            if count_post_increment_byte_reads(value) > 1 {
                return Err(
                    "assign value multiple post-increment byte reads are unsupported".to_string(),
                );
            }
            if let Some(compound_value) =
                emit_mutable_record_pointer_member_compound_assignment_value(
                    target,
                    value,
                    &target_name,
                    symbols,
                    context,
                )?
            {
                return Ok(format!("{indent}{target_name} = {compound_value};\n"));
            }
            if let Some(emitted) = emit_opaque_record_pointer_field_assignment_value(
                target,
                value,
                target_ty,
                symbols,
                context,
                "assign value",
            )? {
                return Ok(format!(
                    "{}{indent}{target_name} = {};\n",
                    emitted.prelude, emitted.expr
                ));
            }
            validate_expr_matches_type(value, target_ty, "assign value")?;
            let emitted =
                emit_expr_with_prelude(value, symbols, context, indent_level, "assign value")?;
            Ok(format!(
                "{}{indent}{target_name} = {};\n",
                emitted.prelude, emitted.expr
            ))
        }
        IrStmt::Return { value, .. } => match value {
            Some(value) => {
                if is_void_type(return_type) {
                    return Err("return value in void function".to_string());
                }
                if let Some(line) = emit_post_increment_deref_return(
                    value,
                    return_type,
                    indent_level,
                    symbols,
                    context,
                )? {
                    return Ok(line);
                }
                if let Some(line) = emit_mutable_record_pointer_identity_return(
                    value,
                    return_type,
                    indent_level,
                    symbols,
                    context,
                )? {
                    return Ok(line);
                }
                if count_post_increment_byte_reads(value) > 1 {
                    return Err("multiple post-increment byte reads are unsupported".to_string());
                }
                validate_expr_matches_type(value, return_type, "return expr")?;
                let emitted =
                    emit_expr_with_prelude(value, symbols, context, indent_level, "return expr")?;
                Ok(format!(
                    "{}{indent}return {};\n",
                    emitted.prelude, emitted.expr
                ))
            }
            None if is_void_type(return_type) => Ok(format!("{indent}return;\n")),
            None => Err("return without value in non-void function".to_string()),
        },
        IrStmt::Break { .. } => {
            if matches!(loop_context, LoopContext::None) {
                return Err("break outside loop".to_string());
            }
            Ok(format!("{indent}break;\n"))
        }
        IrStmt::Continue { .. } => match loop_context {
            LoopContext::None => Err("continue outside loop".to_string()),
            LoopContext::While => Ok(format!("{indent}continue;\n")),
            LoopContext::DoWhile { condition } => {
                let condition_break = emit_do_while_condition_break(
                    condition,
                    indent_level,
                    symbols,
                    context,
                    "continue condition",
                )?;
                Ok(format!("{condition_break}{indent}continue;\n"))
            }
            LoopContext::For { step } => {
                validate_for_step_stmt(step)?;
                let mut step_symbols = symbols.clone();
                let step_line = emit_stmt(
                    step,
                    return_type,
                    indent_level,
                    &mut step_symbols,
                    context,
                    LoopContext::None,
                )
                .map_err(|detail| format!("continue step {detail}"))?;
                Ok(format!("{step_line}{indent}continue;\n"))
            }
        },
        IrStmt::Expr { expr, .. } => {
            if let Some(line) = emit_c_memset_statement(expr, symbols, context)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            if let Some(line) = emit_c_memcpy_statement(expr, symbols, context)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            if let Some(line) = emit_prefix_inc_dec_statement(expr, symbols)
                .map_err(|detail| format!("expr {detail}"))?
            {
                return Ok(format!("{indent}{line}\n"));
            }
            let expr =
                emit_expr(expr, symbols, context).map_err(|detail| format!("expr {detail}"))?;
            Ok(format!("{indent}{expr};\n"))
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            let condition = emit_condition_expr(condition, symbols, context)
                .map_err(|detail| format!("if condition {detail}"))?;
            let mut block = String::new();
            block.push_str(&format!("{indent}if {condition} {{\n"));
            let mut then_symbols = symbols.clone();
            for (index, stmt) in then_body.iter().enumerate() {
                let line = emit_stmt(
                    stmt,
                    return_type,
                    indent_level + 1,
                    &mut then_symbols,
                    context,
                    loop_context,
                )
                .map_err(|detail| format!("if then[{index}].{detail}"))?;
                block.push_str(&line);
            }
            if else_body.is_empty() {
                block.push_str(&format!("{indent}}}\n"));
            } else {
                block.push_str(&format!("{indent}}} else {{\n"));
                let mut else_symbols = symbols.clone();
                for (index, stmt) in else_body.iter().enumerate() {
                    let line = emit_stmt(
                        stmt,
                        return_type,
                        indent_level + 1,
                        &mut else_symbols,
                        context,
                        loop_context,
                    )
                    .map_err(|detail| format!("if else[{index}].{detail}"))?;
                    block.push_str(&line);
                }
                block.push_str(&format!("{indent}}}\n"));
            }
            Ok(block)
        }
        IrStmt::While {
            condition, body, ..
        } => {
            if let Some(block) = emit_prefix_decrement_while_loop(
                condition,
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )? {
                return Ok(block);
            }
            if let Some(block) = emit_postfix_decrement_while_loop(
                condition,
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )? {
                return Ok(block);
            }
            let condition = emit_condition_expr(condition, symbols, context)
                .map_err(|detail| format!("while condition {detail}"))?;
            let mut loop_symbols = symbols.clone();
            let mut block = String::new();
            block.push_str(&format!("{indent}while {condition} {{\n"));
            for (index, stmt) in body.iter().enumerate() {
                let line = emit_stmt(
                    stmt,
                    return_type,
                    indent_level + 1,
                    &mut loop_symbols,
                    context,
                    LoopContext::While,
                )
                .map_err(|detail| format!("while body[{index}].{detail}"))?;
                block.push_str(&line);
            }
            block.push_str(&format!("{indent}}}\n"));
            Ok(block)
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => emit_do_while_stmt(body, condition, return_type, indent_level, symbols, context),
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => emit_for_stmt(
            init,
            condition.as_ref(),
            step.as_deref(),
            body,
            return_type,
            indent_level,
            symbols,
            context,
        ),
        IrStmt::Unsupported { node, reason, .. } => {
            Err(format!("unsupported statement {node}: {reason}"))
        }
    }
}

fn emit_do_while_stmt(
    body: &[IrStmt],
    condition: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    let mut loop_symbols = symbols.clone();
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::DoWhile { condition },
        )
        .map_err(|detail| format!("do while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&emit_do_while_condition_break(
        condition,
        indent_level + 1,
        symbols,
        context,
        "condition",
    )?);
    block.push_str(&format!("{indent}}}\n"));
    Ok(block)
}

fn emit_do_while_condition_break(
    condition: &IrExpr,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("do while {path} {detail}"))?;
    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    Ok(format!(
        "{indent}if !({condition}) {{\n{inner_indent}break;\n{indent}}}\n"
    ))
}

fn emit_for_stmt(
    init: &[IrStmt],
    condition: Option<&IrExpr>,
    step: Option<&IrStmt>,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let mut loop_symbols = symbols.clone();
    let mut block = String::new();
    block.push_str(&format!("{indent}{{\n"));

    for (index, init) in init.iter().enumerate() {
        validate_for_init_stmt(init)?;
        let line = emit_stmt(
            init,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::None,
        )
        .map_err(|detail| format!("for init[{index}] {detail}"))?;
        block.push_str(&line);
    }

    let condition = match condition {
        Some(condition) => emit_condition_expr(condition, &loop_symbols, context)
            .map_err(|detail| format!("for condition {detail}"))?,
        None => "true".to_string(),
    };
    block.push_str(&format!("{inner_indent}while {condition} {{\n"));

    let mut body_symbols = loop_symbols.clone();
    let body_loop_context = step
        .map(|step| LoopContext::For { step })
        .unwrap_or(LoopContext::While);
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 2,
            &mut body_symbols,
            context,
            body_loop_context,
        )
        .map_err(|detail| format!("for body[{index}].{detail}"))?;
        block.push_str(&line);
    }

    if let Some(step) = step {
        validate_for_step_stmt(step)?;
        let line = emit_stmt(
            step,
            return_type,
            indent_level + 2,
            &mut loop_symbols,
            context,
            LoopContext::None,
        )
        .map_err(|detail| format!("for step {detail}"))?;
        block.push_str(&line);
    }

    block.push_str(&format!("{inner_indent}}}\n"));
    block.push_str(&format!("{indent}}}\n"));
    Ok(block)
}

fn validate_for_init_stmt(stmt: &IrStmt) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { .. } | IrStmt::Assign { .. } => Ok(()),
        _ => Err("for init must be a Decl or Assign statement".to_string()),
    }
}

fn validate_for_step_stmt(stmt: &IrStmt) -> Result<(), String> {
    match stmt {
        IrStmt::Assign { .. } => Ok(()),
        _ => Err("for step must be an Assign statement".to_string()),
    }
}

fn emit_assignment_target<'a>(
    target: &'a IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<(String, &'a IrType), String> {
    match target {
        IrExpr::Var { name, ty, .. } => {
            if !symbols.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            let name = emit_identifier(name, "assign target")?;
            Ok((name, ty))
        }
        IrExpr::Index {
            base, index, ty, ..
        } => {
            let target = emit_index_assignment_target(base, index, ty, symbols, context)?;
            Ok((target, ty))
        }
        IrExpr::Deref { ptr, ty, .. } => {
            let target = emit_mutable_pointer_deref_assignment_target(ptr, ty, symbols, context)?;
            Ok((target, ty))
        }
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => {
            if *is_arrow {
                let target = emit_mutable_record_pointer_member_assignment_target(
                    base, field, ty, symbols, context,
                )?;
                return Ok((target, ty));
            }
            let target = emit_member_expr(base, field, ty, *is_arrow, symbols, context)?;
            Ok((target, ty))
        }
        _ => Err(
            "assign target must be Var, local fixed array Index, pointer Deref, or by-value record Member"
                .to_string(),
        ),
    }
}

fn emit_mutable_record_pointer_identity_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if mutable_record_pointer_pointee_type(return_type).is_none() {
        return Ok(None);
    }
    let IrExpr::Var { name, ty, .. } = value else {
        return Err(
            "mutable record pointer return must return the owned record pointer parameter"
                .to_string(),
        );
    };
    if ty != return_type {
        return Err(format!(
            "mutable record pointer return type {} does not match function return type {}",
            type_label(ty),
            type_label(return_type)
        ));
    }
    if !symbols.contains(name) {
        return Err(format!(
            "mutable record pointer return value {name} is not declared"
        ));
    }
    if !context.is_mutable_record_pointer_write_param(name) {
        return Err(format!(
            "mutable record pointer return {name} requires mutable record pointer ownership evidence"
        ));
    }
    let indent = "    ".repeat(indent_level);
    let name = emit_identifier(name, "mutable record pointer return value")?;
    Ok(Some(format!("{indent}return {name};\n")))
}

fn emit_mutable_record_pointer_member_assignment_target(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("arrow member assignment base must be a record pointer variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!(
            "arrow member assignment base {base_name} is not declared"
        ));
    }
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Err(format!(
            "arrow member assignment base {base_name} requires mutable record pointer ownership evidence"
        ));
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member assignment base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_record_field_type(ty)
        .map_err(|detail| format!("mutable record pointer arrow field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "arrow member assignment base")?;
    let field = emit_identifier(field, "arrow member assignment field")?;
    Ok(format!("{base_name}.{field}"))
}

fn emit_mutable_record_pointer_member_compound_assignment_value(
    target: &IrExpr,
    value: &IrExpr,
    emitted_target: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = value
    else {
        return Ok(None);
    };
    if !same_direct_mutable_record_pointer_member(lhs, target, context)? {
        return Ok(None);
    }
    if let Some(reason) = mutable_record_pointer_field_compound_rhs_rejection_reason(rhs) {
        return Err(reason);
    }
    let op_token = emit_binary_op(op)?;
    validate_binary_operand_types(op_token, lhs, rhs, ty)?;
    validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)?;
    let rhs = emit_expr(rhs, symbols, context).map_err(|detail| {
        format!("mutable record pointer field compound assignment RHS {detail}")
    })?;
    Ok(Some(emit_binary_result_expr(
        op,
        op_token,
        emitted_target,
        &rhs,
        ty,
    )))
}

fn emit_opaque_record_pointer_field_assignment_value(
    target: &IrExpr,
    value: &IrExpr,
    target_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<Option<EmittedExpr>, String> {
    let Some(target_pointer_ty) = emit_opaque_void_pointer_type(target_ty) else {
        return Ok(None);
    };
    let Some((base_name, _, _, _)) =
        direct_mutable_record_pointer_opaque_member_parts(target, context)?
    else {
        return Err(format!(
            "{path} opaque pointer field target requires direct mutable record pointer ownership evidence"
        ));
    };
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Err(format!(
            "{path} opaque pointer field target {base_name} requires mutable record pointer ownership evidence"
        ));
    }
    let expr = match value {
        IrExpr::Var { .. } => emit_opaque_record_pointer_field_value_var(
            value,
            &target_pointer_ty,
            symbols,
            context,
            path,
        )?,
        IrExpr::Cast {
            target: cast_target,
            expr,
            ..
        } => {
            let cast_target_ty = emit_opaque_void_pointer_type(cast_target).ok_or_else(|| {
                format!(
                    "{path} opaque pointer cast target {} is unsupported",
                    type_label(cast_target)
                )
            })?;
            if cast_target_ty != target_pointer_ty {
                return Err(format!(
                    "{path} opaque pointer cast target {cast_target_ty} does not match field type {target_pointer_ty}"
                ));
            }
            let source_ty = expr_type(expr)
                .ok_or_else(|| format!("{path} opaque pointer cast source type is unsupported"))?;
            let source_pointer_ty = emit_opaque_void_pointer_type(source_ty).ok_or_else(|| {
                format!(
                    "{path} opaque pointer cast source {} is unsupported",
                    type_label(source_ty)
                )
            })?;
            let expr = emit_opaque_record_pointer_field_value_var(
                expr,
                &source_pointer_ty,
                symbols,
                context,
                &format!("{path} opaque pointer cast source"),
            )?;
            format!("({expr} as {target_pointer_ty})")
        }
        _ => {
            return Err(format!(
                "{path} opaque pointer field write requires an opaque pointer param value or opaque pointer cast"
            ))
        }
    };
    Ok(Some(EmittedExpr {
        prelude: String::new(),
        expr,
    }))
}

fn emit_opaque_record_pointer_field_value_var(
    expr: &IrExpr,
    expected_pointer_ty: &str,
    symbols: &HashSet<String>,
    context: &EmitContext,
    path: &str,
) -> Result<String, String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        let source_ty = expr_type(expr).ok_or_else(|| format!("{path} type is unsupported"))?;
        return Err(format!("{path} {} is unsupported", type_label(source_ty)));
    };
    if !symbols.contains(name) {
        return Err(format!("{path} {name} is not declared"));
    }
    if !context.is_opaque_record_pointer_field_value_param(name) {
        return Err(format!(
            "{path} {name} requires opaque record pointer field value evidence"
        ));
    }
    let source_pointer_ty = emit_opaque_void_pointer_type(ty)
        .ok_or_else(|| format!("{path} {} is unsupported", type_label(ty)))?;
    if source_pointer_ty != expected_pointer_ty {
        return Err(format!(
            "{path} type {source_pointer_ty} does not match expected type {expected_pointer_ty}"
        ));
    }
    emit_identifier(name, "opaque pointer field value")
}

fn direct_mutable_record_pointer_opaque_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_opaque_void_pointer_type(ty).ok_or_else(|| {
        format!(
            "mutable record pointer opaque field {base}.{field} has unsupported type {}",
            type_label(ty)
        )
    })?;
    Ok(Some((base, base_ty, field, ty)))
}

fn same_direct_mutable_record_pointer_member(
    lhs: &IrExpr,
    target: &IrExpr,
    context: &EmitContext,
) -> Result<bool, String> {
    let Some((target_base, target_base_ty, target_field, target_ty)) =
        direct_mutable_record_pointer_member_parts(target, context)?
    else {
        return Ok(false);
    };
    let Some((lhs_base, lhs_base_ty, lhs_field, lhs_ty)) =
        direct_mutable_record_pointer_member_parts(lhs, context)?
    else {
        return Ok(false);
    };
    Ok(target_base == lhs_base
        && target_base_ty == lhs_base_ty
        && target_field == lhs_field
        && target_ty == lhs_ty)
}

fn direct_mutable_record_pointer_member_parts<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let Some((base, base_ty, field, ty)) =
        direct_mutable_record_pointer_member_parts_any_field(expr, context)?
    else {
        return Ok(None);
    };
    emit_scalar_type(ty).map_err(|detail| {
        format!("mutable record pointer field compound assignment field {field} has {detail}")
    })?;
    Ok(Some((base, base_ty, field, ty)))
}

fn direct_mutable_record_pointer_member_parts_any_field<'a>(
    expr: &'a IrExpr,
    context: &EmitContext,
) -> Result<Option<(&'a str, &'a IrType, &'a str, &'a IrType)>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if !context.is_mutable_record_pointer_write_param(name) {
        return Ok(None);
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "mutable record pointer field compound assignment base {name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    Ok(Some((name.as_str(), base_ty, field.as_str(), ty)))
}

fn mutable_record_pointer_field_compound_rhs_rejection_reason(value: &IrExpr) -> Option<String> {
    match value {
        IrExpr::Var { ty, .. } | IrExpr::LitInt { ty, .. } => {
            if is_integer_type(ty) {
                None
            } else {
                Some(format!(
                    "mutable record pointer field compound assignment RHS must be a simple integer variable, literal, or integral cast; got {}",
                    type_label(ty)
                ))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Some(format!(
                    "mutable record pointer field compound assignment RHS cast target must be an integer; got {}",
                    type_label(target)
                ));
            }
            mutable_record_pointer_field_compound_rhs_rejection_reason(expr)
        }
        IrExpr::Unsupported { node, reason, .. } => Some(format!(
            "mutable record pointer field compound assignment RHS uses unsupported expression {node}: {reason}"
        )),
        _ => Some(
            "mutable record pointer field compound assignment RHS must be a simple integer variable, literal, or integral cast"
                .to_string(),
        ),
    }
}

fn emit_index_assignment_target(
    base: &IrExpr,
    index: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("assign index base must be Var".to_string());
    };
    if context.readonly_global(base_name).is_some() {
        return Err(format!(
            "assign index base {base_name} is a readonly global"
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!("assign index base {base_name} is not declared"));
    }
    if base_ty.is_const {
        return Err(format!(
            "assign index base {base_name} has const type {}",
            type_label(base_ty)
        ));
    }
    let element_ty = fixed_integer_array_element_type(base_ty)
        .or_else(|| mutable_pointer_slice_element_type(base_ty))
        .ok_or_else(|| {
            format!(
                "assign index base {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("assign index element has {detail}"))?;
    let result_ty =
        emit_scalar_type(ty).map_err(|detail| format!("assign index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "assign index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    let index_ty =
        expr_type(index).ok_or_else(|| "assign index operand type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "assign index operand type {} is unsupported",
            type_label(index_ty)
        ));
    }
    let base = emit_identifier(base_name, "assign index base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("assign index operand {detail}"))?;
    Ok(format!("{base}[{index} as usize]"))
}

fn emit_mutable_pointer_deref_assignment_target(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(target) =
        emit_mutable_pointer_add_deref_assignment_target(ptr, ty, symbols, context)?
    {
        return Ok(target);
    }
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Err("deref assignment pointer must be Var".to_string());
    };
    if !symbols.contains(ptr_name) {
        return Err(format!(
            "deref assignment pointer {ptr_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereference-assigned in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "deref assignment pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("deref assignment element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("deref assignment result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref assignment result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "deref assignment pointer")?;
    Ok(format!("{ptr_name}[0usize]"))
}

fn emit_mutable_pointer_add_deref_assignment_target(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: add_ty,
        ..
    } = ptr
    else {
        return Ok(None);
    };
    let Some((base, index)) = mutable_pointer_add_operands(lhs, rhs) else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("deref pointer add assignment base must be Var".to_string());
    };
    if add_ty != base_ty {
        return Err(format!(
            "deref pointer add assignment result type {} does not match base type {}",
            type_label(add_ty),
            type_label(base_ty)
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!(
            "deref pointer add assignment base {base_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(base_name) {
        return Err(format!(
            "nullable pointer param {base_name} cannot be offset-dereference-assigned in the bounded emitter"
        ));
    }
    let element_ty = mutable_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "deref pointer add assignment base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("deref assignment element has {detail}"))?;
    let deref_ty =
        emit_scalar_type(ty).map_err(|detail| format!("deref assignment result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref assignment result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let index_ty = expr_type(index)
        .ok_or_else(|| "deref pointer add index type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "deref pointer add index type {} is unsupported",
            type_label(index_ty)
        ));
    }
    validate_readonly_pointer_add_index_expr(index)?;
    let base = emit_identifier(base_name, "deref pointer add assignment base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("deref pointer add index {detail}"))?;
    Ok(Some(format!("{base}[{index} as usize]")))
}

fn emit_postfix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition decrement target")?;
    let counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition decrement step {detail}"))?;
    let snapshot = emit_identifier(
        &first_available_temp_name(&format!("{name}_before_dec"), symbols),
        "while condition decrement snapshot",
    )?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}let {snapshot}: {counter_ty} = {name};\n"
    ));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {snapshot} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::While,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}

fn emit_prefix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: true,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition prefix decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition prefix decrement target")?;
    let _counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition prefix decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition prefix decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition prefix decrement step {detail}"))?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {name} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
            LoopContext::While,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}

fn emit_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match expr {
        IrExpr::LitInt { value, ty, .. } => emit_integer_literal(*value, ty),
        IrExpr::NullPtr { .. } => {
            Err("null pointer literal is only supported in pointer null comparisons".to_string())
        }
        IrExpr::Var { name, ty, .. } => {
            if let Some(global) = context.readonly_global(name) {
                validate_global_expr_type(global, ty)?;
                return context.global_rust_name(name);
            }
            if !symbols.contains(name) {
                return Err(format!("var {name} is not declared"));
            }
            emit_value_type(ty).map_err(|detail| format!("var {name} has {detail}"))?;
            emit_identifier(name, "var")
        }
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            if let Some(expr) = emit_short_circuit_value_expr(op, lhs, rhs, ty, symbols, context)? {
                return Ok(expr);
            }
            if let Some(expr) = emit_comparison_value_expr(op, lhs, rhs, ty, symbols, context)? {
                return Ok(expr);
            }
            let op_token = emit_binary_op(op)?;
            validate_binary_operand_types(op_token, lhs, rhs, ty)?;
            validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)?;
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("binary rhs {detail}"))?;
            Ok(emit_binary_result_expr(op, op_token, &lhs, &rhs, ty))
        }
        IrExpr::Unary {
            op, operand, ty, ..
        } => match op {
            IrUnOp::Neg => {
                validate_signed_unary_minus_operand(operand, ty)?;
                let operand = emit_expr(operand, symbols, context)
                    .map_err(|detail| format!("unary minus operand {detail}"))?;
                Ok(format!("(-{operand})"))
            }
            IrUnOp::Not => emit_logical_not_value_expr(operand, ty, symbols, context),
            IrUnOp::BitNot => {
                validate_expr_matches_type(operand, ty, "bitnot operand")?;
                let operand = emit_expr(operand, symbols, context)
                    .map_err(|detail| format!("bitnot operand {detail}"))?;
                Ok(format!("!{operand}"))
            }
        },
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
            ..
        } => emit_conditional_value_expr(condition, then_expr, else_expr, ty, symbols, context),
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!("cast target {} is unsupported", type_label(target)));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| "cast source type is unsupported".to_string())?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target =
                emit_scalar_type(target).map_err(|detail| format!("cast target has {detail}"))?;
            let expr = emit_expr(expr, symbols, context)
                .map_err(|detail| format!("cast expr {detail}"))?;
            Ok(format!("({expr} as {target})"))
        }
        IrExpr::Index {
            base, index, ty, ..
        } => emit_index_expr(base, index, ty, symbols, context),
        IrExpr::Member {
            base,
            field,
            ty,
            is_arrow,
            ..
        } => emit_member_expr(base, field, ty, *is_arrow, symbols, context),
        IrExpr::ArrayLiteral { .. } => Err(
            "array literal expression is only supported as a declaration initializer".to_string(),
        ),
        IrExpr::Call {
            callee, args, ty, ..
        } => emit_call_expr(callee, args, ty, symbols, context),
        IrExpr::IncDec { .. } => Err("inc/dec expression is unsupported".to_string()),
        IrExpr::Deref { ptr, ty, .. } => {
            emit_readonly_pointer_deref_expr(ptr, ty, symbols, context)
        }
        IrExpr::AddrOf { .. } => Err("address-of expression is unsupported".to_string()),
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported expression {node}: {reason}"))
        }
    }
}

fn emit_readonly_pointer_deref_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(expr) = emit_readonly_pointer_add_deref_expr(ptr, ty, symbols, context)? {
        return Ok(expr);
    }
    let IrExpr::Var {
        name: ptr_name,
        ty: ptr_ty,
        ..
    } = ptr
    else {
        return Err("deref pointer must be Var".to_string());
    };
    if !symbols.contains(ptr_name) {
        return Err(format!("deref pointer {ptr_name} is not declared"));
    }
    if context.is_nullable_pointer_param(ptr_name) {
        return Err(format!(
            "nullable pointer param {ptr_name} cannot be dereferenced in the bounded emitter"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(ptr_ty).ok_or_else(|| {
        format!(
            "deref pointer {ptr_name} has unsupported type {}",
            type_label(ptr_ty)
        )
    })?;
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("deref element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let ptr_name = emit_identifier(ptr_name, "deref pointer")?;
    Ok(format!("{ptr_name}[0usize]"))
}

fn emit_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    is_arrow: bool,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if is_arrow {
        if let Some(expr) =
            emit_mutable_record_pointer_member_expr(base, field, ty, symbols, context)?
        {
            return Ok(expr);
        }
        return emit_readonly_record_pointer_member_expr(base, field, ty, symbols, context);
    }
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("member expression base must be a record variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!("member base {base_name} is not declared"));
    }
    if !matches!(base_ty.kind, IrTypeKind::Record { .. }) {
        return Err(format!(
            "member base {base_name} has unsupported type {}",
            type_label(base_ty)
        ));
    }
    emit_scalar_type(ty).map_err(|detail| format!("member field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "member base")?;
    let field = emit_identifier(field, "member field")?;
    Ok(format!("{base_name}.{field}"))
}

fn emit_mutable_record_pointer_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Ok(None);
    };
    if !context.is_mutable_record_pointer_write_param(base_name) {
        return Ok(None);
    }
    if !symbols.contains(base_name) {
        return Err(format!("arrow member base {base_name} is not declared"));
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_scalar_type(ty)
        .map_err(|detail| format!("mutable arrow member field {field} has {detail}"))?;
    if !context.is_mutable_record_pointer_read_field(base_name, field) {
        return Err(format!(
            "mutable record pointer field {base_name}.{field} lacks definite assignment evidence"
        ));
    }
    let base_name = emit_identifier(base_name, "mutable arrow member base")?;
    let field = emit_identifier(field, "mutable arrow member field")?;
    Ok(Some(format!("{base_name}.{field}")))
}

fn emit_readonly_record_pointer_member_expr(
    base: &IrExpr,
    field: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("arrow member expression base must be a record pointer variable".to_string());
    };
    if !symbols.contains(base_name) {
        return Err(format!("arrow member base {base_name} is not declared"));
    }
    readonly_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "arrow member base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    emit_scalar_type(ty).map_err(|detail| format!("arrow member field {field} has {detail}"))?;
    let base_name = emit_identifier(base_name, "arrow member base")?;
    let field = emit_identifier(field, "arrow member field")?;
    if context.is_nullable_pointer_param(&base_name) {
        return Ok(format!("{base_name}.unwrap().{field}"));
    }
    Ok(format!("{base_name}.{field}"))
}

fn emit_readonly_pointer_add_deref_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Binary {
        op: IrBinOp::Add,
        lhs,
        rhs,
        ty: add_ty,
        ..
    } = ptr
    else {
        return Ok(None);
    };
    let Some((base, index)) = readonly_pointer_add_operands(lhs, rhs) else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("deref pointer add base must be Var".to_string());
    };
    if add_ty != base_ty {
        return Err(format!(
            "deref pointer add result type {} does not match base type {}",
            type_label(add_ty),
            type_label(base_ty)
        ));
    }
    if !symbols.contains(base_name) {
        return Err(format!(
            "deref pointer add base {base_name} is not declared"
        ));
    }
    if context.is_nullable_pointer_param(base_name) {
        return Err(format!(
            "nullable pointer param {base_name} cannot be offset-dereferenced in the bounded emitter"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(base_ty).ok_or_else(|| {
        format!(
            "deref pointer add base {base_name} has unsupported type {}",
            type_label(base_ty)
        )
    })?;
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("deref element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "deref result type {deref_ty} does not match pointer element type {element_ty}"
        ));
    }
    let index_ty = expr_type(index)
        .ok_or_else(|| "deref pointer add index type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "deref pointer add index type {} is unsupported",
            type_label(index_ty)
        ));
    }
    validate_readonly_pointer_add_index_expr(index)?;
    let base = emit_identifier(base_name, "deref pointer add base")?;
    let index = emit_expr(index, symbols, context)
        .map_err(|detail| format!("deref pointer add index {detail}"))?;
    Ok(Some(format!("{base}[{index} as usize]")))
}

fn validate_readonly_pointer_add_index_expr(expr: &IrExpr) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } | IrExpr::Var { ty, .. } => {
            if is_integer_type(ty) {
                Ok(())
            } else {
                Err(format!(
                    "deref pointer add index type {} is unsupported",
                    type_label(ty)
                ))
            }
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "deref pointer add index cast target {} is unsupported",
                    type_label(target)
                ));
            }
            validate_readonly_pointer_add_index_expr(expr)
        }
        IrExpr::Call { callee, .. } => Err(format!(
            "deref pointer add index call expression {callee} is unsupported"
        )),
        IrExpr::Conditional { .. } => {
            Err("deref pointer add index cannot use conditional expression".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("deref pointer add index cannot use increment/decrement".to_string())
        }
        IrExpr::Deref { .. } => Err("deref pointer add index cannot use dereference".to_string()),
        IrExpr::Binary { .. } => {
            Err("deref pointer add index cannot use compound expression".to_string())
        }
        IrExpr::Unary { .. } => {
            Err("deref pointer add index cannot use unary expression".to_string())
        }
        IrExpr::Index { .. } => {
            Err("deref pointer add index cannot use index expression".to_string())
        }
        IrExpr::Member { .. } => {
            Err("deref pointer add index cannot use member expression".to_string())
        }
        IrExpr::AddrOf { .. } => {
            Err("deref pointer add index cannot use address-of expression".to_string())
        }
        IrExpr::NullPtr { .. } => {
            Err("deref pointer add index cannot use null pointer".to_string())
        }
        IrExpr::ArrayLiteral { .. } => {
            Err("deref pointer add index cannot use array literal".to_string())
        }
        IrExpr::Unsupported { node, reason, .. } => Err(format!(
            "deref pointer add index unsupported expression {node}: {reason}"
        )),
    }
}

fn readonly_pointer_add_operands<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a IrExpr, &'a IrExpr)> {
    match (expr_type(lhs), expr_type(rhs)) {
        (Some(lhs_ty), Some(rhs_ty))
            if readonly_pointer_slice_element_type(lhs_ty).is_some() && is_integer_type(rhs_ty) =>
        {
            Some((lhs, rhs))
        }
        (Some(lhs_ty), Some(rhs_ty))
            if is_integer_type(lhs_ty) && readonly_pointer_slice_element_type(rhs_ty).is_some() =>
        {
            Some((rhs, lhs))
        }
        _ => None,
    }
}

fn mutable_pointer_add_operands<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a IrExpr, &'a IrExpr)> {
    match (expr_type(lhs), expr_type(rhs)) {
        (Some(lhs_ty), Some(rhs_ty))
            if mutable_pointer_slice_element_type(lhs_ty).is_some() && is_integer_type(rhs_ty) =>
        {
            Some((lhs, rhs))
        }
        (Some(lhs_ty), Some(rhs_ty))
            if is_integer_type(lhs_ty) && mutable_pointer_slice_element_type(rhs_ty).is_some() =>
        {
            Some((rhs, lhs))
        }
        _ => None,
    }
}

fn emit_call_expr(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let callee = emit_identifier(callee, "call callee")?;
    if callee == "assert" {
        return emit_c_assert_call_expr(args, ty, symbols, context);
    }
    if callee == "abs" {
        return emit_c_abs_call_expr(args, ty, symbols, context);
    }
    if callee == "strlen" {
        return emit_c_strlen_call_expr(args, ty, symbols, context);
    }
    if callee == "strnlen" {
        return emit_c_strnlen_call_expr(args, ty, symbols, context);
    }
    if callee == "memcmp" {
        return emit_c_memcmp_call_expr(args, ty, symbols, context);
    }
    if reserved_c_macro_or_stdlib_callee(&callee) {
        return Err(format!(
            "call callee \"{callee}\" is reserved C macro/stdlib/extern surface and requires explicit lowering or extern binding"
        ));
    }
    if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
        return Err(format!(
            "call result has pointer value return {} requires explicit ownership/lifetime/ABI lowering",
            type_label(ty)
        ));
    }
    if !is_void_type(ty) {
        emit_scalar_type(ty).map_err(|detail| format!("call result has {detail}"))?;
    }
    validate_bounded_call_args(args)?;
    let args = args
        .iter()
        .enumerate()
        .map(|(index, arg)| {
            emit_expr(arg, symbols, context).map_err(|detail| format!("call arg[{index}] {detail}"))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    Ok(format!("{callee}({args})"))
}

fn emit_c_assert_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_void_type(ty) {
        return Err(format!(
            "C assert model requires void result type, got {}",
            type_label(ty)
        ));
    }
    let [condition] = args else {
        return Err(format!(
            "C assert model requires exactly one condition argument, got {}",
            args.len()
        ));
    };
    validate_bounded_call_arg(condition, false)
        .map_err(|detail| format!("C assert condition {detail}"))?;
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("C assert condition {detail}"))?;
    Ok(format!("assert!({condition})"))
}

fn emit_c_abs_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_c_int_type(ty) {
        return Err(format!(
            "C abs(int) model requires i32 result type, got {}",
            type_label(ty)
        ));
    }
    let [arg] = args else {
        return Err(format!(
            "C abs(int) model requires exactly one i32 argument, got {}",
            args.len()
        ));
    };
    validate_bounded_call_arg(arg, false).map_err(|detail| format!("C abs argument {detail}"))?;
    let arg_ty = expr_type(arg).ok_or_else(|| "C abs argument type is unsupported".to_string())?;
    if !is_c_int_type(arg_ty) {
        return Err(format!(
            "C abs(int) argument must be i32, got {}",
            type_label(arg_ty)
        ));
    }
    let arg =
        emit_expr(arg, symbols, context).map_err(|detail| format!("C abs argument {detail}"))?;
    Ok(format!(
        "{arg}.checked_abs().expect(\"C abs(int) precondition violated\")"
    ))
}

fn emit_c_strlen_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    _context: &EmitContext,
) -> Result<String, String> {
    let name = validate_c_strlen_call_shape(args, ty)?;
    let name = emit_identifier(name, "C strlen argument")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C strlen argument {name} is not a function parameter or local binding"
        ));
    }
    Ok(format!(
        "{name}.iter().position(|&byte| byte == 0).expect(\"C strlen precondition violated\")"
    ))
}

fn validate_c_strlen_call_shape<'a>(args: &'a [IrExpr], ty: &IrType) -> Result<&'a str, String> {
    if !is_c_strlen_result_type(ty) {
        return Err(format!(
            "C strlen model requires size_t/usize result type, got {}",
            type_label(ty)
        ));
    }
    let [arg] = args else {
        return Err(format!(
            "C strlen model requires exactly one string pointer argument, got {}",
            args.len()
        ));
    };
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err("C strlen argument must be a direct readonly pointer parameter".to_string());
    };
    let pointee = readonly_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "C strlen argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "C strlen argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}

fn emit_c_strnlen_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let (name, max) = validate_c_strnlen_call_shape(args, ty)?;
    let name = emit_identifier(name, "C strnlen argument")?;
    if !symbols.contains(&name) {
        return Err(format!(
            "C strnlen argument {name} is not a function parameter or local binding"
        ));
    }
    let max =
        emit_expr(max, symbols, context).map_err(|detail| format!("C strnlen size {detail}"))?;
    Ok(format!(
        "{{ let bytes = {name}.get(..({max} as usize)).expect(\"C strnlen precondition violated\"); bytes.iter().position(|&byte| byte == 0).unwrap_or(bytes.len()) }}"
    ))
}

fn validate_c_strnlen_call_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a IrExpr), String> {
    if !is_c_strlen_result_type(ty) {
        return Err(format!(
            "C strnlen model requires size_t/usize result type, got {}",
            type_label(ty)
        ));
    }
    let [arg, max] = args else {
        return Err(format!(
            "C strnlen model requires exactly one string pointer and one size argument, got {}",
            args.len()
        ));
    };
    let name = validate_direct_readonly_8_bit_pointer_arg(arg, "C strnlen")?;
    let max_ty =
        expr_type(max).ok_or_else(|| "C strnlen size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(max_ty) {
        return Err(format!(
            "C strnlen size argument must be size_t/usize, got {}",
            type_label(max_ty)
        ));
    }
    validate_bounded_call_arg(max, false).map_err(|detail| format!("C strnlen size {detail}"))?;
    Ok((name, max))
}

fn emit_c_memcmp_call_expr(
    args: &[IrExpr],
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let (left, right, count) = validate_c_memcmp_call_shape(args, ty)?;
    let left = emit_identifier(left, "C memcmp left argument")?;
    let right = emit_identifier(right, "C memcmp right argument")?;
    if !symbols.contains(&left) {
        return Err(format!(
            "C memcmp left argument {left} is not a function parameter or local binding"
        ));
    }
    if !symbols.contains(&right) {
        return Err(format!(
            "C memcmp right argument {right} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memcmp size {detail}"))?;
    Ok(format!(
        "{{ let left_bytes = {left}.get(..({count} as usize)).expect(\"C memcmp precondition violated\"); let right_bytes = {right}.get(..({count} as usize)).expect(\"C memcmp precondition violated\"); left_bytes.iter().zip(right_bytes.iter()).find_map(|(&left_byte, &right_byte)| ((left_byte as u8) != (right_byte as u8)).then_some(((left_byte as u8) as i32) - ((right_byte as u8) as i32))).unwrap_or(0) }}"
    ))
}

fn validate_c_memcmp_call_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a str, &'a IrExpr), String> {
    if !is_c_int_type(ty) {
        return Err(format!(
            "C memcmp model requires i32 result type, got {}",
            type_label(ty)
        ));
    }
    let [left, right, count] = args else {
        return Err(format!(
            "C memcmp model requires exactly two readonly byte pointers and one size argument, got {}",
            args.len()
        ));
    };
    let left = validate_direct_readonly_8_bit_pointer_arg(left, "C memcmp left")?;
    let right = validate_direct_readonly_8_bit_pointer_arg(right, "C memcmp right")?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memcmp size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memcmp size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memcmp size {detail}"))?;
    Ok((left, right, count))
}

fn validate_direct_readonly_8_bit_pointer_arg<'a>(
    arg: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err(format!(
            "{context} argument must be a direct readonly pointer parameter"
        ));
    };
    let pointee = readonly_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "{context} argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_8_bit_integer_type(pointee) {
        return Err(format!(
            "{context} argument must be a readonly 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}

fn emit_c_memset_statement(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Call {
        callee, args, ty, ..
    } = expr
    else {
        return Ok(None);
    };
    if callee != "memset" {
        return Ok(None);
    }
    let (dest, byte, count) = validate_c_memset_statement_shape(args, ty)?;
    let dest = emit_identifier(dest, "C memset destination")?;
    if !symbols.contains(&dest) {
        return Err(format!(
            "C memset destination {dest} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memset size {detail}"))?;
    Ok(Some(format!(
        "{dest}.get_mut(..({count} as usize)).expect(\"C memset precondition violated\").fill({byte}u8);"
    )))
}

fn emit_c_memcpy_statement(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Call {
        callee, args, ty, ..
    } = expr
    else {
        return Ok(None);
    };
    if callee != "memcpy" {
        return Ok(None);
    }
    let (dest, src, count) = validate_c_memcpy_statement_shape(args, ty)?;
    let dest = emit_identifier(dest, "C memcpy destination")?;
    let src = emit_identifier(src, "C memcpy source")?;
    if !symbols.contains(&dest) {
        return Err(format!(
            "C memcpy destination {dest} is not a function parameter or local binding"
        ));
    }
    if !symbols.contains(&src) {
        return Err(format!(
            "C memcpy source {src} is not a function parameter or local binding"
        ));
    }
    let count =
        emit_expr(count, symbols, context).map_err(|detail| format!("C memcpy size {detail}"))?;
    Ok(Some(format!(
        "{dest}.get_mut(..({count} as usize)).expect(\"C memcpy destination precondition violated\").copy_from_slice({src}.get(..({count} as usize)).expect(\"C memcpy source precondition violated\"));"
    )))
}

fn emit_prefix_inc_dec_statement(
    expr: &IrExpr,
    symbols: &HashSet<String>,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op,
        prefix: true,
        ty,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!("prefix inc/dec target {name} is not declared"));
    }
    if target_ty != ty {
        return Err(format!(
            "prefix inc/dec target {name} type {} does not match result type {}",
            type_label(target_ty),
            type_label(ty)
        ));
    }
    if !is_integer_type(target_ty) {
        return Err(format!(
            "prefix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        ));
    }

    let name = emit_identifier(name, "prefix inc/dec target")?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("prefix inc/dec step {detail}"))?;
    let bin_op = match op {
        IrIncDecOp::Inc => IrBinOp::Add,
        IrIncDecOp::Dec => IrBinOp::Sub,
    };
    let rhs = if let Some(method) = unsigned_wrapping_method(&bin_op, target_ty) {
        format!("{name}.{method}({one})")
    } else if let Some((method, message)) = signed_checked_method(&bin_op, target_ty) {
        format!("{name}.{method}({one}).expect(\"{message}\")")
    } else {
        return Err(format!(
            "prefix inc/dec target {name} has unsupported type {}",
            type_label(target_ty)
        ));
    };
    Ok(Some(format!("{name} = {rhs};")))
}

fn validate_c_memset_statement_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, u8, &'a IrExpr), String> {
    if !is_c_memset_discarded_result_type(ty) {
        return Err(format!(
            "C memset statement model requires void or discarded void * result type, got {}",
            type_label(ty)
        ));
    }
    let [dest, value, count] = args else {
        return Err(format!(
            "C memset statement model requires destination, byte value, and size arguments, got {}",
            args.len()
        ));
    };
    let dest = validate_direct_mutable_unsigned_8_bit_pointer_arg(dest, "C memset destination")?;
    let byte = validate_c_memset_byte_value(value)?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memset size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memset size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memset size {detail}"))?;
    Ok((dest, byte, count))
}

fn validate_c_memcpy_statement_shape<'a>(
    args: &'a [IrExpr],
    ty: &IrType,
) -> Result<(&'a str, &'a str, &'a IrExpr), String> {
    if !is_c_memcpy_discarded_result_type(ty) {
        return Err(format!(
            "C memcpy statement model requires void or discarded void * result type, got {}",
            type_label(ty)
        ));
    }
    let [dest, src, count] = args else {
        return Err(format!(
            "C memcpy statement model requires destination, source, and size arguments, got {}",
            args.len()
        ));
    };
    let dest = validate_direct_mutable_unsigned_8_bit_pointer_arg(dest, "C memcpy destination")?;
    let src = validate_direct_readonly_8_bit_pointer_arg(src, "C memcpy source")?;
    let count_ty =
        expr_type(count).ok_or_else(|| "C memcpy size argument type is unsupported".to_string())?;
    if !is_c_size_argument_type(count_ty) {
        return Err(format!(
            "C memcpy size argument must be size_t/usize, got {}",
            type_label(count_ty)
        ));
    }
    validate_bounded_call_arg(count, false).map_err(|detail| format!("C memcpy size {detail}"))?;
    Ok((dest, src, count))
}

fn validate_direct_mutable_unsigned_8_bit_pointer_arg<'a>(
    arg: &'a IrExpr,
    context: &str,
) -> Result<&'a str, String> {
    let IrExpr::Var {
        name, ty: arg_ty, ..
    } = arg
    else {
        return Err(format!(
            "{context} argument must be a direct mutable pointer parameter"
        ));
    };
    let pointee = mutable_pointer_slice_element_type(arg_ty).ok_or_else(|| {
        format!(
            "{context} argument must be a mutable unsigned 8-bit integer pointer, got {}",
            type_label(arg_ty)
        )
    })?;
    if !is_unsigned_8_bit_integer_type(pointee) {
        return Err(format!(
            "{context} argument must be a mutable unsigned 8-bit integer pointer, got {}",
            type_label(arg_ty)
        ));
    }
    Ok(name)
}

fn validate_c_memset_byte_value(value: &IrExpr) -> Result<u8, String> {
    let IrExpr::LitInt { value: raw, .. } = value else {
        return Err("C memset byte value currently supports only literal byte values".to_string());
    };
    if *raw > u8::MAX as u64 {
        return Err("C memset byte value literal must fit in unsigned char".to_string());
    }
    Ok(*raw as u8)
}

fn reserved_c_macro_or_stdlib_callee(callee: &str) -> bool {
    matches!(
        callee,
        // Keep modeled macro names here as a fail-closed backstop; modeled
        // forms must be intercepted before this reserved-surface guard.
        "assert"
            | "abs"
            | "labs"
            | "llabs"
            | "fabs"
            | "fabsf"
            | "fabsl"
            | "static_assert"
            | "_Static_assert"
            | "sizeof"
            | "offsetof"
            | "malloc"
            | "calloc"
            | "realloc"
            | "free"
            | "memcpy"
            | "memmove"
            | "memset"
            | "strlen"
            | "strnlen"
            | "strnlen_s"
            | "printf"
            | "fprintf"
            | "sprintf"
            | "snprintf"
            | "puts"
            | "putchar"
            | "getchar"
            | "exit"
            | "abort"
    )
}

fn validate_bounded_call_args(args: &[IrExpr]) -> Result<(), String> {
    let nested_call_count = args
        .iter()
        .filter(|arg| matches!(arg, IrExpr::Call { .. }))
        .count();
    if nested_call_count > 1 {
        return Err(
            "multiple nested call arguments are outside the bounded call subset".to_string(),
        );
    }
    for (index, arg) in args.iter().enumerate() {
        validate_bounded_call_arg(arg, true)
            .map_err(|detail| format!("call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn validate_bounded_call_arg(
    expr: &IrExpr,
    allow_immediate_nested_call: bool,
) -> Result<(), String> {
    match expr {
        IrExpr::LitInt { ty, .. } | IrExpr::Var { ty, .. } => {
            if matches!(ty.kind, IrTypeKind::Pointer { .. }) {
                return Err(format!(
                    "pointer value argument {} requires explicit ownership/lifetime/ABI lowering",
                    type_label(ty)
                ));
            }
            emit_scalar_type(ty)?;
            Ok(())
        }
        IrExpr::NullPtr { .. } => {
            Err("null pointer call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_bounded_call_arg(lhs, false)?;
            validate_bounded_call_arg(rhs, false)
        }
        IrExpr::Unary { operand, .. } | IrExpr::Cast { expr: operand, .. } => {
            validate_bounded_call_arg(operand, false)
        }
        IrExpr::Conditional { .. } => {
            Err("conditional call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Index { base, index, .. } => {
            validate_bounded_call_arg(base, false)?;
            validate_bounded_call_arg(index, false)
        }
        IrExpr::Member { .. } => {
            Err("member access call arguments are outside the bounded call subset".to_string())
        }
        IrExpr::ArrayLiteral { .. } => {
            Err("array literal arguments are outside the bounded call subset".to_string())
        }
        IrExpr::Call {
            callee, args, ty, ..
        } if allow_immediate_nested_call => validate_bounded_nested_call_arg(callee, args, ty),
        IrExpr::Call { .. } => {
            Err("nested call expressions are outside the bounded call subset".to_string())
        }
        IrExpr::IncDec { .. } => {
            Err("call arguments cannot use increment/decrement value semantics".to_string())
        }
        IrExpr::Deref { .. } => {
            Err("call arguments cannot use dereference value semantics".to_string())
        }
        IrExpr::AddrOf { .. } => {
            Err("call arguments cannot use address-of value semantics".to_string())
        }
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported argument expression {node}: {reason}"))
        }
    }
}

fn validate_bounded_nested_call_arg(
    callee: &str,
    args: &[IrExpr],
    ty: &IrType,
) -> Result<(), String> {
    emit_identifier(callee, "nested call callee")?;
    if callee == "strlen" {
        validate_c_strlen_call_shape(args, ty)?;
        return Ok(());
    }
    if callee == "strnlen" {
        validate_c_strnlen_call_shape(args, ty)?;
        return Ok(());
    }
    if callee == "memcmp" {
        validate_c_memcmp_call_shape(args, ty)?;
        return Ok(());
    }
    emit_scalar_type(ty).map_err(|detail| format!("nested call result has {detail}"))?;
    for (index, arg) in args.iter().enumerate() {
        validate_bounded_call_arg(arg, false)
            .map_err(|detail| format!("nested call arg[{index}] {detail}"))?;
    }
    Ok(())
}

fn find_call_callee(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Call { callee, .. } => Some(callee),
        IrExpr::Binary { lhs, rhs, .. } => find_call_callee(lhs).or_else(|| find_call_callee(rhs)),
        IrExpr::Unary { operand, .. } => find_call_callee(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => find_call_callee(condition)
            .or_else(|| find_call_callee(then_expr))
            .or_else(|| find_call_callee(else_expr)),
        IrExpr::Cast { expr, .. } => find_call_callee(expr),
        IrExpr::Index { base, index, .. } => {
            find_call_callee(base).or_else(|| find_call_callee(index))
        }
        IrExpr::Member { base, .. } => find_call_callee(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().find_map(find_call_callee),
        IrExpr::IncDec { target, .. } => find_call_callee(target),
        IrExpr::Deref { ptr, .. } => find_call_callee(ptr),
        IrExpr::AddrOf { operand, .. } => find_call_callee(operand),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => None,
    }
}

/// Emits an expression and any required prelude without losing side effects.
///
/// Most expressions lower to a single Rust value, but post-increment byte reads
/// and nested expressions can require preceding statements. Keeping that split
/// explicit prevents the emitter from reordering C-side effects or pretending
/// an unsupported side-effect pattern is a pure value expression.
fn emit_expr_with_prelude(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    match expr {
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            if let Some(expr) = emit_short_circuit_value_expr(op, lhs, rhs, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?
            {
                return Ok(EmittedExpr {
                    prelude: String::new(),
                    expr,
                });
            }
            if let Some(expr) = emit_comparison_value_expr(op, lhs, rhs, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?
            {
                return Ok(EmittedExpr {
                    prelude: String::new(),
                    expr,
                });
            }
            let op_token = emit_binary_op(op).map_err(|detail| format!("{path} {detail}"))?;
            validate_binary_operand_types(op_token, lhs, rhs, ty)
                .map_err(|detail| format!("{path} {detail}"))?;
            validate_binary_runtime_contract(op, lhs, rhs, ty, &context.policy)
                .map_err(|detail| format!("{path} {detail}"))?;
            let lhs = emit_expr_with_prelude(
                lhs,
                symbols,
                context,
                indent_level,
                &format!("{path} binary lhs"),
            )?;
            let rhs = emit_expr_with_prelude(
                rhs,
                symbols,
                context,
                indent_level,
                &format!("{path} binary rhs"),
            )?;
            Ok(EmittedExpr {
                prelude: format!("{}{}", lhs.prelude, rhs.prelude),
                expr: emit_binary_result_expr(op, op_token, &lhs.expr, &rhs.expr, ty),
            })
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "{path} cast target {} is unsupported",
                    type_label(target)
                ));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| format!("{path} cast source type is unsupported"))?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "{path} cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target = emit_scalar_type(target)
                .map_err(|detail| format!("{path} cast target has {detail}"))?;
            let emitted = emit_expr_with_prelude(
                expr,
                symbols,
                context,
                indent_level,
                &format!("{path} cast expr"),
            )?;
            Ok(EmittedExpr {
                prelude: emitted.prelude,
                expr: format!("({} as {target})", emitted.expr),
            })
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ty,
            ..
        } => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_conditional_value_expr(
                condition, then_expr, else_expr, ty, symbols, context,
            )
            .map_err(|detail| format!("{path} {detail}"))?,
        }),
        IrExpr::Index {
            base, index, ty, ..
        } => {
            let index = emit_expr_with_prelude(
                index,
                symbols,
                context,
                indent_level,
                &format!("{path} index operand"),
            )?;
            let expr = emit_index_expr_with_emitted_index(base, &index.expr, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?;
            Ok(EmittedExpr {
                prelude: index.prelude,
                expr,
            })
        }
        IrExpr::ArrayLiteral { .. } => Err(format!(
            "{path} array literal expression is only supported as a declaration initializer"
        )),
        IrExpr::Deref { ptr, ty, .. } if matches!(ptr.as_ref(), IrExpr::IncDec { .. }) => {
            emit_post_increment_byte_read_expr(ptr, ty, symbols, context, indent_level, path)
        }
        IrExpr::Deref { ptr, ty, .. } => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_readonly_pointer_deref_expr(ptr, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?,
        }),
        _ => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_expr(expr, symbols, context).map_err(|detail| format!("{path} {detail}"))?,
        }),
    }
}

fn emit_post_increment_byte_read_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr
    else {
        return Err(format!("{path} deref expression is unsupported"));
    };
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target.as_ref()
    else {
        return Err(format!("{path} post-increment target is unsupported"));
    };
    if !symbols.contains(cursor) {
        return Err(format!(
            "{path} post-increment cursor {cursor} is not declared"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(cursor_ty)
        .filter(|element_ty| is_u8(element_ty))
        .ok_or_else(|| {
            format!(
                "{path} post-increment cursor {cursor} has unsupported type {}",
                type_label(cursor_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("{path} post-increment element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("{path} deref has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "{path} deref type {deref_ty} does not match cursor element type {element_ty}"
        ));
    }
    let (source, cursor, declare_cursor) = if let Some(source) = context.byte_cursor_source(cursor)
    {
        if !symbols.contains(source) {
            return Err(format!("{path} byte source {source} is not declared"));
        }
        (
            emit_identifier(source, "byte source")?,
            emit_identifier(cursor, "byte cursor")?,
            false,
        )
    } else {
        let source = emit_identifier(cursor, "byte source")?;
        let cursor = first_available_named_temp(&format!("{source}_index"), symbols);
        (source, emit_identifier(&cursor, "byte cursor")?, true)
    };
    let temp = first_available_temp_name("byte", symbols);
    let indent = "    ".repeat(indent_level);
    let mut prelude = String::new();
    if declare_cursor {
        prelude.push_str(&format!("{indent}let mut {cursor}: usize = 0;\n"));
    }
    prelude.push_str(&format!(
        "{indent}let {temp}: {element_ty} = {source}[{cursor}];\n\
         {indent}{cursor} += 1;\n"
    ));
    Ok(EmittedExpr {
        prelude,
        expr: temp,
    })
}

fn emit_index_expr(
    base: &IrExpr,
    index: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("index base must be Var".to_string());
    };
    let (element_ty, emitted_base) = if let Some(global) = context.readonly_global(base_name) {
        validate_global_expr_type(global, base_ty)?;
        (
            readonly_global_array_element_type(global)?,
            context.global_rust_name(base_name)?,
        )
    } else {
        if !symbols.contains(base_name) {
            return Err(format!("index base {base_name} is not declared"));
        }
        let element_ty = fixed_integer_array_element_type(base_ty)
            .or_else(|| readonly_pointer_slice_element_type(base_ty))
            .ok_or_else(|| {
                format!(
                    "index base {base_name} has unsupported type {}",
                    type_label(base_ty)
                )
            })?;
        (element_ty, emit_identifier(base_name, "index base")?)
    };
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("index element has {detail}"))?;
    let result_ty = emit_scalar_type(ty).map_err(|detail| format!("index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    let index_ty =
        expr_type(index).ok_or_else(|| "index operand type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "index operand type {} is unsupported",
            type_label(index_ty)
        ));
    }
    let index =
        emit_expr(index, symbols, context).map_err(|detail| format!("index operand {detail}"))?;
    Ok(format!("{emitted_base}[{index} as usize]"))
}

fn emit_index_expr_with_emitted_index(
    base: &IrExpr,
    emitted_index: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("index base must be Var".to_string());
    };
    let (element_ty, emitted_base) = if let Some(global) = context.readonly_global(base_name) {
        validate_global_expr_type(global, base_ty)?;
        (
            readonly_global_array_element_type(global)?,
            context.global_rust_name(base_name)?,
        )
    } else {
        if !symbols.contains(base_name) {
            return Err(format!("index base {base_name} is not declared"));
        }
        let element_ty = fixed_integer_array_element_type(base_ty)
            .or_else(|| readonly_pointer_slice_element_type(base_ty))
            .ok_or_else(|| {
                format!(
                    "index base {base_name} has unsupported type {}",
                    type_label(base_ty)
                )
            })?;
        (element_ty, emit_identifier(base_name, "index base")?)
    };
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("index element has {detail}"))?;
    let result_ty = emit_scalar_type(ty).map_err(|detail| format!("index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    Ok(format!("{emitted_base}[{emitted_index} as usize]"))
}

fn is_byte_cursor_cast_assignment(
    target: &IrExpr,
    value: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<bool, String> {
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target
    else {
        return Ok(false);
    };
    let Some(source) = context.byte_cursor_source(cursor) else {
        return Ok(false);
    };
    let IrExpr::Cast {
        target,
        expr,
        implicit: false,
        ..
    } = value
    else {
        return Ok(false);
    };
    let IrExpr::Var {
        name: source_name,
        ty: source_ty,
        ..
    } = expr.as_ref()
    else {
        return Ok(false);
    };
    if source_name != source || !is_u8_pointer(cursor_ty) || !is_u8_pointer(target) {
        return Ok(false);
    }
    if !is_const_void_pointer(source_ty) {
        return Ok(false);
    }
    if !symbols.contains(cursor) {
        return Err(format!("byte cursor {cursor} is not declared"));
    }
    if !symbols.contains(source_name) {
        return Err(format!("byte cursor source {source_name} is not declared"));
    }
    Ok(true)
}

fn emit_post_increment_deref_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Deref { ptr, ty, .. } = value else {
        return Ok(None);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(base_name) {
        return Err(format!("post-increment cursor {base_name} is not declared"));
    }
    let element_ty = readonly_pointer_slice_element_type(base_ty)
        .filter(|element_ty| is_u8(element_ty))
        .ok_or_else(|| {
            format!(
                "post-increment cursor {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("post-increment element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    let return_ty =
        emit_scalar_type(return_type).map_err(|detail| format!("return type has {detail}"))?;
    if deref_ty != element_ty || return_ty != element_ty {
        return Err(format!(
            "post-increment deref type must match element and return type: element={element_ty}, deref={deref_ty}, return={return_ty}"
        ));
    }
    let (slice_name, cursor_name, declare_cursor) =
        if let Some(source_name) = context.byte_cursor_source(base_name) {
            if !symbols.contains(source_name) {
                return Err(format!(
                    "post-increment source {source_name} is not declared"
                ));
            }
            (
                emit_identifier(source_name, "post-increment source")?,
                emit_identifier(base_name, "post-increment cursor")?,
                false,
            )
        } else {
            let slice_name = emit_identifier(base_name, "post-increment base")?;
            let cursor_name = emit_identifier(
                &first_available_named_temp(&format!("{slice_name}_index"), symbols),
                "post-increment cursor",
            )?;
            (slice_name, cursor_name, true)
        };
    let temp_name = first_available_temp_name("byte", symbols);
    let indent = "    ".repeat(indent_level);
    let mut rust = String::new();
    if declare_cursor {
        rust.push_str(&format!("{indent}let mut {cursor_name}: usize = 0;\n"));
    }
    rust.push_str(&format!(
        "{indent}let {temp_name}: {element_ty} = {slice_name}[{cursor_name}];\n\
         {indent}{cursor_name} += 1;\n\
         {indent}return {temp_name};\n"
    ));
    Ok(Some(rust))
}

fn first_available_temp_name(prefix: &str, symbols: &HashSet<String>) -> String {
    let mut index = 0usize;
    loop {
        let candidate = format!("{prefix}{index}");
        if !symbols.contains(&candidate) {
            return candidate;
        }
        index += 1;
    }
}

fn first_available_named_temp(preferred: &str, symbols: &HashSet<String>) -> String {
    if !symbols.contains(preferred) {
        return preferred.to_string();
    }
    let mut index = 1usize;
    loop {
        let candidate = format!("{preferred}{index}");
        if !symbols.contains(&candidate) {
            return candidate;
        }
        index += 1;
    }
}

fn emit_binary_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Add => Ok("+"),
        IrBinOp::Sub => Ok("-"),
        IrBinOp::Mul => Ok("*"),
        IrBinOp::Div => Ok("/"),
        IrBinOp::Mod => Ok("%"),
        IrBinOp::BitAnd => Ok("&"),
        IrBinOp::BitOr => Ok("|"),
        IrBinOp::BitXor => Ok("^"),
        IrBinOp::Shl => Ok("<<"),
        IrBinOp::Shr => Ok(">>"),
        _ => Err(format!("binary op {op:?} is unsupported")),
    }
}

fn emit_binary_result_expr(
    op: &IrBinOp,
    op_token: &str,
    lhs: &str,
    rhs: &str,
    result_ty: &IrType,
) -> String {
    if let Some(method) = unsigned_wrapping_method(op, result_ty) {
        format!("{lhs}.{method}({rhs})")
    } else if let Some((method, message)) = signed_checked_method(op, result_ty) {
        format!("{lhs}.{method}({rhs}).expect(\"{message}\")")
    } else if let Some((method, message)) = checked_div_rem_method(op, result_ty) {
        format!("{lhs}.{method}({rhs}).expect(\"{message}\")")
    } else if let Some(method) = checked_shift_method(op, result_ty) {
        format!(
            "{lhs}.{method}(core::convert::TryFrom::try_from({rhs}).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\")"
        )
    } else {
        format!("({lhs} {op_token} {rhs})")
    }
}

fn unsigned_wrapping_method(op: &IrBinOp, result_ty: &IrType) -> Option<&'static str> {
    if !is_unsigned_integer_type(result_ty) {
        return None;
    }
    match op {
        IrBinOp::Add => Some("wrapping_add"),
        IrBinOp::Sub => Some("wrapping_sub"),
        IrBinOp::Mul => Some("wrapping_mul"),
        _ => None,
    }
}

fn signed_checked_method(op: &IrBinOp, result_ty: &IrType) -> Option<(&'static str, &'static str)> {
    if !is_signed_integer_type(result_ty) {
        return None;
    }
    match op {
        IrBinOp::Add => Some(("checked_add", "signed addition overflow")),
        IrBinOp::Sub => Some(("checked_sub", "signed subtraction overflow")),
        IrBinOp::Mul => Some(("checked_mul", "signed multiplication overflow")),
        _ => None,
    }
}

fn checked_div_rem_method(
    op: &IrBinOp,
    result_ty: &IrType,
) -> Option<(&'static str, &'static str)> {
    if !is_integer_type(result_ty) {
        return None;
    }
    let signed = is_signed_integer_type(result_ty);
    match (op, signed) {
        (IrBinOp::Div, true) => Some(("checked_div", "division by zero or signed overflow")),
        (IrBinOp::Div, false) => Some(("checked_div", "division by zero")),
        (IrBinOp::Mod, true) => Some(("checked_rem", "modulo by zero or signed overflow")),
        (IrBinOp::Mod, false) => Some(("checked_rem", "modulo by zero")),
        _ => None,
    }
}

fn checked_shift_method(op: &IrBinOp, result_ty: &IrType) -> Option<&'static str> {
    if !is_integer_type(result_ty) {
        return None;
    }
    match op {
        IrBinOp::Shl => Some("checked_shl"),
        IrBinOp::Shr => Some("checked_shr"),
        _ => None,
    }
}

fn emit_comparison_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Eq => Ok("=="),
        IrBinOp::Neq => Ok("!="),
        IrBinOp::Lt => Ok("<"),
        IrBinOp::Le => Ok("<="),
        IrBinOp::Gt => Ok(">"),
        IrBinOp::Ge => Ok(">="),
        _ => Err(format!("binary op {op:?} is not a comparison")),
    }
}

fn emit_negated_comparison_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Eq => Ok("!="),
        IrBinOp::Neq => Ok("=="),
        IrBinOp::Lt => Ok(">="),
        IrBinOp::Le => Ok(">"),
        IrBinOp::Gt => Ok("<="),
        IrBinOp::Ge => Ok("<"),
        _ => Err(format!("binary op {op:?} is not a comparison")),
    }
}

fn validate_binary_operand_types(
    op: &str,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
) -> Result<(), String> {
    let result_ty =
        emit_scalar_type(result_ty).map_err(|detail| format!("binary result has {detail}"))?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "binary lhs type is unsupported".to_string())?;
    let rhs_ty = expr_type(rhs).ok_or_else(|| "binary rhs type is unsupported".to_string())?;
    let lhs_ty = emit_scalar_type(lhs_ty).map_err(|detail| format!("binary lhs has {detail}"))?;
    let rhs_ty = emit_scalar_type(rhs_ty).map_err(|detail| format!("binary rhs has {detail}"))?;

    match op {
        "+" | "-" | "*" | "/" | "%" | "&" | "|" | "^" => {
            if lhs_ty == result_ty && rhs_ty == result_ty {
                Ok(())
            } else {
                Err(format!(
                    "usual arithmetic conversion requires explicit IntegralCast/IntegralPromotion before typed IR emission; binary operand types must match result type for {op}: lhs={lhs_ty}, rhs={rhs_ty}, result={result_ty}"
                ))
            }
        }
        "<<" | ">>" => {
            if lhs_ty == result_ty {
                Ok(())
            } else {
                Err(format!(
                    "shift lhs type must match result type for {op}: lhs={lhs_ty}, result={result_ty}"
                ))
            }
        }
        _ => Err(format!("binary op {op} is unsupported")),
    }
}

fn validate_binary_runtime_contract(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    policy: &EmitPolicy,
) -> Result<(), String> {
    match op {
        IrBinOp::Div if static_integer_value(rhs) == Some(0) => {
            Err("division by zero literal is unsupported".to_string())
        }
        IrBinOp::Mod if static_integer_value(rhs) == Some(0) => {
            Err("modulo by zero literal is unsupported".to_string())
        }
        IrBinOp::Shl | IrBinOp::Shr => {
            validate_shift_runtime_contract(op, lhs, rhs, result_ty, policy)
        }
        _ => Ok(()),
    }
}

fn validate_shift_runtime_contract(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    policy: &EmitPolicy,
) -> Result<(), String> {
    let width = integer_width_bits(result_ty)
        .ok_or_else(|| format!("shift result type {} is unsupported", type_label(result_ty)))?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "shift lhs type is unsupported".to_string())?;
    let lhs_width = integer_width_bits(lhs_ty)
        .ok_or_else(|| format!("shift lhs type {} is unsupported", type_label(lhs_ty)))?;
    if lhs_width != width {
        return Err(format!(
            "shift lhs width {lhs_width} does not match result width {width}"
        ));
    }
    if let Some(count) = static_integer_value(rhs) {
        if count < 0 {
            return Err(format!(
                "negative shift count literal {count} is unsupported"
            ));
        }
        if count >= i128::from(width) {
            return Err(format!(
                "shift count literal {count} must be less than width {width}"
            ));
        }
    }
    if matches!(op, IrBinOp::Shr)
        && is_signed_integer_type(result_ty)
        && policy.signed_right_shift != SignedRightShiftPolicy::ImplementationDefinedArithmetic
    {
        return Err(format!(
            "signed right shift for {} is implementation-defined without an explicit contract",
            type_label(result_ty)
        ));
    }
    Ok(())
}

fn static_integer_value(expr: &IrExpr) -> Option<i128> {
    match expr {
        IrExpr::LitInt { value, .. } => Some(i128::from(*value)),
        IrExpr::Cast { expr, .. } => static_integer_value(expr),
        IrExpr::Unary {
            op: IrUnOp::Neg,
            operand,
            ..
        } => static_integer_value(operand).and_then(i128::checked_neg),
        _ => None,
    }
}

fn integer_width_bits(ty: &IrType) -> Option<u16> {
    match ty.kind {
        IrTypeKind::Integer { width, .. } => Some(width),
        _ => None,
    }
}

fn validate_expr_matches_type(
    expr: &IrExpr,
    expected_ty: &IrType,
    context: &str,
) -> Result<(), String> {
    let actual_ty = expr_type(expr).ok_or_else(|| format!("{context} type is unsupported"))?;
    validate_record_value_type_matches(actual_ty, expected_ty, context)?;
    let expected = emit_value_type(expected_ty)
        .map_err(|detail| format!("{context} expected type has {detail}"))?;
    let actual = emit_value_type(actual_ty).map_err(|detail| format!("{context} has {detail}"))?;
    if actual != expected {
        Err(format!(
            "{context} type {actual} does not match expected type {expected}"
        ))
    } else {
        Ok(())
    }
}

fn validate_record_value_type_matches(
    actual_ty: &IrType,
    expected_ty: &IrType,
    context: &str,
) -> Result<(), String> {
    let (
        IrTypeKind::Record {
            name: actual_name,
            fields: actual_fields,
        },
        IrTypeKind::Record {
            name: expected_name,
            fields: expected_fields,
        },
    ) = (&actual_ty.kind, &expected_ty.kind)
    else {
        return Ok(());
    };
    if actual_name != expected_name {
        return Err(format!(
            "{context} record type {actual_name} does not match expected record type {expected_name}"
        ));
    }
    let Some(expected_fields) = expected_fields else {
        return Ok(());
    };
    match actual_fields {
        Some(actual_fields) if actual_fields == expected_fields => Ok(()),
        Some(_) => Err(format!(
            "{context} record field inventory does not match expected record type {expected_name}"
        )),
        None => Err(format!(
            "{context} record type {actual_name} lacks field inventory required by expected record type {expected_name}"
        )),
    }
}

fn validate_signed_unary_minus_operand(expr: &IrExpr, result_ty: &IrType) -> Result<(), String> {
    let IrTypeKind::Integer {
        signed: true,
        width: result_width,
    } = result_ty.kind
    else {
        return Err(format!(
            "unary minus result type {} is not a signed integer",
            type_label(result_ty)
        ));
    };
    let operand_ty =
        expr_type(expr).ok_or_else(|| "unary minus operand type is unsupported".to_string())?;
    let IrTypeKind::Integer {
        signed: true,
        width: operand_width,
    } = operand_ty.kind
    else {
        return Err(format!(
            "unary minus operand type {} is not a signed integer",
            type_label(operand_ty)
        ));
    };
    let result_ty =
        emit_scalar_type(result_ty).map_err(|detail| format!("unary minus result has {detail}"))?;
    let operand_ty = emit_scalar_type(operand_ty)
        .map_err(|detail| format!("unary minus operand has {detail}"))?;
    if operand_width == result_width && operand_ty == result_ty {
        Ok(())
    } else {
        Err(format!(
            "unary minus operand type {operand_ty} does not match result type {result_ty}"
        ))
    }
}

fn emit_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let Some(callee) = find_call_callee(expr) {
        return Err(format!("call expression {callee} is unsupported"));
    }
    if matches!(expr, IrExpr::Conditional { .. }) {
        return Err("conditional expression is unsupported in condition positions".to_string());
    }
    if let IrExpr::Unary {
        op: IrUnOp::Not,
        operand,
        ty,
        ..
    } = expr
    {
        return emit_logical_not_condition_expr(operand, ty, symbols, context);
    }
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        if let Some(condition) =
            emit_short_circuit_condition_expr(op, lhs, rhs, ty, symbols, context)?
        {
            return Ok(condition);
        }
    }
    if let Some(condition) = emit_comparison_condition_expr(expr, symbols, context)? {
        return Ok(condition);
    }
    let ty = expr_type(expr).ok_or_else(|| "type is unsupported".to_string())?;
    let zero = zero_literal_for_type(ty)?;
    let expr = emit_expr(expr, symbols, context)?;
    Ok(format!("{expr} != {zero}"))
}

fn emit_comparison_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        return emit_comparison_condition_from_parts(op, lhs, rhs, ty, symbols, context);
    }
    Ok(None)
}

fn emit_comparison_condition_from_parts(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Ok(op) = emit_comparison_op(op) else {
        return Ok(None);
    };
    if let Some(callee) = find_call_callee(lhs).or_else(|| find_call_callee(rhs)) {
        return Err(format!(
            "comparison operand call expression {callee} is unsupported"
        ));
    }
    if let Some(condition) =
        emit_null_pointer_comparison_condition(op, lhs, rhs, result_ty, symbols, context)?
    {
        return Ok(Some(condition));
    }
    validate_comparison_condition_types(lhs, rhs, result_ty, op)?;
    let lhs =
        emit_expr(lhs, symbols, context).map_err(|detail| format!("comparison lhs {detail}"))?;
    let rhs =
        emit_expr(rhs, symbols, context).map_err(|detail| format!("comparison rhs {detail}"))?;
    Ok(Some(format!("({lhs} {op} {rhs})")))
}

fn emit_short_circuit_condition_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let op = match op {
        IrBinOp::LogAnd => "&&",
        IrBinOp::LogOr => "||",
        _ => return Ok(None),
    };
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "short-circuit result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    let lhs =
        emit_condition_expr(lhs, symbols, context).map_err(|detail| format!("lhs {detail}"))?;
    let rhs =
        emit_condition_expr(rhs, symbols, context).map_err(|detail| format!("rhs {detail}"))?;
    Ok(Some(format!("({lhs} {op} {rhs})")))
}

fn emit_short_circuit_value_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(condition) =
        emit_short_circuit_condition_expr(op, lhs, rhs, result_ty, symbols, context)?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("short-circuit true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("short-circuit false literal {detail}"))?;
    Ok(Some(format!(
        "(if {condition} {{ {one} }} else {{ {zero} }})"
    )))
}

fn emit_comparison_value_expr(
    op: &IrBinOp,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some(condition) =
        emit_comparison_condition_from_parts(op, lhs, rhs, result_ty, symbols, context)?
    else {
        return Ok(None);
    };
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("comparison true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("comparison false literal {detail}"))?;
    Ok(Some(format!(
        "(if {condition} {{ {one} }} else {{ {zero} }})"
    )))
}

fn emit_conditional_value_expr(
    condition: &IrExpr,
    then_expr: &IrExpr,
    else_expr: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    emit_scalar_type(result_ty)
        .map_err(|detail| format!("conditional result type has {detail}"))?;
    if !is_integer_type(result_ty) {
        return Err(format!(
            "conditional result type {} is unsupported",
            type_label(result_ty)
        ));
    }
    validate_conditional_arm_expr(then_expr, result_ty, "then")?;
    validate_conditional_arm_expr(else_expr, result_ty, "else")?;
    let condition = emit_condition_expr(condition, symbols, context)
        .map_err(|detail| format!("conditional condition {detail}"))?;
    let then_expr = emit_expr(then_expr, symbols, context)
        .map_err(|detail| format!("conditional then expression {detail}"))?;
    let else_expr = emit_expr(else_expr, symbols, context)
        .map_err(|detail| format!("conditional else expression {detail}"))?;
    Ok(format!(
        "(if {condition} {{ {then_expr} }} else {{ {else_expr} }})"
    ))
}

fn validate_conditional_arm_expr(
    expr: &IrExpr,
    expected_ty: &IrType,
    side: &str,
) -> Result<(), String> {
    if let Some(callee) = find_call_callee(expr) {
        return Err(format!(
            "conditional {side} expression call expression {callee} is unsupported"
        ));
    }
    if expr_has_inc_dec(expr) {
        return Err(format!(
            "conditional {side} expression cannot use increment/decrement value semantics"
        ));
    }
    if count_post_increment_byte_reads(expr) > 0 {
        return Err(format!(
            "conditional {side} expression cannot use post-increment byte reads"
        ));
    }
    if expr_has_assign_or_comma(expr) {
        return Err(format!(
            "conditional {side} expression cannot use assignment or comma operators"
        ));
    }
    validate_expr_matches_type(expr, expected_ty, &format!("conditional {side} expression"))
}

fn expr_has_inc_dec(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::IncDec { .. } => true,
        IrExpr::Binary { lhs, rhs, .. } => expr_has_inc_dec(lhs) || expr_has_inc_dec(rhs),
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => expr_has_inc_dec(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_has_inc_dec(condition)
                || expr_has_inc_dec(then_expr)
                || expr_has_inc_dec(else_expr)
        }
        IrExpr::Index { base, index, .. } => expr_has_inc_dec(base) || expr_has_inc_dec(index),
        IrExpr::Member { base, .. } => expr_has_inc_dec(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().any(expr_has_inc_dec),
        IrExpr::Call { args, .. } => args.iter().any(expr_has_inc_dec),
        IrExpr::Deref { ptr, .. } => expr_has_inc_dec(ptr),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn expr_has_assign_or_comma(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::Assign | IrBinOp::Comma,
            ..
        } => true,
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_has_assign_or_comma(lhs) || expr_has_assign_or_comma(rhs)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => expr_has_assign_or_comma(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_has_assign_or_comma(condition)
                || expr_has_assign_or_comma(then_expr)
                || expr_has_assign_or_comma(else_expr)
        }
        IrExpr::Index { base, index, .. } => {
            expr_has_assign_or_comma(base) || expr_has_assign_or_comma(index)
        }
        IrExpr::Member { base, .. } => expr_has_assign_or_comma(base),
        IrExpr::ArrayLiteral { elements, .. } => elements.iter().any(expr_has_assign_or_comma),
        IrExpr::Call { args, .. } => args.iter().any(expr_has_assign_or_comma),
        IrExpr::IncDec { target, .. } => expr_has_assign_or_comma(target),
        IrExpr::Deref { ptr, .. } => expr_has_assign_or_comma(ptr),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn emit_logical_not_condition_expr(
    operand: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "logical not result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    if let Some(callee) = find_call_callee(operand) {
        return Err(format!(
            "logical not operand call expression {callee} is unsupported"
        ));
    }
    if let Some(condition) = emit_negated_comparison_condition_expr(operand, symbols, context)? {
        return Ok(condition);
    }
    let ty =
        expr_type(operand).ok_or_else(|| "logical not operand type is unsupported".to_string())?;
    let zero =
        zero_literal_for_type(ty).map_err(|detail| format!("logical not operand zero {detail}"))?;
    let operand = emit_expr(operand, symbols, context)
        .map_err(|detail| format!("logical not operand {detail}"))?;
    Ok(format!("{operand} == {zero}"))
}

fn emit_logical_not_value_expr(
    operand: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let condition = emit_logical_not_condition_expr(operand, result_ty, symbols, context)?;
    let one = emit_integer_literal(1, result_ty)
        .map_err(|detail| format!("logical not true literal {detail}"))?;
    let zero = emit_integer_literal(0, result_ty)
        .map_err(|detail| format!("logical not false literal {detail}"))?;
    Ok(format!("(if {condition} {{ {one} }} else {{ {zero} }})"))
}

fn emit_negated_comparison_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        if let Ok(negated_op) = emit_negated_comparison_op(op) {
            if let Some(condition) =
                emit_null_pointer_comparison_condition(negated_op, lhs, rhs, ty, symbols, context)?
            {
                return Ok(Some(condition));
            }
            validate_comparison_condition_types(lhs, rhs, ty, negated_op)?;
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("logical not operand comparison lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("logical not operand comparison rhs {detail}"))?;
            return Ok(Some(format!("({lhs} {negated_op} {rhs})")));
        }
    }
    Ok(None)
}

fn emit_null_pointer_comparison_condition(
    op: &str,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let Some((name, pointer_ty)) = null_pointer_comparison_var(lhs, rhs) else {
        return Ok(None);
    };
    if !context.is_nullable_pointer_param(name) {
        return Ok(None);
    }
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "comparison result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    if !symbols.contains(name) {
        return Err(format!("nullable pointer param {name} is not declared"));
    }
    validate_nullable_pointer_type(name, pointer_ty)?;
    let name = emit_identifier(name, "nullable pointer param")?;
    match op {
        "==" => Ok(Some(format!("{name}.is_none()"))),
        "!=" => Ok(Some(format!("{name}.is_some()"))),
        _ => Ok(None),
    }
}

fn validate_comparison_condition_types(
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    op: &str,
) -> Result<(), String> {
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "comparison result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    validate_comparison_cast_operand(lhs, "lhs")?;
    validate_comparison_cast_operand(rhs, "rhs")?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "comparison lhs type is unsupported".to_string())?;
    let rhs_ty = expr_type(rhs).ok_or_else(|| "comparison rhs type is unsupported".to_string())?;
    let lhs_ty =
        emit_scalar_type(lhs_ty).map_err(|detail| format!("comparison lhs has {detail}"))?;
    let rhs_ty =
        emit_scalar_type(rhs_ty).map_err(|detail| format!("comparison rhs has {detail}"))?;
    if lhs_ty == rhs_ty {
        Ok(())
    } else {
        Err(format!(
            "comparison operand types must match for {op}: lhs={lhs_ty}, rhs={rhs_ty}"
        ))
    }
}

fn validate_comparison_cast_operand(expr: &IrExpr, side: &str) -> Result<(), String> {
    let IrExpr::Cast { target, expr, .. } = expr else {
        return Ok(());
    };
    if !is_integer_type(target) {
        return Err(format!(
            "comparison {side} cast target {} is unsupported",
            type_label(target)
        ));
    }
    let source_type = expr_type(expr)
        .ok_or_else(|| format!("comparison {side} cast source type is unsupported"))?;
    if !is_integer_type(source_type) {
        return Err(format!(
            "comparison {side} cast source {} is unsupported",
            type_label(source_type)
        ));
    }
    emit_scalar_type(target)
        .map_err(|detail| format!("comparison {side} cast target has {detail}"))?;
    emit_scalar_type(source_type)
        .map_err(|detail| format!("comparison {side} cast source has {detail}"))?;
    Ok(())
}

fn ends_with_return_value(body: &[IrStmt]) -> bool {
    match body.last() {
        Some(IrStmt::Return { value: Some(_), .. }) => true,
        Some(IrStmt::If {
            then_body,
            else_body,
            ..
        }) => ends_with_return_value(then_body) && ends_with_return_value(else_body),
        _ => false,
    }
}

fn validate_definite_assignment(
    function: &IrFunction,
    globals: &[IrGlobal],
    context: &EmitContext,
) -> Result<HashSet<MutableRecordPointerFieldKey>, String> {
    let mut state = DefiniteAssignmentState::from_function_and_globals(function, globals, context);
    validate_definite_assignment_body(&function.body, &mut state)?;
    Ok(state.validated_mutable_record_pointer_read_fields)
}

fn validate_definite_assignment_body(
    body: &[IrStmt],
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    for (index, stmt) in body.iter().enumerate() {
        validate_definite_assignment_stmt(stmt, state)
            .map_err(|detail| format!("stmt[{index}].{detail}"))?;
    }
    Ok(())
}

fn validate_definite_assignment_labeled_body(
    body: &[IrStmt],
    state: &mut DefiniteAssignmentState,
    label: &str,
) -> Result<(), String> {
    for (index, stmt) in body.iter().enumerate() {
        validate_definite_assignment_stmt(stmt, state)
            .map_err(|detail| format!("{label}[{index}].{detail}"))?;
    }
    Ok(())
}

fn body_definitely_returns(body: &[IrStmt]) -> bool {
    body.iter().any(stmt_definitely_returns)
}

fn stmt_definitely_returns(stmt: &IrStmt) -> bool {
    match stmt {
        IrStmt::Return { .. } => true,
        IrStmt::If {
            then_body,
            else_body,
            ..
        } => {
            !else_body.is_empty()
                && body_definitely_returns(then_body)
                && body_definitely_returns(else_body)
        }
        IrStmt::Decl { .. }
        | IrStmt::Assign { .. }
        | IrStmt::While { .. }
        | IrStmt::DoWhile { .. }
        | IrStmt::For { .. }
        | IrStmt::Break { .. }
        | IrStmt::Continue { .. }
        | IrStmt::Expr { .. }
        | IrStmt::Unsupported { .. } => false,
    }
}

fn merge_definite_branch_set<T>(
    before: &HashSet<T>,
    then_set: &HashSet<T>,
    then_returns: bool,
    else_set: &HashSet<T>,
    else_returns: bool,
) -> HashSet<T>
where
    T: Clone + Eq + Hash,
{
    if then_returns && else_returns {
        return before.clone();
    }
    before
        .iter()
        .chain(then_set.iter())
        .chain(else_set.iter())
        .filter(|item| {
            before.contains(*item)
                || ((then_returns || then_set.contains(*item))
                    && (else_returns || else_set.contains(*item)))
        })
        .cloned()
        .collect()
}

/// Checks one statement against the emitter's conservative initialization model.
///
/// This pass is intentionally narrower than full C data-flow analysis. It only
/// carries facts that are definitely true on all non-returning paths, avoids
/// assuming loops execute, and treats mutable record-pointer fields as separate
/// facts so reads cannot be emitted before an observed write.
fn validate_definite_assignment_stmt(
    stmt: &IrStmt,
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { name, init, .. } => {
            if let Some(init) = init {
                validate_definite_assignment_expr(init, state)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
            }
            state.declare(name, init.is_some())
        }
        IrStmt::Assign { target, value, .. } => {
            let mutable_record_pointer_target =
                mutable_record_pointer_field_key_for_definite_assignment(target, state)?;
            let assigned_var = validate_definite_assignment_target(target, state)?;
            match &mutable_record_pointer_target {
                Some(target_key) => {
                    validate_definite_assignment_assign_value(value, state, target_key)
                        .map_err(|detail| format!("assign value {detail}"))?
                }
                None => validate_definite_assignment_expr(value, state)
                    .map_err(|detail| format!("assign value {detail}"))?,
            }
            if let Some(name) = assigned_var {
                state.assign(&name)?;
            }
            if let Some(key) = mutable_record_pointer_target {
                state.assign_mutable_record_pointer_field(key);
            }
            Ok(())
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                validate_definite_assignment_expr(value, state)
                    .map_err(|detail| format!("return expr {detail}"))?;
            }
            Ok(())
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } => Ok(()),
        IrStmt::Expr { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("expr {detail}")),
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("if condition {detail}"))?;
            let before = state.clone();
            let mut then_state = before.clone();
            validate_definite_assignment_labeled_body(then_body, &mut then_state, "if then")?;
            let mut else_state = before.clone();
            validate_definite_assignment_labeled_body(else_body, &mut else_state, "if else")?;
            let then_returns = body_definitely_returns(then_body);
            let else_returns = body_definitely_returns(else_body);

            state.initialized = merge_definite_branch_set(
                &before.initialized,
                &then_state.initialized,
                then_returns,
                &else_state.initialized,
                else_returns,
            );
            state
                .initialized
                .retain(|name| before.declared.contains(name));
            state.mutable_record_pointer_fields = merge_definite_branch_set(
                &before.mutable_record_pointer_fields,
                &then_state.mutable_record_pointer_fields,
                then_returns,
                &else_state.mutable_record_pointer_fields,
                else_returns,
            );
            state
                .validated_mutable_record_pointer_read_fields
                .extend(then_state.validated_mutable_record_pointer_read_fields);
            state
                .validated_mutable_record_pointer_read_fields
                .extend(else_state.validated_mutable_record_pointer_read_fields);
            Ok(())
        }
        IrStmt::While {
            condition, body, ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("while condition {detail}"))?;
            let mut body_state = state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "while body")?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            Ok(())
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            let mut body_state = state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "do while body")?;
            validate_definite_assignment_expr(condition, &mut body_state)
                .map_err(|detail| format!("do while condition {detail}"))?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            Ok(())
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            let mut loop_state = state.clone();
            for (index, init) in init.iter().enumerate() {
                validate_definite_assignment_stmt(init, &mut loop_state)
                    .map_err(|detail| format!("for init[{index}] {detail}"))?;
            }
            if let Some(condition) = condition {
                validate_definite_assignment_expr(condition, &mut loop_state)
                    .map_err(|detail| format!("for condition {detail}"))?;
            }
            let loop_reads = loop_state
                .validated_mutable_record_pointer_read_fields
                .clone();
            let mut body_state = loop_state.clone();
            validate_definite_assignment_labeled_body(body, &mut body_state, "for body")?;
            state
                .validated_mutable_record_pointer_read_fields
                .extend(loop_reads);
            state
                .validated_mutable_record_pointer_read_fields
                .extend(body_state.validated_mutable_record_pointer_read_fields);
            if let Some(step) = step {
                let mut step_state = loop_state;
                validate_definite_assignment_stmt(step, &mut step_state)
                    .map_err(|detail| format!("for step {detail}"))?;
                state
                    .validated_mutable_record_pointer_read_fields
                    .extend(step_state.validated_mutable_record_pointer_read_fields);
            }
            Ok(())
        }
        IrStmt::Unsupported { .. } => Ok(()),
    }
}

fn validate_definite_assignment_target(
    target: &IrExpr,
    state: &mut DefiniteAssignmentState,
) -> Result<Option<String>, String> {
    match target {
        IrExpr::Var { name, ty, .. } if should_track_definite_assignment_type(ty) => {
            if !state.declared.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            Ok(Some(name.clone()))
        }
        IrExpr::Var { .. } => Ok(None),
        IrExpr::Index { base, index, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("assign index base {detail}"))?;
            validate_definite_assignment_expr(index, state)
                .map_err(|detail| format!("assign index operand {detail}"))?;
            Ok(None)
        }
        IrExpr::Deref { ptr, .. } => {
            validate_definite_assignment_expr(ptr, state)
                .map_err(|detail| format!("assign deref pointer {detail}"))?;
            Ok(None)
        }
        IrExpr::Member { base, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("assign member base {detail}"))?;
            Ok(None)
        }
        _ => Err(
            "assign target must be Var, local fixed array Index, pointer Deref, or by-value record Member"
                .to_string(),
        ),
    }
}

fn validate_definite_assignment_assign_value(
    value: &IrExpr,
    state: &mut DefiniteAssignmentState,
    target_key: &MutableRecordPointerFieldKey,
) -> Result<(), String> {
    if let IrExpr::Binary { lhs, rhs, .. } = value {
        if mutable_record_pointer_field_key_for_definite_assignment(lhs, state)?.as_ref()
            == Some(target_key)
        {
            return validate_definite_assignment_expr(rhs, state)
                .map_err(|detail| format!("binary rhs {detail}"));
        }
    }
    validate_definite_assignment_expr(value, state)
}

fn validate_definite_assignment_expr(
    expr: &IrExpr,
    state: &mut DefiniteAssignmentState,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. } if should_track_definite_assignment_type(ty) => {
            state.require_initialized(name)
        }
        IrExpr::Var { .. } => Ok(()),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_definite_assignment_expr(lhs, state)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            validate_definite_assignment_expr(rhs, state)
                .map_err(|detail| format!("binary rhs {detail}"))
        }
        IrExpr::Unary { operand, .. } => validate_definite_assignment_expr(operand, state)
            .map_err(|detail| format!("unary operand {detail}")),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            validate_definite_assignment_expr(condition, state)
                .map_err(|detail| format!("conditional condition {detail}"))?;
            validate_definite_assignment_expr(then_expr, state)
                .map_err(|detail| format!("conditional then {detail}"))?;
            validate_definite_assignment_expr(else_expr, state)
                .map_err(|detail| format!("conditional else {detail}"))
        }
        IrExpr::Cast { expr, .. } => validate_definite_assignment_expr(expr, state)
            .map_err(|detail| format!("cast expr {detail}")),
        IrExpr::Index { base, index, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("index base {detail}"))?;
            validate_definite_assignment_expr(index, state)
                .map_err(|detail| format!("index operand {detail}"))
        }
        IrExpr::Member { base, .. } => {
            validate_definite_assignment_expr(base, state)
                .map_err(|detail| format!("member base {detail}"))?;
            if let Some(key) =
                mutable_record_pointer_field_key_for_definite_assignment(expr, state)?
            {
                state.require_mutable_record_pointer_field_initialized(&key)?;
            }
            Ok(())
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for (index, element) in elements.iter().enumerate() {
                validate_definite_assignment_expr(element, state)
                    .map_err(|detail| format!("array element[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::Call { args, .. } => {
            for (index, arg) in args.iter().enumerate() {
                validate_definite_assignment_expr(arg, state)
                    .map_err(|detail| format!("call arg[{index}] {detail}"))?;
            }
            Ok(())
        }
        IrExpr::IncDec { target, .. } => validate_definite_assignment_expr(target, state)
            .map_err(|detail| format!("inc/dec target {detail}")),
        IrExpr::Deref { ptr, .. } => validate_definite_assignment_expr(ptr, state)
            .map_err(|detail| format!("deref pointer {detail}")),
        IrExpr::AddrOf { operand, .. } => validate_definite_assignment_expr(operand, state)
            .map_err(|detail| format!("address-of operand {detail}")),
        IrExpr::LitInt { .. } | IrExpr::NullPtr { .. } | IrExpr::Unsupported { .. } => Ok(()),
    }
}

fn mutable_record_pointer_field_key_for_definite_assignment(
    expr: &IrExpr,
    state: &DefiniteAssignmentState,
) -> Result<Option<MutableRecordPointerFieldKey>, String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(None);
    };
    if !state.mutable_record_pointer_write_params.contains(name) {
        return Ok(None);
    }
    mutable_record_pointer_pointee_type(base_ty).ok_or_else(|| {
        format!(
            "mutable record pointer field {name}.{field} has unsupported base type {}",
            type_label(base_ty)
        )
    })?;
    emit_record_field_type(ty)
        .map_err(|detail| format!("mutable record pointer field {name}.{field} has {detail}"))?;
    Ok(Some(MutableRecordPointerFieldKey {
        base: name.clone(),
        field: field.clone(),
    }))
}

fn should_track_definite_assignment_type(ty: &IrType) -> bool {
    emit_scalar_type(ty).is_ok()
}

fn emit_integer_literal_suffix(ty: &IrType) -> Result<String, String> {
    if is_size_t_type(ty) {
        return Ok("usize".to_string());
    }
    match &ty.kind {
        IrTypeKind::Integer { signed, width } => match (*signed, *width) {
            (true, 8) => Ok("i8".to_string()),
            (true, 16) => Ok("i16".to_string()),
            (true, 32) => Ok("i32".to_string()),
            (true, 64) => Ok("i64".to_string()),
            (false, 8) => Ok("u8".to_string()),
            (false, 16) => Ok("u16".to_string()),
            (false, 32) => Ok("u32".to_string()),
            (false, 64) => Ok("u64".to_string()),
            _ => Err(format!(
                "literal integer type {} is unsupported",
                type_label(ty)
            )),
        },
        _ => Err(format!("literal type {} is not an integer", type_label(ty))),
    }
}

fn emit_integer_literal(value: u64, ty: &IrType) -> Result<String, String> {
    validate_integer_literal_range(value, ty)?;
    let suffix = emit_integer_literal_suffix(ty)?;
    Ok(format!("{value}{suffix}"))
}

fn zero_literal_for_type(ty: &IrType) -> Result<String, String> {
    emit_integer_literal(0, ty)
}

fn validate_integer_literal_range(value: u64, ty: &IrType) -> Result<(), String> {
    let label = emit_scalar_type(ty)?;
    let max = match &ty.kind {
        IrTypeKind::Integer { signed, width } => {
            if is_size_t_type(ty) {
                usize::MAX as u64
            } else if *signed {
                match width {
                    8 => i8::MAX as u64,
                    16 => i16::MAX as u64,
                    32 => i32::MAX as u64,
                    64 => i64::MAX as u64,
                    _ => return Err(format!("literal integer type {label} is unsupported")),
                }
            } else {
                match width {
                    8 => u8::MAX as u64,
                    16 => u16::MAX as u64,
                    32 => u32::MAX as u64,
                    64 => u64::MAX,
                    _ => return Err(format!("literal integer type {label} is unsupported")),
                }
            }
        }
        _ => return Err(format!("literal type {label} is not an integer")),
    };

    if value <= max {
        Ok(())
    } else {
        Err(format!("literal value {value} does not fit type {label}"))
    }
}

fn collect_assigned_vars(body: &[IrStmt]) -> HashSet<String> {
    let mut assigned_vars = HashSet::new();
    collect_assigned_vars_from_body(body, &mut assigned_vars);
    assigned_vars
}

fn collect_byte_cursor_sources(body: &[IrStmt]) -> HashMap<String, String> {
    let mut candidates = HashMap::new();
    collect_byte_cursor_sources_from_body(body, &mut candidates);
    candidates
        .into_iter()
        .filter(|(cursor, _)| body_has_post_increment_byte_read(body, cursor))
        .collect()
}

fn collect_byte_cursor_sources_from_body(
    body: &[IrStmt],
    cursor_sources: &mut HashMap<String, String>,
) {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, value, .. } => {
                if let Some((cursor, source)) = byte_cursor_cast_assignment_parts(target, value) {
                    cursor_sources.insert(cursor.to_string(), source.to_string());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_byte_cursor_sources_from_body(then_body, cursor_sources);
                collect_byte_cursor_sources_from_body(else_body, cursor_sources);
            }
            IrStmt::While { body, .. } => {
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            IrStmt::DoWhile { body, .. } => {
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_byte_cursor_sources_from_body(init, cursor_sources);
                if let Some(step) = step {
                    collect_byte_cursor_sources_from_body(
                        std::slice::from_ref(step.as_ref()),
                        cursor_sources,
                    );
                }
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            _ => {}
        }
    }
}

fn byte_cursor_cast_assignment_parts<'a>(
    target: &'a IrExpr,
    value: &'a IrExpr,
) -> Option<(&'a str, &'a str)> {
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target
    else {
        return None;
    };
    let IrExpr::Cast {
        target,
        expr,
        implicit: false,
        ..
    } = value
    else {
        return None;
    };
    let IrExpr::Var {
        name: source,
        ty: source_ty,
        ..
    } = expr.as_ref()
    else {
        return None;
    };
    if is_u8_pointer(cursor_ty) && is_u8_pointer(target) && is_const_void_pointer(source_ty) {
        Some((cursor.as_str(), source.as_str()))
    } else {
        None
    }
}

fn body_has_post_increment_byte_read(body: &[IrStmt], cursor: &str) -> bool {
    body.iter()
        .any(|stmt| stmt_has_post_increment_byte_read(stmt, cursor))
}

fn stmt_has_post_increment_byte_read(stmt: &IrStmt, cursor: &str) -> bool {
    match stmt {
        IrStmt::Decl { init, .. } => init
            .as_ref()
            .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor)),
        IrStmt::Assign { target, value, .. } => {
            expr_has_post_increment_byte_read(target, cursor)
                || expr_has_post_increment_byte_read(value, cursor)
        }
        IrStmt::Return { value, .. } => value
            .as_ref()
            .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor)),
        IrStmt::Break { .. } | IrStmt::Continue { .. } => false,
        IrStmt::Expr { expr, .. } => expr_has_post_increment_byte_read(expr, cursor),
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || body_has_post_increment_byte_read(then_body, cursor)
                || body_has_post_increment_byte_read(else_body, cursor)
        }
        IrStmt::While {
            condition, body, ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || body_has_post_increment_byte_read(body, cursor)
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            body_has_post_increment_byte_read(body, cursor)
                || expr_has_post_increment_byte_read(condition, cursor)
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            body_has_post_increment_byte_read(init, cursor)
                || condition
                    .as_ref()
                    .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor))
                || step
                    .as_ref()
                    .is_some_and(|stmt| stmt_has_post_increment_byte_read(stmt, cursor))
                || body_has_post_increment_byte_read(body, cursor)
        }
        IrStmt::Unsupported { .. } => false,
    }
}

fn expr_has_post_increment_byte_read(expr: &IrExpr, cursor: &str) -> bool {
    match expr {
        IrExpr::Deref { ptr, ty, .. } => is_u8(ty) && is_post_inc_var(ptr, cursor),
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_has_post_increment_byte_read(lhs, cursor)
                || expr_has_post_increment_byte_read(rhs, cursor)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => expr_has_post_increment_byte_read(operand, cursor),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || expr_has_post_increment_byte_read(then_expr, cursor)
                || expr_has_post_increment_byte_read(else_expr, cursor)
        }
        IrExpr::ArrayLiteral { elements, .. } => elements
            .iter()
            .any(|element| expr_has_post_increment_byte_read(element, cursor)),
        IrExpr::Index { base, index, .. } => {
            expr_has_post_increment_byte_read(base, cursor)
                || expr_has_post_increment_byte_read(index, cursor)
        }
        IrExpr::Member { base, .. } => expr_has_post_increment_byte_read(base, cursor),
        IrExpr::Call { args, .. } => args
            .iter()
            .any(|arg| expr_has_post_increment_byte_read(arg, cursor)),
        IrExpr::IncDec { target, .. } => expr_has_post_increment_byte_read(target, cursor),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => false,
    }
}

fn count_post_increment_byte_reads(expr: &IrExpr) -> usize {
    match expr {
        IrExpr::Deref { ptr, ty, .. } if is_u8(ty) && is_post_inc_expr(ptr) => 1,
        IrExpr::Deref { ptr, .. } => count_post_increment_byte_reads(ptr),
        IrExpr::Binary { lhs, rhs, .. } => {
            count_post_increment_byte_reads(lhs) + count_post_increment_byte_reads(rhs)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => count_post_increment_byte_reads(operand),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            count_post_increment_byte_reads(condition)
                + count_post_increment_byte_reads(then_expr)
                + count_post_increment_byte_reads(else_expr)
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            elements.iter().map(count_post_increment_byte_reads).sum()
        }
        IrExpr::Index { base, index, .. } => {
            count_post_increment_byte_reads(base) + count_post_increment_byte_reads(index)
        }
        IrExpr::Member { base, .. } => count_post_increment_byte_reads(base),
        IrExpr::Call { args, .. } => args.iter().map(count_post_increment_byte_reads).sum(),
        IrExpr::IncDec { target, .. } => count_post_increment_byte_reads(target),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => 0,
    }
}

fn collect_nullable_pointer_params(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<HashSet<String>, String> {
    reject_nullable_mutable_pointer_params(body, params)?;
    let readonly_pointer_params = params
        .iter()
        .filter(|param| is_supported_nullable_pointer_type(&param.ty))
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut nullable_params = HashSet::new();
    collect_nullable_pointer_params_from_body(body, &readonly_pointer_params, &mut nullable_params);
    let mut proven_nonnull_params = HashSet::new();
    validate_nullable_pointer_param_uses_in_body(
        body,
        &nullable_params,
        &mut proven_nonnull_params,
    )?;
    Ok(nullable_params)
}

fn reject_nullable_mutable_pointer_params(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<(), String> {
    let mutable_pointer_params = params
        .iter()
        .filter(|param| mutable_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    if mutable_pointer_params.is_empty() {
        return Ok(());
    }
    for stmt in body {
        reject_nullable_mutable_pointer_params_in_stmt(stmt, &mutable_pointer_params)?;
    }
    Ok(())
}

fn reject_nullable_mutable_pointer_params_in_stmt(
    stmt: &IrStmt,
    mutable_pointer_params: &HashMap<&str, &IrType>,
) -> Result<(), String> {
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                reject_nullable_mutable_pointer_params_in_expr(init, mutable_pointer_params)?;
            }
        }
        IrStmt::Assign { target, value, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(target, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(value, mutable_pointer_params)?;
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            for stmt in then_body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
            for stmt in else_body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
        }
        IrStmt::While {
            condition, body, ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            for stmt in body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            for stmt in body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            for stmt in init {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
            if let Some(condition) = condition {
                reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            }
            if let Some(step) = step {
                reject_nullable_mutable_pointer_params_in_stmt(step, mutable_pointer_params)?;
            }
            for stmt in body {
                reject_nullable_mutable_pointer_params_in_stmt(stmt, mutable_pointer_params)?;
            }
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                reject_nullable_mutable_pointer_params_in_expr(value, mutable_pointer_params)?;
            }
        }
        IrStmt::Expr { expr, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(expr, mutable_pointer_params)?;
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
    }
    Ok(())
}

fn reject_nullable_mutable_pointer_params_in_expr(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
) -> Result<(), String> {
    if let IrExpr::Binary {
        op: IrBinOp::Eq | IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = expr
    {
        if let Some((name, pointer_ty)) = null_pointer_comparison_var(lhs, rhs) {
            if mutable_pointer_params
                .get(name)
                .is_some_and(|param_ty| *param_ty == pointer_ty)
            {
                return Err(format!(
                    "nullable mutable pointer param {name} cannot be lowered to &mut [T]"
                ));
            }
        }
    }
    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(lhs, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(rhs, mutable_pointer_params)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::Deref { ptr: operand, .. }
        | IrExpr::Member { base: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(operand, mutable_pointer_params)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            reject_nullable_mutable_pointer_params_in_expr(condition, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(then_expr, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(else_expr, mutable_pointer_params)?;
        }
        IrExpr::Index { base, index, .. } => {
            reject_nullable_mutable_pointer_params_in_expr(base, mutable_pointer_params)?;
            reject_nullable_mutable_pointer_params_in_expr(index, mutable_pointer_params)?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                reject_nullable_mutable_pointer_params_in_expr(element, mutable_pointer_params)?;
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                reject_nullable_mutable_pointer_params_in_expr(arg, mutable_pointer_params)?;
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

fn collect_nullable_pointer_params_from_body(
    body: &[IrStmt],
    readonly_pointer_params: &HashMap<&str, &IrType>,
    nullable_params: &mut HashSet<String>,
) {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_nullable_pointer_params_from_expr(
                        init,
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_nullable_pointer_params_from_expr(
                    target,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_expr(
                    value,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_nullable_pointer_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_body(
                    then_body,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_body(
                    else_body,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_nullable_pointer_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_body(
                    body,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_nullable_pointer_params_from_body(
                    body,
                    readonly_pointer_params,
                    nullable_params,
                );
                collect_nullable_pointer_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_nullable_pointer_params_from_body(
                    init,
                    readonly_pointer_params,
                    nullable_params,
                );
                if let Some(condition) = condition {
                    collect_nullable_pointer_params_from_expr(
                        condition,
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
                if let Some(step) = step {
                    collect_nullable_pointer_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
                collect_nullable_pointer_params_from_body(
                    body,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_nullable_pointer_params_from_expr(
                        value,
                        readonly_pointer_params,
                        nullable_params,
                    );
                }
            }
            IrStmt::Break { .. } | IrStmt::Continue { .. } => {}
            IrStmt::Expr { expr, .. } => {
                collect_nullable_pointer_params_from_expr(
                    expr,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
            IrStmt::Unsupported { .. } => {}
        }
    }
}

fn collect_nullable_pointer_params_from_expr(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    nullable_params: &mut HashSet<String>,
) {
    if let IrExpr::Binary {
        op: IrBinOp::Eq | IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = expr
    {
        if let Some((name, pointer_ty)) = null_pointer_comparison_var(lhs, rhs) {
            if readonly_pointer_params
                .get(name)
                .is_some_and(|param_ty| *param_ty == pointer_ty)
            {
                nullable_params.insert(name.to_string());
            }
        }
    }
    match expr {
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_nullable_pointer_params_from_expr(
                lhs,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                rhs,
                readonly_pointer_params,
                nullable_params,
            );
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => collect_nullable_pointer_params_from_expr(
            operand,
            readonly_pointer_params,
            nullable_params,
        ),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_nullable_pointer_params_from_expr(
                condition,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                then_expr,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                else_expr,
                readonly_pointer_params,
                nullable_params,
            );
        }
        IrExpr::Index { base, index, .. } => {
            collect_nullable_pointer_params_from_expr(
                base,
                readonly_pointer_params,
                nullable_params,
            );
            collect_nullable_pointer_params_from_expr(
                index,
                readonly_pointer_params,
                nullable_params,
            );
        }
        IrExpr::Member { base, .. } => collect_nullable_pointer_params_from_expr(
            base,
            readonly_pointer_params,
            nullable_params,
        ),
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_nullable_pointer_params_from_expr(
                    element,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                collect_nullable_pointer_params_from_expr(
                    arg,
                    readonly_pointer_params,
                    nullable_params,
                );
            }
        }
        IrExpr::IncDec { target, .. } => collect_nullable_pointer_params_from_expr(
            target,
            readonly_pointer_params,
            nullable_params,
        ),
        IrExpr::Deref { ptr, .. } => {
            collect_nullable_pointer_params_from_expr(ptr, readonly_pointer_params, nullable_params)
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
}

fn collect_mutable_record_pointer_write_params(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<HashSet<String>, String> {
    let pointer_param_count = params
        .iter()
        .filter(|param| {
            matches!(param.ty.kind, IrTypeKind::Pointer { .. })
                && emit_opaque_void_pointer_type(&param.ty).is_none()
        })
        .count();
    let mutable_record_pointer_params = params
        .iter()
        .filter(|param| mutable_record_pointer_pointee_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut write_params = HashSet::new();
    collect_mutable_record_pointer_write_params_from_body(
        body,
        &mutable_record_pointer_params,
        &mut write_params,
    )?;
    if !write_params.is_empty() && pointer_param_count != 1 {
        return Err(
            "mutable record pointer field assignment requires exactly one pointer param for alias proof"
                .to_string(),
        );
    }
    Ok(write_params)
}

fn collect_opaque_record_pointer_field_value_params(
    body: &[IrStmt],
    params: &[IrParam],
    mutable_record_pointer_write_params: &HashSet<String>,
) -> Result<HashSet<String>, String> {
    let param_types: HashMap<&str, &IrType> = params
        .iter()
        .map(|param| (param.name.as_str(), &param.ty))
        .collect();
    let mut value_params = HashSet::new();
    collect_opaque_record_pointer_field_value_params_from_body(
        body,
        &param_types,
        mutable_record_pointer_write_params,
        &mut value_params,
    )?;
    Ok(value_params)
}

fn collect_opaque_record_pointer_field_value_params_from_body(
    body: &[IrStmt],
    param_types: &HashMap<&str, &IrType>,
    mutable_record_pointer_write_params: &HashSet<String>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, value, .. } => {
                collect_opaque_record_pointer_field_value_param_from_assignment(
                    target,
                    value,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_opaque_record_pointer_field_value_params_from_body(
                    then_body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
                collect_opaque_record_pointer_field_value_params_from_body(
                    else_body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_opaque_record_pointer_field_value_params_from_body(
                    body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_opaque_record_pointer_field_value_params_from_body(
                    init,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
                if let Some(step) = step {
                    collect_opaque_record_pointer_field_value_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        param_types,
                        mutable_record_pointer_write_params,
                        value_params,
                    )?;
                }
                collect_opaque_record_pointer_field_value_params_from_body(
                    body,
                    param_types,
                    mutable_record_pointer_write_params,
                    value_params,
                )?;
            }
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_opaque_record_pointer_field_value_param_from_assignment(
    target: &IrExpr,
    value: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    mutable_record_pointer_write_params: &HashSet<String>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Member {
        base,
        ty,
        is_arrow: true,
        ..
    } = target
    else {
        return Ok(());
    };
    let IrExpr::Var {
        name: base_name, ..
    } = base.as_ref()
    else {
        return Ok(());
    };
    if !mutable_record_pointer_write_params.contains(base_name) {
        return Ok(());
    }
    if emit_opaque_void_pointer_type(ty).is_none() {
        return Ok(());
    }
    collect_opaque_record_pointer_value_param_from_expr(value, param_types, value_params)
}

fn collect_opaque_record_pointer_value_param_from_expr(
    value: &IrExpr,
    param_types: &HashMap<&str, &IrType>,
    value_params: &mut HashSet<String>,
) -> Result<(), String> {
    match value {
        IrExpr::Var { name, ty, .. } => {
            if param_types.get(name.as_str()).is_some_and(|param_ty| {
                *param_ty == ty && emit_opaque_void_pointer_type(ty).is_some()
            }) {
                value_params.insert(name.clone());
            }
            Ok(())
        }
        IrExpr::Cast { expr, .. } => {
            collect_opaque_record_pointer_value_param_from_expr(expr, param_types, value_params)
        }
        _ => Ok(()),
    }
}

fn validate_mutable_pointer_write_alias_boundary(
    body: &[IrStmt],
    params: &[IrParam],
    policy: &EmitPolicy,
) -> Result<(), String> {
    let mutable_pointer_params = params
        .iter()
        .filter(|param| mutable_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let readonly_pointer_params = params
        .iter()
        .filter(|param| readonly_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut write_params = HashSet::new();
    collect_mutable_pointer_write_params_from_body(
        body,
        &mutable_pointer_params,
        &mut write_params,
    )?;
    if write_params.len() > 1 {
        return Err(
            "mutable pointer write requires exactly one pointer param for alias proof".to_string(),
        );
    }
    // Safe Rust cannot express a potentially aliased `&[T]` read beside an
    // `&mut [T]` write without an explicit noalias fact.
    if !write_params.is_empty() {
        let mut readonly_pointer_uses = ReadonlyPointerParamUses::default();
        collect_readonly_pointer_read_params_from_body(
            body,
            &readonly_pointer_params,
            &mut readonly_pointer_uses,
        )?;
        if !readonly_pointer_uses.read_params.is_empty()
            && !readonly_mutable_pointer_noalias_proven(
                &readonly_pointer_uses.read_params,
                &write_params,
                params,
                policy,
            )
        {
            return Err(
                "mutable pointer write with readonly pointer read requires noalias proof"
                    .to_string(),
            );
        }
    }
    Ok(())
}

fn readonly_mutable_pointer_noalias_proven(
    readonly_params: &HashSet<String>,
    mutable_params: &HashSet<String>,
    params: &[IrParam],
    policy: &EmitPolicy,
) -> bool {
    let Some(mutable_param) = mutable_params.iter().next() else {
        return false;
    };
    let params_by_name = params
        .iter()
        .map(|param| (param.name.as_str(), param))
        .collect::<HashMap<_, _>>();

    readonly_params.iter().all(|readonly_param| {
        explicit_noalias_pair(policy, readonly_param, mutable_param)
            || params_have_restrict_noalias(&params_by_name, readonly_param, mutable_param)
    })
}

fn explicit_noalias_pair(policy: &EmitPolicy, readonly_param: &str, mutable_param: &str) -> bool {
    policy
        .noalias_param_pairs
        .iter()
        .any(|pair| pair.readonly_param == readonly_param && pair.mutable_param == mutable_param)
}

fn params_have_restrict_noalias(
    params_by_name: &HashMap<&str, &IrParam>,
    readonly_param: &str,
    mutable_param: &str,
) -> bool {
    params_by_name
        .get(readonly_param)
        .is_some_and(|param| type_has_restrict_qualifier(&param.ty))
        && params_by_name
            .get(mutable_param)
            .is_some_and(|param| type_has_restrict_qualifier(&param.ty))
}

fn type_has_restrict_qualifier(ty: &IrType) -> bool {
    [ty.spelled.as_str(), ty.canonical.as_str()]
        .iter()
        .any(|spelling| spelling_has_restrict_qualifier(spelling))
}

fn spelling_has_restrict_qualifier(spelling: &str) -> bool {
    spelling
        .split(|ch: char| {
            ch.is_whitespace() || matches!(ch, '*' | '(' | ')' | '[' | ']' | ',' | ';')
        })
        .any(|token| matches!(token, "restrict" | "__restrict" | "__restrict__"))
}

fn collect_readonly_pointer_param_uses(
    body: &[IrStmt],
    params: &[IrParam],
) -> Result<ReadonlyPointerParamUses, String> {
    let readonly_pointer_params = params
        .iter()
        .filter(|param| readonly_pointer_slice_element_type(&param.ty).is_some())
        .map(|param| (param.name.as_str(), &param.ty))
        .collect::<HashMap<_, _>>();
    let mut uses = ReadonlyPointerParamUses::default();
    collect_readonly_pointer_read_params_from_body(body, &readonly_pointer_params, &mut uses)?;
    Ok(uses)
}

fn validate_readonly_pointer_slice_lowering_evidence(
    params: &[IrParam],
    byte_slice_params: &HashSet<String>,
    nullable_pointer_params: &HashSet<String>,
    readonly_pointer_read_params: &HashSet<String>,
    readonly_pointer_mentioned_params: &HashSet<String>,
) -> Result<(), String> {
    for param in params {
        if readonly_pointer_slice_element_type(&param.ty).is_some()
            && !byte_slice_params.contains(&param.name)
            && !nullable_pointer_params.contains(&param.name)
            && !readonly_pointer_read_params.contains(&param.name)
            && !readonly_pointer_mentioned_params.contains(&param.name)
        {
            return Err(format!(
                "readonly pointer param {} requires pointer-to-slice lowering evidence before lowering {} to &[T]",
                param.name,
                type_label(&param.ty)
            ));
        }
    }
    Ok(())
}

fn collect_mutable_pointer_write_params_from_body(
    body: &[IrStmt],
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                collect_mutable_pointer_write_param_from_target(
                    target,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_mutable_pointer_write_params_from_body(
                    then_body,
                    mutable_pointer_params,
                    write_params,
                )?;
                collect_mutable_pointer_write_params_from_body(
                    else_body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_mutable_pointer_write_params_from_body(
                    body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_mutable_pointer_write_params_from_body(
                    init,
                    mutable_pointer_params,
                    write_params,
                )?;
                if let Some(step) = step {
                    collect_mutable_pointer_write_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        mutable_pointer_params,
                        write_params,
                    )?;
                }
                collect_mutable_pointer_write_params_from_body(
                    body,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Expr { expr, .. } => {
                collect_c_memset_mutable_pointer_write_param(
                    expr,
                    mutable_pointer_params,
                    write_params,
                )?;
                collect_c_memcpy_mutable_pointer_write_param(
                    expr,
                    mutable_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_c_memset_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return Ok(());
    };
    if callee == "memset" && args.len() == 3 {
        collect_direct_mutable_pointer_write_param(&args[0], mutable_pointer_params, write_params)?;
    }
    Ok(())
}

fn collect_c_memcpy_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return Ok(());
    };
    if callee == "memcpy" && args.len() == 3 {
        collect_direct_mutable_pointer_write_param(&args[0], mutable_pointer_params, write_params)?;
    }
    Ok(())
}

fn collect_mutable_pointer_write_param_from_target(
    target: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    match target {
        IrExpr::Index { base, .. } => {
            collect_direct_mutable_pointer_write_param(base, mutable_pointer_params, write_params)
        }
        IrExpr::Deref { ptr, .. } => match ptr.as_ref() {
            IrExpr::Binary { .. } => {
                if let Some((base, _)) = mutable_pointer_add_operands_from_expr(ptr.as_ref()) {
                    collect_direct_mutable_pointer_write_param(
                        base,
                        mutable_pointer_params,
                        write_params,
                    )?;
                }
                Ok(())
            }
            expr => collect_direct_mutable_pointer_write_param(
                expr,
                mutable_pointer_params,
                write_params,
            ),
        },
        _ => Ok(()),
    }
}

fn mutable_pointer_add_operands_from_expr(expr: &IrExpr) -> Option<(&IrExpr, &IrExpr)> {
    let IrExpr::Binary { lhs, rhs, .. } = expr else {
        return None;
    };
    mutable_pointer_add_operands(lhs, rhs)
}

fn collect_direct_mutable_pointer_write_param(
    expr: &IrExpr,
    mutable_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        return Ok(());
    };
    if mutable_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == ty)
    {
        write_params.insert(name.to_string());
    }
    Ok(())
}

fn collect_readonly_pointer_read_params_from_body(
    body: &[IrStmt],
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Decl { init, .. } => {
                if let Some(init) = init {
                    collect_readonly_pointer_read_params_from_expr(
                        init,
                        readonly_pointer_params,
                        uses,
                    )?;
                }
            }
            IrStmt::Assign { target, value, .. } => {
                collect_readonly_pointer_read_params_from_expr(
                    target,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_expr(
                    value,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::If {
                condition,
                then_body,
                else_body,
                ..
            } => {
                collect_readonly_pointer_read_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_body(
                    then_body,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_body(
                    else_body,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::While {
                condition, body, ..
            } => {
                collect_readonly_pointer_read_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_body(
                    body,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                collect_readonly_pointer_read_params_from_body(
                    body,
                    readonly_pointer_params,
                    uses,
                )?;
                collect_readonly_pointer_read_params_from_expr(
                    condition,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::For {
                init,
                condition,
                step,
                body,
                ..
            } => {
                collect_readonly_pointer_read_params_from_body(
                    init,
                    readonly_pointer_params,
                    uses,
                )?;
                if let Some(condition) = condition {
                    collect_readonly_pointer_read_params_from_expr(
                        condition,
                        readonly_pointer_params,
                        uses,
                    )?;
                }
                if let Some(step) = step {
                    collect_readonly_pointer_read_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        readonly_pointer_params,
                        uses,
                    )?;
                }
                collect_readonly_pointer_read_params_from_body(
                    body,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::Return { value, .. } => {
                if let Some(value) = value {
                    collect_readonly_pointer_read_params_from_expr(
                        value,
                        readonly_pointer_params,
                        uses,
                    )?;
                }
            }
            IrStmt::Expr { expr, .. } => {
                collect_readonly_pointer_read_params_from_expr(
                    expr,
                    readonly_pointer_params,
                    uses,
                )?;
            }
            IrStmt::Break { .. } | IrStmt::Continue { .. } | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_readonly_pointer_read_params_from_expr(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    collect_direct_readonly_pointer_mentioned_param(expr, readonly_pointer_params, uses)?;
    match expr {
        IrExpr::Index { base, index, .. } => {
            collect_direct_readonly_pointer_read_param(base, readonly_pointer_params, uses)?;
            collect_readonly_pointer_read_params_from_expr(base, readonly_pointer_params, uses)?;
            collect_readonly_pointer_read_params_from_expr(index, readonly_pointer_params, uses)?;
        }
        IrExpr::Deref { ptr, .. } => {
            collect_direct_readonly_pointer_read_param(ptr, readonly_pointer_params, uses)?;
            if let Some((base, _)) = readonly_pointer_add_operands_from_expr(ptr.as_ref()) {
                collect_direct_readonly_pointer_read_param(base, readonly_pointer_params, uses)?;
            }
            collect_readonly_pointer_read_params_from_expr(ptr, readonly_pointer_params, uses)?;
        }
        IrExpr::Binary { lhs, rhs, .. } => {
            collect_readonly_pointer_read_params_from_expr(lhs, readonly_pointer_params, uses)?;
            collect_readonly_pointer_read_params_from_expr(rhs, readonly_pointer_params, uses)?;
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. }
        | IrExpr::Member { base: operand, .. }
        | IrExpr::IncDec {
            target: operand, ..
        } => {
            collect_readonly_pointer_read_params_from_expr(operand, readonly_pointer_params, uses)?;
        }
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            collect_readonly_pointer_read_params_from_expr(
                condition,
                readonly_pointer_params,
                uses,
            )?;
            collect_readonly_pointer_read_params_from_expr(
                then_expr,
                readonly_pointer_params,
                uses,
            )?;
            collect_readonly_pointer_read_params_from_expr(
                else_expr,
                readonly_pointer_params,
                uses,
            )?;
        }
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                collect_readonly_pointer_read_params_from_expr(
                    element,
                    readonly_pointer_params,
                    uses,
                )?;
            }
        }
        IrExpr::Call { callee, args, .. } => {
            if callee == "strlen" && args.len() == 1 {
                collect_direct_readonly_pointer_read_param(
                    &args[0],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            if callee == "strnlen" && args.len() == 2 {
                collect_direct_readonly_pointer_read_param(
                    &args[0],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            if callee == "memcmp" && args.len() == 3 {
                collect_direct_readonly_pointer_read_param(
                    &args[0],
                    readonly_pointer_params,
                    uses,
                )?;
                collect_direct_readonly_pointer_read_param(
                    &args[1],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            if callee == "memcpy" && args.len() == 3 {
                collect_direct_readonly_pointer_read_param(
                    &args[1],
                    readonly_pointer_params,
                    uses,
                )?;
            }
            for arg in args {
                collect_readonly_pointer_read_params_from_expr(arg, readonly_pointer_params, uses)?;
            }
        }
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => {}
    }
    Ok(())
}

fn readonly_pointer_add_operands_from_expr(expr: &IrExpr) -> Option<(&IrExpr, &IrExpr)> {
    let IrExpr::Binary { lhs, rhs, .. } = expr else {
        return None;
    };
    readonly_pointer_add_operands(lhs, rhs)
}

fn collect_direct_readonly_pointer_read_param(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    match expr {
        IrExpr::Var { name, ty, .. } => {
            if readonly_pointer_params
                .get(name.as_str())
                .is_some_and(|param_ty| *param_ty == ty)
            {
                uses.read_params.insert(name.to_string());
                uses.mentioned_params.insert(name.to_string());
            }
        }
        IrExpr::IncDec { target, .. } => {
            collect_direct_readonly_pointer_read_param(target, readonly_pointer_params, uses)?
        }
        _ => {}
    }
    Ok(())
}

fn collect_direct_readonly_pointer_mentioned_param(
    expr: &IrExpr,
    readonly_pointer_params: &HashMap<&str, &IrType>,
    uses: &mut ReadonlyPointerParamUses,
) -> Result<(), String> {
    let IrExpr::Var { name, ty, .. } = expr else {
        return Ok(());
    };
    if readonly_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == ty)
    {
        uses.mentioned_params.insert(name.to_string());
    }
    Ok(())
}

fn collect_mutable_record_pointer_write_params_from_body(
    body: &[IrStmt],
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                collect_mutable_record_pointer_write_param_from_target(
                    target,
                    mutable_record_pointer_params,
                    write_params,
                )?
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_mutable_record_pointer_write_params_from_body(
                    then_body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                collect_mutable_record_pointer_write_params_from_body(
                    else_body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::While { body, .. } | IrStmt::DoWhile { body, .. } => {
                collect_mutable_record_pointer_write_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_mutable_record_pointer_write_params_from_body(
                    init,
                    mutable_record_pointer_params,
                    write_params,
                )?;
                if let Some(step) = step {
                    collect_mutable_record_pointer_write_params_from_body(
                        std::slice::from_ref(step.as_ref()),
                        mutable_record_pointer_params,
                        write_params,
                    )?;
                }
                collect_mutable_record_pointer_write_params_from_body(
                    body,
                    mutable_record_pointer_params,
                    write_params,
                )?;
            }
            IrStmt::Decl { .. }
            | IrStmt::Return { .. }
            | IrStmt::Break { .. }
            | IrStmt::Continue { .. }
            | IrStmt::Expr { .. }
            | IrStmt::Unsupported { .. } => {}
        }
    }
    Ok(())
}

fn collect_mutable_record_pointer_write_param_from_target(
    target: &IrExpr,
    mutable_record_pointer_params: &HashMap<&str, &IrType>,
    write_params: &mut HashSet<String>,
) -> Result<(), String> {
    let IrExpr::Member {
        base,
        field,
        ty,
        is_arrow: true,
        ..
    } = target
    else {
        return Ok(());
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(());
    };
    if !mutable_record_pointer_params
        .get(name.as_str())
        .is_some_and(|param_ty| *param_ty == base_ty)
    {
        return Ok(());
    }
    emit_record_field_type(ty)
        .map_err(|detail| format!("mutable record pointer arrow field {field} has {detail}"))?;
    write_params.insert(name.clone());
    Ok(())
}

fn validate_nullable_pointer_param_uses_in_body(
    body: &[IrStmt],
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &mut HashSet<String>,
) -> Result<(), String> {
    for stmt in body {
        validate_nullable_pointer_param_uses_in_stmt(stmt, nullable_params, proven_nonnull_params)?;
        if let Some(param) = null_return_guard_proves_nonnull(stmt, nullable_params) {
            proven_nonnull_params.insert(param.to_string());
        }
    }
    Ok(())
}

/// Enforces the semantic boundary for nullable pointer parameters in one stmt.
///
/// Nullable pointers may only be dereferenced, indexed, or member-accessed after
/// a local guard has proven the parameter non-null on that path. The checker
/// carries simple branch and early-return facts but does not infer loop
/// invariants or global alias guarantees.
fn validate_nullable_pointer_param_uses_in_stmt(
    stmt: &IrStmt,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<(), String> {
    if nullable_params.is_empty() {
        return Ok(());
    }
    match stmt {
        IrStmt::Decl { init, .. } => {
            if let Some(init) = init {
                validate_nullable_pointer_param_uses_in_expr(
                    init,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
        }
        IrStmt::Assign { target, value, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                target,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                value,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
            let mut then_nonnull_params = proven_nonnull_params.clone();
            let mut else_nonnull_params = proven_nonnull_params.clone();
            match null_comparison_nonnull_branch(condition, nullable_params) {
                Some(NullComparisonNonnullBranch::Then { param }) => {
                    then_nonnull_params.insert(param.to_string());
                }
                Some(NullComparisonNonnullBranch::Else { param }) => {
                    else_nonnull_params.insert(param.to_string());
                }
                None => {}
            }
            validate_nullable_pointer_param_uses_in_body(
                then_body,
                nullable_params,
                &mut then_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_body(
                else_body,
                nullable_params,
                &mut else_nonnull_params,
            )?;
        }
        IrStmt::While {
            condition, body, ..
        } => {
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
            let mut loop_nonnull_params = proven_nonnull_params.clone();
            validate_nullable_pointer_param_uses_in_body(
                body,
                nullable_params,
                &mut loop_nonnull_params,
            )?;
        }
        IrStmt::DoWhile {
            body, condition, ..
        } => {
            let mut loop_nonnull_params = proven_nonnull_params.clone();
            validate_nullable_pointer_param_uses_in_body(
                body,
                nullable_params,
                &mut loop_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::For {
            init,
            condition,
            step,
            body,
            ..
        } => {
            let mut loop_nonnull_params = proven_nonnull_params.clone();
            validate_nullable_pointer_param_uses_in_body(
                init,
                nullable_params,
                &mut loop_nonnull_params,
            )
            .map_err(|detail| format!("for init {detail}"))?;
            if let Some(condition) = condition {
                validate_nullable_pointer_param_uses_in_expr(
                    condition,
                    nullable_params,
                    &loop_nonnull_params,
                )?;
            }
            if let Some(step) = step {
                validate_nullable_pointer_param_uses_in_stmt(
                    step,
                    nullable_params,
                    &loop_nonnull_params,
                )?;
            }
            validate_nullable_pointer_param_uses_in_body(
                body,
                nullable_params,
                &mut loop_nonnull_params,
            )?;
        }
        IrStmt::Return { value, .. } => {
            if let Some(value) = value {
                validate_nullable_pointer_param_uses_in_expr(
                    value,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
        }
        IrStmt::Break { .. } | IrStmt::Continue { .. } => {}
        IrStmt::Expr { expr, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                expr,
                nullable_params,
                proven_nonnull_params,
            )?;
        }
        IrStmt::Unsupported { .. } => {}
    }
    Ok(())
}

fn validate_nullable_pointer_param_uses_in_expr(
    expr: &IrExpr,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<(), String> {
    if let IrExpr::Binary {
        op: IrBinOp::Eq | IrBinOp::Neq,
        lhs,
        rhs,
        ..
    } = expr
    {
        if null_pointer_comparison_var(lhs, rhs)
            .is_some_and(|(name, _)| nullable_params.contains(name))
        {
            return Ok(());
        }
    }
    if nullable_record_pointer_arrow_read_is_proven_nonnull(
        expr,
        nullable_params,
        proven_nonnull_params,
    )? {
        return Ok(());
    }
    match expr {
        IrExpr::Var { name, .. } if nullable_params.contains(name) => Err(format!(
            "nullable pointer param {name} is only supported in null comparisons"
        )),
        IrExpr::Binary { lhs, rhs, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                lhs,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                rhs,
                nullable_params,
                proven_nonnull_params,
            )
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => validate_nullable_pointer_param_uses_in_expr(
            operand,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::Conditional {
            condition,
            then_expr,
            else_expr,
            ..
        } => {
            validate_nullable_pointer_param_uses_in_expr(
                condition,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                then_expr,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                else_expr,
                nullable_params,
                proven_nonnull_params,
            )
        }
        IrExpr::Index { base, index, .. } => {
            validate_nullable_pointer_param_uses_in_expr(
                base,
                nullable_params,
                proven_nonnull_params,
            )?;
            validate_nullable_pointer_param_uses_in_expr(
                index,
                nullable_params,
                proven_nonnull_params,
            )
        }
        IrExpr::Member { base, .. } => validate_nullable_pointer_param_uses_in_expr(
            base,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::ArrayLiteral { elements, .. } => {
            for element in elements {
                validate_nullable_pointer_param_uses_in_expr(
                    element,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
            Ok(())
        }
        IrExpr::Call { args, .. } => {
            for arg in args {
                validate_nullable_pointer_param_uses_in_expr(
                    arg,
                    nullable_params,
                    proven_nonnull_params,
                )?;
            }
            Ok(())
        }
        IrExpr::IncDec { target, .. } => validate_nullable_pointer_param_uses_in_expr(
            target,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::Deref { ptr, .. } => validate_nullable_pointer_param_uses_in_expr(
            ptr,
            nullable_params,
            proven_nonnull_params,
        ),
        IrExpr::LitInt { .. }
        | IrExpr::NullPtr { .. }
        | IrExpr::Var { .. }
        | IrExpr::Unsupported { .. } => Ok(()),
    }
}

fn null_return_guard_proves_nonnull<'a>(
    stmt: &'a IrStmt,
    nullable_params: &HashSet<String>,
) -> Option<&'a str> {
    let IrStmt::If {
        condition,
        then_body,
        else_body,
        ..
    } = stmt
    else {
        return None;
    };
    if !else_body.is_empty() || !matches!(then_body.as_slice(), [IrStmt::Return { .. }]) {
        return None;
    }
    let IrExpr::Binary {
        op: IrBinOp::Eq,
        lhs,
        rhs,
        ..
    } = condition
    else {
        return None;
    };
    let Some((name, _)) = null_pointer_comparison_var(lhs, rhs) else {
        return None;
    };
    nullable_params.contains(name).then_some(name)
}

enum NullComparisonNonnullBranch<'a> {
    Then { param: &'a str },
    Else { param: &'a str },
}

fn null_comparison_nonnull_branch<'a>(
    condition: &'a IrExpr,
    nullable_params: &HashSet<String>,
) -> Option<NullComparisonNonnullBranch<'a>> {
    let IrExpr::Binary { op, lhs, rhs, .. } = condition else {
        return None;
    };
    let Some((name, _)) = null_pointer_comparison_var(lhs, rhs) else {
        return None;
    };
    if !nullable_params.contains(name) {
        return None;
    }
    match op {
        IrBinOp::Neq => Some(NullComparisonNonnullBranch::Then { param: name }),
        IrBinOp::Eq => Some(NullComparisonNonnullBranch::Else { param: name }),
        _ => None,
    }
}

fn nullable_record_pointer_arrow_read_is_proven_nonnull(
    expr: &IrExpr,
    nullable_params: &HashSet<String>,
    proven_nonnull_params: &HashSet<String>,
) -> Result<bool, String> {
    let IrExpr::Member {
        base,
        field,
        ty: member_ty,
        is_arrow: true,
        ..
    } = expr
    else {
        return Ok(false);
    };
    let IrExpr::Var {
        name, ty: base_ty, ..
    } = base.as_ref()
    else {
        return Ok(false);
    };
    if !nullable_params.contains(name) || !proven_nonnull_params.contains(name) {
        return Ok(false);
    }
    if readonly_record_pointer_pointee_type(base_ty).is_none() {
        return Ok(false);
    }
    emit_scalar_type(member_ty)
        .map_err(|detail| format!("nullable record pointer arrow field {field} has {detail}"))?;
    Ok(true)
}

fn collect_param_symbols(params: &[IrParam]) -> Result<HashSet<String>, String> {
    let mut symbols = HashSet::new();
    for param in params {
        if !symbols.insert(param.name.clone()) {
            return Err(format!(
                "param {} duplicates an existing symbol",
                param.name
            ));
        }
    }
    Ok(symbols)
}

fn collect_assigned_vars_from_body(body: &[IrStmt], assigned_vars: &mut HashSet<String>) {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                if let Some(name) = assigned_var_name_from_target(target) {
                    assigned_vars.insert(name.clone());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_assigned_vars_from_body(then_body, assigned_vars);
                collect_assigned_vars_from_body(else_body, assigned_vars);
            }
            IrStmt::While {
                condition, body, ..
            } => {
                if let IrExpr::IncDec {
                    target,
                    op: IrIncDecOp::Dec,
                    ..
                } = condition
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            IrStmt::DoWhile {
                body, condition, ..
            } => {
                if let IrExpr::IncDec {
                    target,
                    op: IrIncDecOp::Dec,
                    ..
                } = condition
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            IrStmt::For {
                init, step, body, ..
            } => {
                collect_assigned_vars_from_body(init, assigned_vars);
                if let Some(step) = step {
                    collect_assigned_vars_from_body(
                        std::slice::from_ref(step.as_ref()),
                        assigned_vars,
                    );
                }
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            IrStmt::Expr { expr, .. } => {
                if let Some(name) =
                    c_memset_assigned_var_name(expr).or_else(|| c_memcpy_assigned_var_name(expr))
                {
                    assigned_vars.insert(name.clone());
                }
                if let IrExpr::IncDec {
                    target,
                    prefix: true,
                    ..
                } = expr
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
            }
            _ => {}
        }
    }
}

fn c_memset_assigned_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return None;
    };
    if callee != "memset" || args.len() != 3 {
        return None;
    }
    match &args[0] {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

fn c_memcpy_assigned_var_name(expr: &IrExpr) -> Option<&String> {
    let IrExpr::Call { callee, args, .. } = expr else {
        return None;
    };
    if callee != "memcpy" || args.len() != 3 {
        return None;
    }
    match &args[0] {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

fn assigned_var_name_from_target(target: &IrExpr) -> Option<&String> {
    match target {
        IrExpr::Var { name, .. } => Some(name),
        IrExpr::Index { base, .. } => match base.as_ref() {
            IrExpr::Var { name, .. } => Some(name),
            _ => None,
        },
        IrExpr::Deref { ptr, .. } => pointer_write_base_name_from_ptr(ptr),
        IrExpr::Member { base, .. } => match base.as_ref() {
            IrExpr::Var { name, .. } => Some(name),
            _ => None,
        },
        _ => None,
    }
}

fn pointer_write_base_name_from_ptr(ptr: &IrExpr) -> Option<&String> {
    match ptr {
        IrExpr::Var { name, .. } => Some(name),
        IrExpr::Binary {
            op: IrBinOp::Add,
            lhs,
            rhs,
            ..
        } => mutable_pointer_add_operands(lhs, rhs).and_then(|(base, _)| match base {
            IrExpr::Var { name, .. } => Some(name),
            _ => None,
        }),
        _ => None,
    }
}

fn expr_type(expr: &IrExpr) -> Option<&IrType> {
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
        | IrExpr::AddrOf { ty, .. } => Some(ty),
        IrExpr::Cast { target, .. } => Some(target),
        IrExpr::Unsupported { .. } => None,
    }
}

fn null_pointer_comparison_var<'a>(
    lhs: &'a IrExpr,
    rhs: &'a IrExpr,
) -> Option<(&'a str, &'a IrType)> {
    match (lhs, rhs) {
        (
            IrExpr::Var {
                name,
                ty: pointer_ty,
                ..
            },
            IrExpr::NullPtr { ty: null_ty, .. },
        ) if matches!(pointer_ty.kind, IrTypeKind::Pointer { .. })
            && matches!(null_ty.kind, IrTypeKind::Pointer { .. }) =>
        {
            Some((name.as_str(), pointer_ty))
        }
        (
            IrExpr::NullPtr { ty: null_ty, .. },
            IrExpr::Var {
                name,
                ty: pointer_ty,
                ..
            },
        ) if matches!(pointer_ty.kind, IrTypeKind::Pointer { .. })
            && matches!(null_ty.kind, IrTypeKind::Pointer { .. }) =>
        {
            Some((name.as_str(), pointer_ty))
        }
        _ => None,
    }
}

fn is_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { .. })
}

fn is_unsigned_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { signed: false, .. })
}

fn is_unsigned_8_bit_integer_type(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    )
}

fn is_signed_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { signed: true, .. })
}

fn readonly_pointer_slice_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } if pointee.is_const && is_integer_type(pointee) => {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

fn readonly_record_pointer_pointee_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee }
            if pointee.is_const && matches!(pointee.kind, IrTypeKind::Record { .. }) =>
        {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

fn mutable_record_pointer_pointee_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee }
            if !pointee.is_const && matches!(pointee.kind, IrTypeKind::Record { .. }) =>
        {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

fn record_pointer_pointee_type(ty: &IrType) -> Option<&IrType> {
    readonly_record_pointer_pointee_type(ty).or_else(|| mutable_record_pointer_pointee_type(ty))
}

fn is_supported_nullable_pointer_type(ty: &IrType) -> bool {
    readonly_pointer_slice_element_type(ty).is_some()
        || readonly_record_pointer_pointee_type(ty).is_some()
}

fn validate_nullable_pointer_type(name: &str, ty: &IrType) -> Result<(), String> {
    if is_supported_nullable_pointer_type(ty) {
        return Ok(());
    }
    Err(format!(
        "nullable pointer param {name} has unsupported type {}",
        type_label(ty)
    ))
}

fn mutable_pointer_slice_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } if !pointee.is_const && is_integer_type(pointee) => {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

fn fixed_integer_array_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Array {
            element,
            len: Some(_),
        } if is_integer_type(element) => Some(element.as_ref()),
        _ => None,
    }
}

fn readonly_global_array_element_type(global: &IrGlobal) -> Result<&IrType, String> {
    let IrTypeKind::Array { element, len } = &global.ty.kind else {
        return Err(format!(
            "global {} has unsupported type {}",
            global.name,
            type_label(&global.ty)
        ));
    };
    if !global.ty.is_const {
        return Err(format!("global {} is not readonly const", global.name));
    }
    if len.is_none() {
        return Err(format!("global {} array length is unknown", global.name));
    }
    if !is_integer_type(element) {
        return Err(format!(
            "global {} element type {} is unsupported",
            global.name,
            type_label(element)
        ));
    }
    Ok(element.as_ref())
}

fn validate_global_expr_type(global: &IrGlobal, ty: &IrType) -> Result<(), String> {
    if &global.ty == ty {
        Ok(())
    } else {
        Err(format!(
            "global {} type {} does not match expression type {}",
            global.name,
            type_label(&global.ty),
            type_label(ty)
        ))
    }
}

fn is_c_int_type(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    )
}

fn is_void_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Void)
}

fn is_c_memset_discarded_result_type(ty: &IrType) -> bool {
    is_void_type(ty) || is_mutable_void_pointer(ty)
}

fn is_c_memcpy_discarded_result_type(ty: &IrType) -> bool {
    is_void_type(ty) || is_mutable_void_pointer(ty)
}

fn is_mutable_void_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            !pointee.is_const && matches!(pointee.kind, IrTypeKind::Void)
        }
        _ => false,
    }
}

fn is_const_void_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            pointee.is_const && matches!(pointee.kind, IrTypeKind::Void)
        }
        _ => false,
    }
}

fn is_size_t_type(ty: &IrType) -> bool {
    ty.spelled == "size_t" || ty.canonical == "size_t"
}

fn type_label(ty: &IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        ty.spelled.clone()
    } else if !ty.canonical.trim().is_empty() {
        ty.canonical.clone()
    } else {
        format!("{:?}", ty.kind)
    }
}

fn emit_identifier(name: &str, context: &str) -> Result<String, String> {
    if is_rust_identifier(name) && !is_rust_keyword(name) {
        Ok(name.to_string())
    } else {
        Err(format!("{context} identifier {name:?} is unsupported"))
    }
}

fn emit_global_const_identifier(name: &str) -> Result<String, String> {
    let mut output = String::new();
    let mut previous_was_underscore = false;
    for character in name.chars() {
        if character.is_ascii_alphanumeric() {
            output.push(character.to_ascii_uppercase());
            previous_was_underscore = false;
        } else if character == '_' && !previous_was_underscore {
            output.push('_');
            previous_was_underscore = true;
        } else {
            return Err(format!("global identifier {name:?} is unsupported"));
        }
    }
    while output.ends_with('_') {
        output.pop();
    }
    if output.is_empty()
        || output
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_digit())
    {
        return Err(format!("global identifier {name:?} is unsupported"));
    }
    Ok(output)
}

fn emit_record_type_name(name: &str) -> Result<String, String> {
    if !is_rust_identifier(name) || is_rust_keyword(name) {
        return Err(format!("record type name {name:?} is unsupported"));
    }
    let mut output = String::new();
    let mut uppercase_next = true;
    for character in name.chars() {
        if character == '_' {
            uppercase_next = true;
            continue;
        }
        if !character.is_ascii_alphanumeric() {
            return Err(format!("record type name {name:?} is unsupported"));
        }
        if uppercase_next {
            output.push(character.to_ascii_uppercase());
            uppercase_next = false;
        } else {
            output.push(character);
        }
    }
    if output.is_empty()
        || output
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_digit())
        || is_rust_keyword(&output)
    {
        return Err(format!("record type name {name:?} is unsupported"));
    }
    Ok(output)
}

fn is_rust_identifier(name: &str) -> bool {
    if name == "_" {
        return false;
    }
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|character| character == '_' || character.is_ascii_alphanumeric())
}

fn is_rust_keyword(name: &str) -> bool {
    matches!(
        name,
        "as" | "async"
            | "await"
            | "break"
            | "const"
            | "continue"
            | "crate"
            | "dyn"
            | "else"
            | "enum"
            | "extern"
            | "false"
            | "fn"
            | "for"
            | "if"
            | "impl"
            | "in"
            | "let"
            | "loop"
            | "match"
            | "mod"
            | "move"
            | "mut"
            | "pub"
            | "ref"
            | "return"
            | "self"
            | "Self"
            | "static"
            | "struct"
            | "super"
            | "trait"
            | "true"
            | "type"
            | "union"
            | "unsafe"
            | "use"
            | "where"
            | "while"
            | "abstract"
            | "become"
            | "box"
            | "do"
            | "final"
            | "macro"
            | "override"
            | "priv"
            | "try"
            | "typeof"
            | "unsized"
            | "virtual"
            | "yield"
    )
}

fn is_u8(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    )
}

fn is_8_bit_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { width: 8, .. })
}

fn is_usize(ty: &IrType) -> bool {
    ty.spelled == "size_t"
        || ty.canonical == "size_t"
        || matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        )
}

fn is_c_strlen_result_type(ty: &IrType) -> bool {
    is_c_size_argument_type(ty)
}

fn is_c_size_argument_type(ty: &IrType) -> bool {
    ty.spelled == "size_t"
        || ty.canonical == "size_t"
        || ty.spelled == "usize"
        || ty.canonical == "usize"
}

fn is_u8_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => is_u8(pointee),
        _ => false,
    }
}

fn is_post_inc_var(expr: &IrExpr, expected_name: &str) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if var_name(target) == Some(expected_name)
    )
}

fn is_post_inc_expr(expr: &IrExpr) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if matches!(target.as_ref(), IrExpr::Var { .. })
    )
}

fn var_name(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}
