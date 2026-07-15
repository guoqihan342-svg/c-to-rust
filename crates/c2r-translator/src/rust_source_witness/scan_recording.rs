use super::collector::{Collector, MAX_SYNTAX_BYTES};
use super::model::{AttributeFact, MacroFact};
use super::sha256_text;
use super::syntax_scan::ScanResult;

impl Collector {
    pub(super) fn record_scan(&mut self, item_id: &str, scan: ScanResult) {
        for attribute in scan.attributes {
            let (kind, supported, expansion, blocker) = attribute_policy(&attribute.path);
            let detail = sha256_text(&attribute.syntax);
            if let Some(code) = blocker {
                self.add_blocker(code, Some(item_id), Some(detail.clone()));
            }
            if attribute.syntax.len() > MAX_SYNTAX_BYTES {
                self.syntax_limit(item_id, &attribute.syntax);
                continue;
            }
            if !self.allow_fact() {
                continue;
            }
            let fact_id = self.next_fact_id("attribute");
            self.attributes.push(AttributeFact {
                fact_id,
                item_id: item_id.to_string(),
                path: attribute.path,
                kind,
                syntax_size_bytes: attribute.syntax.len() as u64,
                syntax_sha256: detail,
                syntax: attribute.syntax,
                supported_pre_cfg: supported,
                requires_expansion: expansion,
            });
        }
        for invocation in scan.macros {
            self.add_blocker(
                "rust_source_macro_expansion_required",
                Some(item_id),
                Some(invocation.syntax_sha256.clone()),
            );
            if !self.allow_fact() {
                continue;
            }
            let fact_id = self.next_fact_id("macro");
            self.macro_invocations.push(MacroFact {
                fact_id,
                item_id: item_id.to_string(),
                path: invocation.path,
                syntax_sha256: invocation.syntax_sha256,
                syntax_size_bytes: invocation.syntax_size_bytes,
            });
        }
    }
}

fn attribute_policy(path: &str) -> (&'static str, bool, bool, Option<&'static str>) {
    if path == "cfg" {
        return ("cfg", true, false, None);
    }
    if path == "cfg_attr" {
        return (
            "cfg_attr",
            false,
            true,
            Some("rust_source_cfg_attr_unresolved"),
        );
    }
    if path == "derive" {
        return (
            "derive",
            false,
            true,
            Some("rust_source_macro_expansion_required"),
        );
    }
    if is_builtin_attribute(path) {
        return ("builtin", true, false, None);
    }
    (
        "unsupported",
        false,
        false,
        Some("rust_source_unsupported_attribute"),
    )
}

fn is_builtin_attribute(path: &str) -> bool {
    matches!(
        path,
        "allow"
            | "warn"
            | "deny"
            | "forbid"
            | "expect"
            | "doc"
            | "inline"
            | "cold"
            | "must_use"
            | "deprecated"
            | "non_exhaustive"
            | "repr"
            | "no_mangle"
            | "export_name"
            | "link_name"
            | "link_section"
            | "used"
            | "link"
            | "path"
            | "crate_name"
            | "crate_type"
            | "feature"
            | "test"
            | "ignore"
            | "should_panic"
            | "panic_handler"
            | "global_allocator"
            | "alloc_error_handler"
            | "target_feature"
            | "track_caller"
            | "naked"
            | "ffi_returns_twice"
            | "windows_subsystem"
            | "macro_export"
            | "macro_use"
            | "proc_macro"
            | "proc_macro_attribute"
            | "proc_macro_derive"
    )
}
