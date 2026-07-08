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
//! arithmetic is decomposed into element access. Array/function-to-pointer decay is explicit.
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
//! - Floating-point, enum, union, and general pointer types fail closed.
//! - Function pointers are admitted only for narrow direct-call, local-initializer, local-assignment, and return shapes.
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
use std::collections::{HashMap, HashSet};
use std::hash::Hash;

mod definite_assignment;
mod ir;
mod rust_types;

use definite_assignment::*;
pub use ir::{
    EmitPolicy, IrBinOp, IrEmitError, IrExpr, IrFunction, IrGlobal, IrGlobalInit, IrIncDecOp,
    IrParam, IrRecordField, IrStmt, IrType, IrTypeKind, IrUnOp, NoAliasParamPair,
    SignedRightShiftPolicy, SourceSpan,
};
use rust_types::*;

include!("context.rs");
include!("emitter_entry.rs");
include!("params.rs");
include!("records.rs");
include!("globals.rs");
include!("statements.rs");
include!("expressions.rs");
include!("memory_calls.rs");
include!("call_validation.rs");
include!("side_effects.rs");
include!("arithmetic.rs");
include!("type_validation.rs");
include!("local_analysis.rs");
include!("pointer_analysis.rs");
include!("nullable_validation.rs");
include!("symbols.rs");
