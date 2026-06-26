use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum CandidateRoute {
    DeprecatedLegacyCrc32,
    GenericTypedIr,
    Unsupported,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum CandidateGenerator {
    LegacyCrc32Emitter,
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

pub const LEGACY_CRC32_DELETE_WHEN: &[&str] = &[
    "readonly global const table IR is supported",
    "real FlashDB crc32 emits through GenericTypedIr",
    "legacy crc32 matcher has no remaining callers",
];

pub fn deprecated_legacy_crc32_route() -> CandidateRouteDecision {
    CandidateRouteDecision {
        route_id: "deprecated-legacy-crc32-byte-cursor".to_string(),
        route: CandidateRoute::DeprecatedLegacyCrc32,
        candidate_generator: CandidateGenerator::LegacyCrc32Emitter,
        reasons: vec![CandidateRouteReason {
            code: "legacy_crc32_byte_cursor_match".to_string(),
            detail:
                "temporary crc32 byte-cursor matcher kept as an explicit deprecated candidate route"
                    .to_string(),
        }],
        fallback: Some(CandidateRoute::GenericTypedIr),
        token_cost: 0,
        deprecated: true,
        replacement: Some(CandidateRoute::GenericTypedIr),
        delete_when: LEGACY_CRC32_DELETE_WHEN
            .iter()
            .map(|item| (*item).to_string())
            .collect(),
        suggested_required_gates: vec![
            "rustc_smoke".to_string(),
            "existing_crc32_contract_tests".to_string(),
        ],
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
