//! Legacy string translator for bounded compatibility candidates.
//!
//! This module is a compatibility-only candidate source. It recognizes a small
//! historical subset of C by string shape, then emits candidate Rust plus route
//! evidence for that subset. It is not a C semantic authority; new forward
//! translation should prefer clang lowering into typed IR and use this path only
//! where existing compatibility fixtures still depend on it.

use crate::{
    BuildProfile, CallExpressionEvidence, CfgBlock, CfgFunction, PointerEdge, PointerNode,
    SliceSpec, StructuredControlFlowEvidence, TranslationError, TranslationPlan, TranslationResult,
    TranslationSource, TypeMapping, TypeUncertainty,
};

include!("legacy_translation/model.rs");
include!("legacy_translation/pipeline.rs");
include!("legacy_translation/parse.rs");
include!("legacy_translation/control_flow.rs");
include!("legacy_translation/statements.rs");
include!("legacy_translation/cfg.rs");
include!("legacy_translation/lvalues.rs");
include!("legacy_translation/statement_parse.rs");
include!("legacy_translation/refusals.rs");
include!("legacy_translation/calls.rs");
include!("legacy_translation/type_map.rs");
include!("legacy_translation/pointer_graph.rs");
include!("legacy_translation/buffers.rs");
include!("legacy_translation/emitter.rs");
include!("legacy_translation/tests.rs");
