use quote::ToTokens;
use syn::{Abi, Signature, Visibility};

use super::model::*;
use super::sha256_text;

pub const MAX_FACTS: usize = 20_000;
pub const MAX_BLOCKERS: usize = 4_096;
pub const MAX_MODULE_DEPTH: usize = 128;
pub const MAX_SYNTAX_BYTES: usize = 64 * 1024;

pub struct Collector {
    pub(super) modules: Vec<ModuleFact>,
    pub(super) items: Vec<ItemFact>,
    pub(super) signatures: Vec<SignatureFact>,
    pub(super) types: Vec<TypeFact>,
    pub(super) globals: Vec<GlobalFact>,
    pub(super) initialization: Vec<InitializationFact>,
    pub(super) attributes: Vec<AttributeFact>,
    pub(super) macro_invocations: Vec<MacroFact>,
    pub(super) blockers: Vec<Blocker>,
    next_item: usize,
    next_module: usize,
    next_fact: usize,
    limit_seen: bool,
}

impl Collector {
    pub fn new() -> Self {
        Self {
            modules: vec![ModuleFact {
                module_id: "module-000000".to_string(),
                parent_module_id: None,
                module_path: "crate".to_string(),
                kind: "root",
            }],
            items: Vec::new(),
            signatures: Vec::new(),
            types: Vec::new(),
            globals: Vec::new(),
            initialization: Vec::new(),
            attributes: Vec::new(),
            macro_invocations: Vec::new(),
            blockers: Vec::new(),
            next_item: 0,
            next_module: 1,
            next_fact: 0,
            limit_seen: false,
        }
    }

    pub fn into_parts(mut self) -> WitnessParts {
        self.blockers.sort();
        self.blockers.dedup();
        WitnessParts {
            modules: self.modules,
            items: self.items,
            signatures: self.signatures,
            types: self.types,
            globals: self.globals,
            initialization: self.initialization,
            attributes: self.attributes,
            macro_invocations: self.macro_invocations,
            blockers: self.blockers,
        }
    }

    pub(super) fn add_item(
        &mut self,
        module_id: &str,
        item_path: String,
        name: Option<String>,
        kind: &'static str,
        visibility: &Visibility,
    ) -> Option<String> {
        if !self.allow_fact() {
            return None;
        }
        let item_id = format!("item-{:06}", self.next_item);
        self.next_item += 1;
        self.items.push(ItemFact {
            item_id: item_id.clone(),
            module_id: module_id.to_string(),
            item_path,
            name,
            kind,
            visibility: visibility_syntax(visibility),
        });
        Some(item_id)
    }

    pub(super) fn add_module(
        &mut self,
        parent_module_id: &str,
        module_path: String,
        kind: &'static str,
    ) -> Option<String> {
        if !self.allow_fact() {
            return None;
        }
        let module_id = format!("module-{:06}", self.next_module);
        self.next_module += 1;
        self.modules.push(ModuleFact {
            module_id: module_id.clone(),
            parent_module_id: Some(parent_module_id.to_string()),
            module_path,
            kind,
        });
        Some(module_id)
    }

    pub(super) fn record_signature(
        &mut self,
        item_id: &str,
        kind: &'static str,
        signature: &Signature,
        inherited_abi: Option<&Abi>,
    ) {
        let syntax = signature.to_token_stream().to_string();
        let Some((syntax, syntax_sha256, syntax_size_bytes)) = self.bounded_syntax(item_id, syntax)
        else {
            return;
        };
        if !self.allow_fact() {
            return;
        }
        self.signatures.push(SignatureFact {
            item_id: item_id.to_string(),
            kind,
            syntax,
            syntax_sha256,
            syntax_size_bytes,
            abi: signature.abi.as_ref().or(inherited_abi).map(token_syntax),
            is_unsafe: signature.unsafety.is_some(),
            is_async: signature.asyncness.is_some(),
            is_const: signature.constness.is_some(),
            is_variadic: signature.variadic.is_some(),
        });
    }

    pub(super) fn add_blocker(
        &mut self,
        code: &'static str,
        item_id: Option<&str>,
        detail_sha256: Option<String>,
    ) {
        if self.blockers.len() >= MAX_BLOCKERS {
            self.limit_seen = true;
            return;
        }
        self.blockers.push(Blocker {
            code,
            item_id: item_id.map(str::to_string),
            detail_sha256,
        });
    }

    pub(super) fn bounded_syntax(
        &mut self,
        item_id: &str,
        syntax: String,
    ) -> Option<(String, String, u64)> {
        if syntax.len() > MAX_SYNTAX_BYTES {
            self.syntax_limit(item_id, &syntax);
            return None;
        }
        let digest = sha256_text(&syntax);
        let size = syntax.len() as u64;
        Some((syntax, digest, size))
    }

    pub(super) fn next_fact_id(&mut self, prefix: &str) -> String {
        let value = format!("{prefix}-{:06}", self.next_fact);
        self.next_fact += 1;
        value
    }

    pub(super) fn allow_fact(&mut self) -> bool {
        let count = self.modules.len()
            + self.items.len()
            + self.signatures.len()
            + self.types.len()
            + self.globals.len()
            + self.initialization.len()
            + self.attributes.len()
            + self.macro_invocations.len();
        if count < MAX_FACTS {
            true
        } else {
            if !self.limit_seen {
                self.limit_seen = true;
                self.add_blocker("rust_source_fact_limit_exceeded", None, None);
            }
            false
        }
    }

    pub(super) fn syntax_limit(&mut self, item_id: &str, syntax: &str) {
        self.add_blocker(
            "rust_source_syntax_limit_exceeded",
            Some(item_id),
            Some(sha256_text(syntax)),
        );
    }
}

pub struct WitnessParts {
    pub modules: Vec<ModuleFact>,
    pub items: Vec<ItemFact>,
    pub signatures: Vec<SignatureFact>,
    pub types: Vec<TypeFact>,
    pub globals: Vec<GlobalFact>,
    pub initialization: Vec<InitializationFact>,
    pub attributes: Vec<AttributeFact>,
    pub macro_invocations: Vec<MacroFact>,
    pub blockers: Vec<Blocker>,
}

pub(super) fn token_syntax<T: ToTokens>(value: &T) -> String {
    value.to_token_stream().to_string()
}

pub(super) fn visibility_syntax(value: &Visibility) -> String {
    match value {
        Visibility::Inherited => "inherited".to_string(),
        _ => token_syntax(value),
    }
}
