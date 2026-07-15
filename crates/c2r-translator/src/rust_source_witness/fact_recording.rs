use quote::ToTokens;
use syn::{Expr, Type};

use super::collector::{token_syntax, Collector};
use super::model::{GlobalFact, InitializationFact, TypeFact};

impl Collector {
    pub(super) fn record_type(
        &mut self,
        item_id: &str,
        kind: &'static str,
        syntax: String,
        field_count: usize,
        variant_count: usize,
    ) {
        let Some((syntax, syntax_sha256, syntax_size_bytes)) = self.bounded_syntax(item_id, syntax)
        else {
            return;
        };
        if !self.allow_fact() {
            return;
        }
        self.types.push(TypeFact {
            item_id: item_id.to_string(),
            kind,
            syntax,
            syntax_sha256,
            syntax_size_bytes,
            field_count: field_count as u64,
            variant_count: variant_count as u64,
        });
    }

    pub(super) fn record_global(
        &mut self,
        item_id: &str,
        kind: &'static str,
        ty: &Type,
        mutable: bool,
        initializer: Option<&Expr>,
    ) {
        let syntax = token_syntax(ty);
        let Some((type_syntax, type_sha256, type_size_bytes)) =
            self.bounded_syntax(item_id, syntax)
        else {
            return;
        };
        if self.allow_fact() {
            self.globals.push(GlobalFact {
                item_id: item_id.to_string(),
                kind,
                type_syntax,
                type_sha256,
                type_size_bytes,
                mutable,
                has_initializer: initializer.is_some(),
            });
        }
        if let Some(expression) = initializer {
            self.record_initialization(
                item_id,
                match kind {
                    "static" | "foreign-static" => "static-initializer",
                    "const" | "associated-const" => "const-initializer",
                    _ => "global-initializer",
                },
                Some(expression.to_token_stream().to_string()),
            );
        }
    }

    pub(super) fn record_initialization(
        &mut self,
        item_id: &str,
        kind: &'static str,
        expression: Option<String>,
    ) {
        let projection = match expression {
            Some(value) => {
                let Some((_, digest, size)) = self.bounded_syntax(item_id, value) else {
                    return;
                };
                (Some(digest), Some(size))
            }
            None => (None, None),
        };
        if !self.allow_fact() {
            return;
        }
        self.initialization.push(InitializationFact {
            item_id: item_id.to_string(),
            kind,
            expression_sha256: projection.0,
            expression_size_bytes: projection.1,
            order: "unresolved-pre-cfg",
        });
    }
}
