
#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ExternalDirectCallee {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub signature_ref: String,
    #[serde(default)]
    pub source_ref: String,
    #[serde(default)]
    pub accepted_named_slice_evidence: Option<AcceptedNamedSliceEvidence>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, JsonValue>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct AcceptedNamedSliceEvidence {
    #[serde(default)]
    pub target_id: String,
    #[serde(default)]
    pub slice_id: String,
    #[serde(default)]
    pub final_verification: String,
    #[serde(default)]
    pub boundary: String,
    #[serde(flatten)]
    pub extra: BTreeMap<String, JsonValue>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct CSignature {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub function: String,
    #[serde(default)]
    pub return_type: String,
    #[serde(default)]
    pub parameters: Vec<CParameter>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct CParameter {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub c_type: String,
    #[serde(default)]
    pub direction: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct CDirectDependency {
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub source_span: Option<SourceSpanRef>,
    #[serde(default)]
    pub value: Option<JsonValue>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ScalarArithmeticContract {
    #[serde(default)]
    pub signed_right_shift: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerContract {
    #[serde(default)]
    pub input_buffers: Vec<PointerContractNode>,
    #[serde(default)]
    pub output_pointers: Vec<PointerContractNode>,
    #[serde(default)]
    pub noalias_required: Vec<Vec<String>>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerContractNode {
    #[serde(default)]
    pub name: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SourceFileRef {
    pub path: String,
    pub role: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SourceSpanRef {
    pub file: String,
    pub line_start: u64,
    pub line_end: u64,
    #[serde(default)]
    pub byte_start: u64,
    #[serde(default)]
    pub byte_end: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationResult {
    pub rust_code: String,
    pub errors: Vec<TranslationError>,
    #[serde(default)]
    pub translation_source: TranslationSource,
    pub type_map: TypeMapEvidence,
    pub cfg: CfgEvidence,
    pub pointer_graph: PointerGraphEvidence,
    pub plan: TranslationPlan,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationSource {
    pub selected: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_from: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fallback_reason: Option<String>,
}

impl Default for TranslationSource {
    fn default() -> Self {
        Self {
            selected: "unknown".to_string(),
            fallback_from: None,
            fallback_reason: None,
        }
    }
}

impl TranslationSource {
    pub fn selected(selected: impl Into<String>) -> Self {
        Self {
            selected: selected.into(),
            ..Self::default()
        }
    }

    pub fn fallback(
        selected: impl Into<String>,
        fallback_from: impl Into<String>,
        fallback_reason: impl Into<String>,
    ) -> Self {
        Self {
            selected: selected.into(),
            fallback_from: Some(fallback_from.into()),
            fallback_reason: Some(fallback_reason.into()),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationError {
    pub kind: String,
    pub message: String,
    pub source_span: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TypeMapEvidence {
    pub mappings: Vec<TypeMapping>,
    pub uncertainties: Vec<TypeUncertainty>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TypeMapping {
    pub c_type: String,
    pub rust_type: String,
    pub symbol: String,
    pub reason: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct TypeUncertainty {
    pub symbol: String,
    pub c_type: String,
    pub reason: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct CfgEvidence {
    pub functions: Vec<CfgFunction>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CfgFunction {
    pub name: String,
    pub blocks: Vec<CfgBlock>,
    pub unsupported_control_flow: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub structured_control_flow: Option<StructuredControlFlowEvidence>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct StructuredControlFlowEvidence {
    pub if_count: usize,
    pub loop_count: usize,
    pub has_goto: bool,
    pub has_switch: bool,
    pub relooper_required: bool,
    pub recovery_status: String,
    #[serde(default)]
    pub relooper_preconditions: Vec<String>,
    #[serde(default)]
    pub relooper_refusals: Vec<String>,
    pub scope_note: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CfgBlock {
    pub id: String,
    pub statements: Vec<String>,
    pub statement_kinds: Vec<String>,
    #[serde(default)]
    pub lvalue_kinds: Vec<String>,
    pub terminator: String,
    pub edges: Vec<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerGraphEvidence {
    pub nodes: Vec<PointerNode>,
    pub edges: Vec<PointerEdge>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerNode {
    pub id: String,
    pub c_type: String,
    pub role: String,
    pub rust_boundary: String,
    pub read_effects: Vec<String>,
    pub write_effects: Vec<String>,
    #[serde(default)]
    pub boundary_decisions: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PointerEdge {
    pub from: String,
    pub to: String,
    pub relationship: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationPlan {
    pub target_id: String,
    pub slice_id: String,
    pub function_name: String,
    pub translation_rule_ids: Vec<String>,
    #[serde(default)]
    pub call_expressions: Vec<CallExpressionEvidence>,
    pub unsupported_node_count: usize,
    pub unsafe_candidate_count: usize,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct CallExpressionEvidence {
    pub callee: String,
    pub arguments: Vec<String>,
    pub source_expression: String,
    pub statement_context: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ArtifactManifest {
    pub target_id: String,
    pub slice_id: String,
    pub status: String,
    pub artifact_paths: Vec<String>,
}
