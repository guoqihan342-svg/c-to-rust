//! Translation route metadata for typed IR candidate generation.
//!
//! # Candidate Route Model
//!
//! This module defines the route metadata that accompanies every typed IR Rust draft.
//! The route describes **how** the candidate was produced, not whether it is correct.
//!
//! ## Current Route States
//!
//! - `GenericTypedIr`: the generic typed IR emitter successfully produced a Rust candidate.
//!   This does not mean the candidate is semantically correct — only that the emitter
//!   recognized the IR shape and emitted compilable Rust.
//! - `Unsupported`: the typed IR emitter fail-closed. No Rust candidate was produced.
//!   The `CandidateRouteReason` records the specific fail-closed reason.
//!
//! ## Key Design Principle
//!
//! **Candidate route does not decide semantic acceptance.** It only answers:
//! "Which generator produced this candidate, or why was no candidate produced?"
//! Semantic acceptance is always decided by the validation profile + evidence gates
//! (C oracle, Rust replay, schema diff, negative diff, unsafe ledger, final verification).
//!
//! ## Relationship to Evidence Route Decision
//!
//! `CandidateRouteDecision` (this module) is a typed IR-level metadata record.
//! `validation/tools/auto_migrate.py` produces an evidence-level `route_decision.json`
//! that answers "what is the migration path and budget for the whole slice?"
//! The two are distinct but the former is embedded as provenance into the latter.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum CandidateRoute {
    GenericTypedIr,
    Unsupported,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum CandidateGenerator {
    GenericTypedIrEmitter,
    None,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CandidateRouteReason {
    pub code: String,
    pub detail: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CandidateRouteDecision {
    pub route_id: String,
    pub route: CandidateRoute,
    pub candidate_generator: CandidateGenerator,
    pub reasons: Vec<CandidateRouteReason>,
    pub fallback: Option<CandidateRoute>,
    pub token_cost: u32,
    pub deprecated: bool,
    pub replacement: Option<CandidateRoute>,
    pub delete_when: Vec<String>,
    pub suggested_required_gates: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct EmittedRust {
    pub rust: String,
    pub route: CandidateRouteDecision,
}

impl std::ops::Deref for EmittedRust {
    type Target = str;

    fn deref(&self) -> &Self::Target {
        &self.rust
    }
}

impl AsRef<str> for EmittedRust {
    fn as_ref(&self) -> &str {
        &self.rust
    }
}

pub fn generic_typed_ir_route() -> CandidateRouteDecision {
    CandidateRouteDecision {
        route_id: "generic-typed-ir".to_string(),
        route: CandidateRoute::GenericTypedIr,
        candidate_generator: CandidateGenerator::GenericTypedIrEmitter,
        reasons: vec![CandidateRouteReason {
            code: "generic_typed_ir_subset".to_string(),
            detail: "typed IR matched the current generic emitter subset".to_string(),
        }],
        fallback: None,
        token_cost: 0,
        deprecated: false,
        replacement: None,
        delete_when: Vec::new(),
        suggested_required_gates: vec![
            "rustc_smoke".to_string(),
            "typed_ir_contract_tests".to_string(),
        ],
    }
}

pub fn unsupported_route(reason: impl Into<String>) -> CandidateRouteDecision {
    CandidateRouteDecision {
        route_id: "unsupported".to_string(),
        route: CandidateRoute::Unsupported,
        candidate_generator: CandidateGenerator::None,
        reasons: vec![CandidateRouteReason {
            code: "outside_typed_ir_emitter_subset".to_string(),
            detail: reason.into(),
        }],
        fallback: None,
        token_cost: 0,
        deprecated: false,
        replacement: None,
        delete_when: Vec::new(),
        suggested_required_gates: vec!["manual_review".to_string()],
    }
}
