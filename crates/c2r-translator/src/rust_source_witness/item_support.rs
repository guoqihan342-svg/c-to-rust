use quote::ToTokens;
use syn::{Item, Visibility};

use super::collector::Collector;
use super::sha256_text;
use super::syntax_scan::scan_item;

impl Collector {
    pub(super) fn collect_module(
        &mut self,
        parent_id: &str,
        parent_path: &str,
        item: &Item,
        value: &syn::ItemMod,
        depth: usize,
    ) {
        let name = value.ident.to_string();
        let path = child_path(parent_path, &name);
        let kind = if value.content.is_some() {
            "inline"
        } else {
            "external"
        };
        let Some(item_id) =
            self.add_item(parent_id, path.clone(), Some(name), "module", &value.vis)
        else {
            return;
        };
        self.record_scan(&item_id, scan_item(item));
        let Some(module_id) = self.add_module(parent_id, path.clone(), kind) else {
            return;
        };
        match &value.content {
            Some((_, items)) => self.collect_items(&module_id, &path, items, depth + 1),
            None => self.add_blocker(
                "rust_source_external_module_unresolved",
                Some(&item_id),
                None,
            ),
        }
    }

    pub(super) fn collect_simple(
        &mut self,
        module_id: &str,
        module_path: &str,
        item: &Item,
        kind: &'static str,
        name: Option<String>,
        visibility: &Visibility,
    ) {
        let suffix = name.clone().unwrap_or_else(|| {
            format!(
                "{kind}@{}",
                &sha256_text(&item.to_token_stream().to_string())[..16]
            )
        });
        if let Some(id) = self.add_item(
            module_id,
            child_path(module_path, &suffix),
            name,
            kind,
            visibility,
        ) {
            self.record_scan(&id, scan_item(item));
        }
    }
}

pub(super) fn child_path(parent: &str, child: &str) -> String {
    format!("{parent}::{child}")
}
