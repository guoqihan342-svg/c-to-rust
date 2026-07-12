use std::collections::BTreeMap;
use std::ops::Deref;

use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct BuildProfile {
    pub include_paths: Vec<String>,
    pub defines: Vec<String>,
    #[serde(default)]
    pub target: Option<TargetAbiProfile>,
    #[serde(default)]
    pub clang_ast_fixture: Option<String>,
    pub target_triple: Option<String>,
    pub abi: Option<String>,
    pub compiler_command_source: String,
    pub clang_available: bool,
}

impl BuildProfile {
    pub fn resolved_target_abi(&self) -> Option<TargetAbiProfile> {
        if let Some(target) = &self.target {
            let inferred = known_target_abi_profile(
                self.target_triple
                    .as_deref()
                    .or_else(|| non_empty_str(&target.triple_or_abi)),
                self.abi
                    .as_deref()
                    .or_else(|| non_empty_str(&target.triple_or_abi)),
            );
            return Some(match inferred {
                Some(inferred) => merge_target_abi_profile(target, &inferred),
                None => target.clone(),
            });
        }
        known_target_abi_profile(self.target_triple.as_deref(), self.abi.as_deref())
    }
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct TargetAbiProfile {
    pub triple_or_abi: String,
    #[serde(default)]
    pub endianness: Option<String>,
    pub int_width: u16,
    #[serde(default)]
    pub int_align: u16,
    #[serde(default)]
    pub char_width: u16,
    #[serde(default)]
    pub char_align: u16,
    #[serde(default)]
    pub plain_char_signed: Option<bool>,
    #[serde(default)]
    pub short_width: u16,
    #[serde(default)]
    pub short_align: u16,
    pub long_width: u16,
    #[serde(default)]
    pub long_align: u16,
    #[serde(default)]
    pub long_long_width: u16,
    #[serde(default)]
    pub long_long_align: u16,
    pub pointer_width: u16,
    #[serde(default)]
    pub pointer_align: u16,
}

fn known_target_abi_profile(
    target_triple: Option<&str>,
    abi: Option<&str>,
) -> Option<TargetAbiProfile> {
    let target_id = target_triple
        .or(abi)
        .map(str::trim)
        .filter(|value| !value.is_empty())?;
    let triple = target_triple.unwrap_or_default().to_ascii_lowercase();
    let abi = abi.unwrap_or_default().to_ascii_lowercase();

    if triple.contains("x86_64") && triple.contains("windows") && triple.contains("msvc") {
        return Some(inferred_target_abi_profile(target_id, 32, true));
    }
    if triple.contains("x86_64")
        && (triple.contains("linux")
            || triple.contains("darwin")
            || triple.contains("freebsd")
            || triple.contains("unknown-none"))
        && !abi.contains("msvc")
    {
        return Some(inferred_target_abi_profile(target_id, 64, true));
    }
    if triple.contains("aarch64")
        && (triple.contains("linux") || triple.contains("darwin") || triple.contains("windows"))
    {
        return Some(inferred_target_abi_profile(target_id, 64, true));
    }

    None
}

fn non_empty_str(value: &str) -> Option<&str> {
    let value = value.trim();
    (!value.is_empty()).then_some(value)
}

fn merge_target_abi_profile(
    explicit: &TargetAbiProfile,
    inferred: &TargetAbiProfile,
) -> TargetAbiProfile {
    let mut merged = explicit.clone();
    if merged.triple_or_abi.trim().is_empty() {
        merged.triple_or_abi = inferred.triple_or_abi.clone();
    }
    if merged.endianness.is_none() {
        merged.endianness = inferred.endianness.clone();
    }
    if merged.int_width == 0 {
        merged.int_width = inferred.int_width;
    }
    if merged.int_align == 0 {
        merged.int_align = inferred.int_align;
    }
    if merged.char_width == 0 {
        merged.char_width = inferred.char_width;
    }
    if merged.char_align == 0 {
        merged.char_align = inferred.char_align;
    }
    if merged.plain_char_signed.is_none() {
        merged.plain_char_signed = inferred.plain_char_signed;
    }
    if merged.short_width == 0 {
        merged.short_width = inferred.short_width;
    }
    if merged.short_align == 0 {
        merged.short_align = inferred.short_align;
    }
    if merged.long_width == 0 {
        merged.long_width = inferred.long_width;
    }
    if merged.long_align == 0 {
        merged.long_align = inferred.long_align;
    }
    if merged.long_long_width == 0 {
        merged.long_long_width = inferred.long_long_width;
    }
    if merged.long_long_align == 0 {
        merged.long_long_align = inferred.long_long_align;
    }
    if merged.pointer_width == 0 {
        merged.pointer_width = inferred.pointer_width;
    }
    if merged.pointer_align == 0 {
        merged.pointer_align = inferred.pointer_align;
    }
    merged
}

fn inferred_target_abi_profile(
    triple_or_abi: &str,
    long_width: u16,
    plain_char_signed: bool,
) -> TargetAbiProfile {
    TargetAbiProfile {
        triple_or_abi: triple_or_abi.to_string(),
        endianness: Some("little".to_string()),
        int_width: 32,
        int_align: 32,
        char_width: 8,
        char_align: 8,
        plain_char_signed: Some(plain_char_signed),
        short_width: 16,
        short_align: 16,
        long_width,
        long_align: long_width,
        long_long_width: 64,
        long_long_align: 64,
        pointer_width: 64,
        pointer_align: 64,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolved_target_abi_fills_missing_char_fields_from_known_explicit_target() {
        let profile = BuildProfile {
            target: Some(TargetAbiProfile {
                triple_or_abi: "x86_64-unknown-linux-gnu".to_string(),
                endianness: Some("big".to_string()),
                int_width: 32,
                long_width: 64,
                pointer_width: 64,
                ..TargetAbiProfile::default()
            }),
            ..BuildProfile::default()
        };

        let abi = profile
            .resolved_target_abi()
            .expect("known explicit target");

        assert_eq!(abi.triple_or_abi, "x86_64-unknown-linux-gnu");
        assert_eq!(abi.endianness.as_deref(), Some("big"));
        assert_eq!(abi.int_width, 32);
        assert_eq!(abi.long_width, 64);
        assert_eq!(abi.pointer_width, 64);
        assert_eq!(abi.char_width, 8);
        assert_eq!(abi.char_align, 8);
        assert_eq!(abi.plain_char_signed, Some(true));
    }
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub translation_carrier: Option<JsonValue>,
    #[serde(default)]
    pub compile_commands: Option<CompileDatabaseRef>,
    #[serde(default)]
    pub c_boundary: CBoundary,
    pub build_profile: BuildProfile,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(untagged)]
pub enum CompileDatabaseRef {
    HashBound { path: String, sha256: String },
    LegacyPath(String),
}

impl CompileDatabaseRef {
    pub fn path(&self) -> &str {
        match self {
            Self::HashBound { path, .. } => path,
            Self::LegacyPath(path) => path,
        }
    }

    pub fn sha256(&self) -> Option<&str> {
        match self {
            Self::HashBound { sha256, .. } => Some(sha256),
            Self::LegacyPath(_) => None,
        }
    }
}

impl Deref for CompileDatabaseRef {
    type Target = str;

    fn deref(&self) -> &Self::Target {
        self.path()
    }
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct CBoundary {
    #[serde(default)]
    pub scalar_arithmetic_contract: ScalarArithmeticContract,
    #[serde(default)]
    pub pointer_contract: PointerContract,
    #[serde(default)]
    pub signatures: Vec<CSignature>,
    #[serde(default)]
    pub direct_dependencies: Vec<CDirectDependency>,
    #[serde(default)]
    pub external_direct_callees: Vec<ExternalDirectCallee>,
}

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
