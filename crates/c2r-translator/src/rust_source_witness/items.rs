use quote::ToTokens;
use syn::{File, Item, Visibility};

use super::collector::{token_syntax, Collector, MAX_MODULE_DEPTH};
use super::item_support::child_path;
use super::sha256_text;
use super::syntax_scan::{scan_file_attributes, scan_item};

impl Collector {
    pub fn collect_file(&mut self, file: &File) {
        self.record_scan("crate-root", scan_file_attributes(&file.attrs));
        self.collect_items("module-000000", "crate", &file.items, 0);
        if self.items.is_empty() {
            self.add_blocker("rust_source_no_items", None, None);
        }
    }

    pub(super) fn collect_items(
        &mut self,
        module_id: &str,
        module_path: &str,
        items: &[Item],
        depth: usize,
    ) {
        if depth > MAX_MODULE_DEPTH {
            self.add_blocker("rust_source_module_depth_exceeded", None, None);
            return;
        }
        for item in items {
            self.collect_item(module_id, module_path, item, depth);
        }
    }

    fn collect_item(&mut self, module_id: &str, module_path: &str, item: &Item, depth: usize) {
        match item {
            Item::Fn(value) => {
                let name = value.sig.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "function",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    self.record_signature(&id, "function", &value.sig, None);
                }
            }
            Item::Struct(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "struct",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    let mut declaration = value.clone();
                    declaration.attrs.clear();
                    self.record_type(
                        &id,
                        "struct",
                        token_syntax(&declaration),
                        value.fields.iter().count(),
                        0,
                    );
                }
            }
            Item::Enum(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "enum",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    let mut declaration = value.clone();
                    declaration.attrs.clear();
                    let fields = value
                        .variants
                        .iter()
                        .map(|variant| variant.fields.iter().count())
                        .sum();
                    self.record_type(
                        &id,
                        "enum",
                        token_syntax(&declaration),
                        fields,
                        value.variants.len(),
                    );
                }
            }
            Item::Union(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "union",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    let mut declaration = value.clone();
                    declaration.attrs.clear();
                    self.record_type(
                        &id,
                        "union",
                        token_syntax(&declaration),
                        value.fields.named.len(),
                        0,
                    );
                }
            }
            Item::Type(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "type-alias",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    let mut declaration = value.clone();
                    declaration.attrs.clear();
                    self.record_type(&id, "type-alias", token_syntax(&declaration), 0, 0);
                }
            }
            Item::Trait(value) => {
                let name = value.ident.to_string();
                let path = child_path(module_path, &name);
                if let Some(id) =
                    self.add_item(module_id, path.clone(), Some(name), "trait", &value.vis)
                {
                    self.record_scan(&id, scan_item(item));
                    let mut declaration = value.clone();
                    declaration.attrs.clear();
                    declaration.items.clear();
                    self.record_type(&id, "trait", token_syntax(&declaration), 0, 0);
                    self.collect_trait_items(module_id, &path, &value.items);
                }
            }
            Item::TraitAlias(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "trait-alias",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    let mut declaration = value.clone();
                    declaration.attrs.clear();
                    self.record_type(&id, "trait-alias", token_syntax(&declaration), 0, 0);
                }
            }
            Item::Const(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "const",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    self.record_global(&id, "const", &value.ty, false, Some(value.expr.as_ref()));
                }
            }
            Item::Static(value) => {
                let name = value.ident.to_string();
                if let Some(id) = self.add_item(
                    module_id,
                    child_path(module_path, &name),
                    Some(name),
                    "static",
                    &value.vis,
                ) {
                    self.record_scan(&id, scan_item(item));
                    self.record_global(
                        &id,
                        "static",
                        &value.ty,
                        !matches!(value.mutability, syn::StaticMutability::None),
                        Some(&value.expr),
                    );
                }
            }
            Item::Mod(value) => self.collect_module(module_id, module_path, item, value, depth),
            Item::Impl(value) => {
                let identity = impl_identity(value);
                let path = child_path(module_path, &format!("impl@{identity}"));
                if let Some(id) = self.add_item(
                    module_id,
                    path.clone(),
                    None,
                    "impl",
                    &Visibility::Inherited,
                ) {
                    self.record_scan(&id, scan_item(item));
                    if is_drop_impl(value) {
                        self.record_initialization(
                            &id,
                            "drop-impl",
                            Some(value.to_token_stream().to_string()),
                        );
                    }
                    self.collect_impl_items(module_id, &path, &value.items);
                }
            }
            Item::ForeignMod(value) => {
                let identity = &sha256_text(&token_syntax(&value.abi))[..16];
                let path = child_path(module_path, &format!("extern@{identity}"));
                if let Some(id) = self.add_item(
                    module_id,
                    path.clone(),
                    None,
                    "foreign-module",
                    &Visibility::Inherited,
                ) {
                    self.record_scan(&id, scan_item(item));
                    self.collect_foreign_items(module_id, &path, &value.abi, &value.items);
                }
            }
            Item::Use(value) => {
                self.collect_simple(module_id, module_path, item, "use", None, &value.vis)
            }
            Item::ExternCrate(value) => self.collect_simple(
                module_id,
                module_path,
                item,
                "extern-crate",
                Some(value.ident.to_string()),
                &value.vis,
            ),
            Item::Macro(value) => self.collect_simple(
                module_id,
                module_path,
                item,
                "macro",
                value.ident.as_ref().map(ToString::to_string),
                &Visibility::Inherited,
            ),
            Item::Verbatim(value) => {
                let detail = sha256_text(&value.to_string());
                self.add_blocker("rust_source_parse_ambiguity", None, Some(detail));
            }
            _ => self.add_blocker("rust_source_unsupported_item", None, None),
        }
    }
}

fn impl_identity(value: &syn::ItemImpl) -> String {
    let trait_path = value
        .trait_
        .as_ref()
        .map(|(_, path, _)| token_syntax(path))
        .unwrap_or_else(|| "inherent".to_string());
    let identity = format!("{trait_path}|{}", token_syntax(&value.self_ty));
    sha256_text(&identity)[..16].to_string()
}

fn is_drop_impl(value: &syn::ItemImpl) -> bool {
    value
        .trait_
        .as_ref()
        .and_then(|(_, path, _)| path.segments.last())
        .is_some_and(|segment| segment.ident == "Drop")
}
