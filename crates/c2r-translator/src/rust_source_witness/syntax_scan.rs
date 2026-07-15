use quote::ToTokens;
use syn::visit::{self, Visit};
use syn::{Attribute, ForeignItem, ImplItem, Item, TraitItem};

use super::sha256_text;

#[derive(Debug)]
pub struct AttributeSnapshot {
    pub path: String,
    pub syntax: String,
}

#[derive(Debug)]
pub struct MacroSnapshot {
    pub path: String,
    pub syntax_sha256: String,
    pub syntax_size_bytes: u64,
}

#[derive(Default, Debug)]
pub struct ScanResult {
    pub attributes: Vec<AttributeSnapshot>,
    pub macros: Vec<MacroSnapshot>,
}

pub fn scan_file_attributes(attributes: &[Attribute]) -> ScanResult {
    let mut scanner = SyntaxScanner::default();
    for attribute in attributes {
        scanner.visit_attribute(attribute);
    }
    scanner.result
}

pub fn scan_item(item: &Item) -> ScanResult {
    let mut scanner = SyntaxScanner::default();
    match item {
        Item::Mod(value) => scanner.scan_attributes(&value.attrs),
        Item::Trait(value) => {
            scanner.scan_attributes(&value.attrs);
            scanner.visit_generics(&value.generics);
            for bound in &value.supertraits {
                scanner.visit_type_param_bound(bound);
            }
        }
        Item::Impl(value) => {
            scanner.scan_attributes(&value.attrs);
            scanner.visit_generics(&value.generics);
            if let Some((_, path, _)) = &value.trait_ {
                scanner.visit_path(path);
            }
            scanner.visit_type(&value.self_ty);
        }
        Item::ForeignMod(value) => {
            scanner.scan_attributes(&value.attrs);
            scanner.visit_abi(&value.abi);
        }
        value => scanner.visit_item(value),
    }
    scanner.result
}

pub fn scan_trait_item(item: &TraitItem) -> ScanResult {
    let mut scanner = SyntaxScanner::default();
    scanner.visit_trait_item(item);
    scanner.result
}

pub fn scan_impl_item(item: &ImplItem) -> ScanResult {
    let mut scanner = SyntaxScanner::default();
    scanner.visit_impl_item(item);
    scanner.result
}

pub fn scan_foreign_item(item: &ForeignItem) -> ScanResult {
    let mut scanner = SyntaxScanner::default();
    scanner.visit_foreign_item(item);
    scanner.result
}

#[derive(Default)]
struct SyntaxScanner {
    result: ScanResult,
}

impl SyntaxScanner {
    fn scan_attributes(&mut self, attributes: &[Attribute]) {
        for attribute in attributes {
            self.visit_attribute(attribute);
        }
    }
}

impl<'ast> Visit<'ast> for SyntaxScanner {
    fn visit_attribute(&mut self, value: &'ast Attribute) {
        self.result.attributes.push(AttributeSnapshot {
            path: value.path().to_token_stream().to_string(),
            syntax: value.to_token_stream().to_string(),
        });
        visit::visit_attribute(self, value);
    }

    fn visit_macro(&mut self, value: &'ast syn::Macro) {
        let syntax = value.to_token_stream().to_string();
        self.result.macros.push(MacroSnapshot {
            path: value.path.to_token_stream().to_string(),
            syntax_sha256: sha256_text(&syntax),
            syntax_size_bytes: syntax.len() as u64,
        });
        visit::visit_macro(self, value);
    }
}
