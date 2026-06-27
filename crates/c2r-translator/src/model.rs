use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct BuildProfile {
    pub include_paths: Vec<String>,
    pub defines: Vec<String>,
    pub target_triple: Option<String>,
    pub abi: Option<String>,
    pub compiler_command_source: String,
    pub clang_available: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct SliceSpec {
    pub target_id: String,
    pub slice_id: String,
    pub source_commit: String,
    pub function_name: String,
    pub c_source: String,
    pub fixture_hash: String,
    #[serde(default)]
    pub source_root: Option<String>,
    #[serde(default)]
    pub source_file: Option<String>,
    #[serde(default)]
    pub source_files: Vec<SourceFileRef>,
    #[serde(default)]
    pub source_file_hashes: BTreeMap<String, String>,
    #[serde(default)]
    pub function_source_span: Option<SourceSpanRef>,
    #[serde(default)]
    pub compile_commands: Option<String>,
    pub build_profile: BuildProfile,
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
    pub byte_start: u64,
    pub byte_end: u64,
    pub sha256: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TranslationResult {
    pub rust_code: String,
    pub errors: Vec<TranslationError>,
    pub type_map: TypeMapEvidence,
    pub cfg: CfgEvidence,
    pub pointer_graph: PointerGraphEvidence,
    pub plan: TranslationPlan,
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
