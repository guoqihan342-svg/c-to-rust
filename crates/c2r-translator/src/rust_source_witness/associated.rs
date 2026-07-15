use quote::ToTokens;
use syn::{Abi, ForeignItem, ImplItem, TraitItem, Visibility};

use super::collector::{token_syntax, Collector};
use super::item_support::child_path;
use super::sha256_text;
use super::syntax_scan::{scan_foreign_item, scan_impl_item, scan_trait_item};

impl Collector {
    pub(super) fn collect_trait_items(
        &mut self,
        module_id: &str,
        owner_path: &str,
        items: &[TraitItem],
    ) {
        for item in items {
            match item {
                TraitItem::Fn(value) => {
                    let name = value.sig.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "trait-function",
                        &Visibility::Inherited,
                    ) {
                        self.record_scan(&id, scan_trait_item(item));
                        self.record_signature(&id, "trait-function", &value.sig, None);
                    }
                }
                TraitItem::Const(value) => {
                    let name = value.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "trait-const",
                        &Visibility::Inherited,
                    ) {
                        self.record_scan(&id, scan_trait_item(item));
                        let initializer = value.default.as_ref().map(|(_, expr)| expr);
                        self.record_global(&id, "associated-const", &value.ty, false, initializer);
                    }
                }
                TraitItem::Type(value) => {
                    let name = value.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "trait-type",
                        &Visibility::Inherited,
                    ) {
                        self.record_scan(&id, scan_trait_item(item));
                        let mut declaration = value.clone();
                        declaration.attrs.clear();
                        self.record_type(&id, "associated-type", token_syntax(&declaration), 0, 0);
                    }
                }
                TraitItem::Macro(_) => {
                    self.collect_trait_other(module_id, owner_path, item, "trait-macro")
                }
                TraitItem::Verbatim(value) => self.add_blocker(
                    "rust_source_parse_ambiguity",
                    None,
                    Some(sha256_text(&value.to_string())),
                ),
                _ => self.add_blocker("rust_source_unsupported_trait_item", None, None),
            }
        }
    }

    pub(super) fn collect_impl_items(
        &mut self,
        module_id: &str,
        owner_path: &str,
        items: &[ImplItem],
    ) {
        for item in items {
            match item {
                ImplItem::Fn(value) => {
                    let name = value.sig.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "impl-function",
                        &value.vis,
                    ) {
                        self.record_scan(&id, scan_impl_item(item));
                        self.record_signature(&id, "impl-function", &value.sig, None);
                    }
                }
                ImplItem::Const(value) => {
                    let name = value.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "impl-const",
                        &value.vis,
                    ) {
                        self.record_scan(&id, scan_impl_item(item));
                        self.record_global(
                            &id,
                            "associated-const",
                            &value.ty,
                            false,
                            Some(&value.expr),
                        );
                    }
                }
                ImplItem::Type(value) => {
                    let name = value.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "impl-type",
                        &value.vis,
                    ) {
                        self.record_scan(&id, scan_impl_item(item));
                        let mut declaration = value.clone();
                        declaration.attrs.clear();
                        self.record_type(&id, "associated-type", token_syntax(&declaration), 0, 0);
                    }
                }
                ImplItem::Macro(_) => {
                    self.collect_impl_other(module_id, owner_path, item, "impl-macro")
                }
                ImplItem::Verbatim(value) => self.add_blocker(
                    "rust_source_parse_ambiguity",
                    None,
                    Some(sha256_text(&value.to_string())),
                ),
                _ => self.add_blocker("rust_source_unsupported_impl_item", None, None),
            }
        }
    }

    pub(super) fn collect_foreign_items(
        &mut self,
        module_id: &str,
        owner_path: &str,
        abi: &Abi,
        items: &[ForeignItem],
    ) {
        for item in items {
            match item {
                ForeignItem::Fn(value) => {
                    let name = value.sig.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "foreign-function",
                        &value.vis,
                    ) {
                        self.record_scan(&id, scan_foreign_item(item));
                        self.record_signature(&id, "foreign-function", &value.sig, Some(abi));
                    }
                }
                ForeignItem::Static(value) => {
                    let name = value.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "foreign-static",
                        &value.vis,
                    ) {
                        self.record_scan(&id, scan_foreign_item(item));
                        self.record_global(
                            &id,
                            "foreign-static",
                            &value.ty,
                            !matches!(value.mutability, syn::StaticMutability::None),
                            None,
                        );
                    }
                }
                ForeignItem::Type(value) => {
                    let name = value.ident.to_string();
                    if let Some(id) = self.add_item(
                        module_id,
                        child_path(owner_path, &name),
                        Some(name),
                        "foreign-type",
                        &value.vis,
                    ) {
                        self.record_scan(&id, scan_foreign_item(item));
                        let mut declaration = value.clone();
                        declaration.attrs.clear();
                        self.record_type(&id, "foreign-type", token_syntax(&declaration), 0, 0);
                    }
                }
                ForeignItem::Macro(_) => {
                    self.collect_foreign_other(module_id, owner_path, item, "foreign-macro")
                }
                ForeignItem::Verbatim(value) => self.add_blocker(
                    "rust_source_parse_ambiguity",
                    None,
                    Some(sha256_text(&value.to_string())),
                ),
                _ => self.add_blocker("rust_source_unsupported_foreign_item", None, None),
            }
        }
    }

    fn collect_trait_other(
        &mut self,
        module_id: &str,
        owner_path: &str,
        item: &TraitItem,
        kind: &'static str,
    ) {
        let syntax = item.to_token_stream().to_string();
        let suffix = format!("{kind}@{}", &sha256_text(&syntax)[..16]);
        if let Some(id) = self.add_item(
            module_id,
            child_path(owner_path, &suffix),
            None,
            kind,
            &Visibility::Inherited,
        ) {
            self.record_scan(&id, scan_trait_item(item));
        }
    }

    fn collect_impl_other(
        &mut self,
        module_id: &str,
        owner_path: &str,
        item: &ImplItem,
        kind: &'static str,
    ) {
        let syntax = item.to_token_stream().to_string();
        let suffix = format!("{kind}@{}", &sha256_text(&syntax)[..16]);
        if let Some(id) = self.add_item(
            module_id,
            child_path(owner_path, &suffix),
            None,
            kind,
            &Visibility::Inherited,
        ) {
            self.record_scan(&id, scan_impl_item(item));
        }
    }

    fn collect_foreign_other(
        &mut self,
        module_id: &str,
        owner_path: &str,
        item: &ForeignItem,
        kind: &'static str,
    ) {
        let syntax = item.to_token_stream().to_string();
        let suffix = format!("{kind}@{}", &sha256_text(&syntax)[..16]);
        if let Some(id) = self.add_item(
            module_id,
            child_path(owner_path, &suffix),
            None,
            kind,
            &Visibility::Inherited,
        ) {
            self.record_scan(&id, scan_foreign_item(item));
        }
    }
}
