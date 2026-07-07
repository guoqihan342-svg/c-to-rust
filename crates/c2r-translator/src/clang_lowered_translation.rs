//! Evidence bridge for clang-lowered typed IR.
//!
//! This module connects the clang frontend and typed IR emitter to
//! `TranslationResult`. It is not a Rust generator: `typed_ir` decides whether a
//! function can be emitted and fails closed when it cannot. This layer records
//! the accepted IR as route, CFG, call-expression, type-map, and pointer
//! evidence for downstream gates and reports.

include!("clang_lowered_translation_split_parts/part_00.rs");
include!("clang_lowered_translation_split_parts/part_01.rs");
include!("clang_lowered_translation_split_parts/part_02.rs");
include!("clang_lowered_translation_split_parts/part_03.rs");
