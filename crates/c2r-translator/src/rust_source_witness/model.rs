use serde::Serialize;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RustSourceWitness {
    pub schema_version: u32,
    pub artifact_kind: &'static str,
    pub status: &'static str,
    pub parser: ParserIdentity,
    pub source: SourceIdentity,
    pub modules: Vec<ModuleFact>,
    pub items: Vec<ItemFact>,
    pub signatures: Vec<SignatureFact>,
    pub types: Vec<TypeFact>,
    pub globals: Vec<GlobalFact>,
    pub initialization: Vec<InitializationFact>,
    pub attributes: Vec<AttributeFact>,
    pub macro_invocations: Vec<MacroFact>,
    pub blockers: Vec<Blocker>,
    pub claim_boundary: ClaimBoundary,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ParserIdentity {
    pub implementation: &'static str,
    pub version: &'static str,
    pub quote_version: &'static str,
    pub protocol_version: u32,
    pub crate_version: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SourceIdentity {
    pub sha256: String,
    pub size_bytes: u64,
    pub encoding: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ClaimBoundary {
    pub phase: &'static str,
    pub candidate_only: bool,
    pub post_cfg: bool,
    pub section_closure: bool,
    pub semantic_gate: bool,
    pub translation_coverage_numerator: u32,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ModuleFact {
    pub module_id: String,
    pub parent_module_id: Option<String>,
    pub module_path: String,
    pub kind: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ItemFact {
    pub item_id: String,
    pub module_id: String,
    pub item_path: String,
    pub name: Option<String>,
    pub kind: &'static str,
    pub visibility: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SignatureFact {
    pub item_id: String,
    pub kind: &'static str,
    pub syntax: String,
    pub syntax_sha256: String,
    pub syntax_size_bytes: u64,
    pub abi: Option<String>,
    pub is_unsafe: bool,
    pub is_async: bool,
    pub is_const: bool,
    pub is_variadic: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct TypeFact {
    pub item_id: String,
    pub kind: &'static str,
    pub syntax: String,
    pub syntax_sha256: String,
    pub syntax_size_bytes: u64,
    pub field_count: u64,
    pub variant_count: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GlobalFact {
    pub item_id: String,
    pub kind: &'static str,
    pub type_syntax: String,
    pub type_sha256: String,
    pub type_size_bytes: u64,
    pub mutable: bool,
    pub has_initializer: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct InitializationFact {
    pub item_id: String,
    pub kind: &'static str,
    pub expression_sha256: Option<String>,
    pub expression_size_bytes: Option<u64>,
    pub order: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct AttributeFact {
    pub fact_id: String,
    pub item_id: String,
    pub path: String,
    pub kind: &'static str,
    pub syntax: String,
    pub syntax_sha256: String,
    pub syntax_size_bytes: u64,
    pub supported_pre_cfg: bool,
    pub requires_expansion: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct MacroFact {
    pub fact_id: String,
    pub item_id: String,
    pub path: String,
    pub syntax_sha256: String,
    pub syntax_size_bytes: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
pub struct Blocker {
    pub code: &'static str,
    pub item_id: Option<String>,
    pub detail_sha256: Option<String>,
}
