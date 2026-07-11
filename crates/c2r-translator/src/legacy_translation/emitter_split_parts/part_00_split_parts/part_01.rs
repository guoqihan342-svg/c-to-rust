
#[derive(Default)]
struct RecordLayouts {
    records: Vec<RecordLayout>,
}

#[derive(Clone)]
struct RecordLayout {
    name: String,
    fields: Vec<RecordField>,
}

#[derive(Clone)]
struct RecordField {
    name: String,
    ty: RecordFieldType,
}

#[derive(Clone, Eq, PartialEq)]
enum RecordFieldType {
    Scalar(&'static str),
    Record(String),
}

impl RecordLayouts {
    fn record_path(&mut self, root_type: &str, fields: &[String]) {
        if fields.is_empty() {
            return;
        }
        let mut current_record = root_type.to_string();
        for (index, field) in fields.iter().enumerate() {
            let is_leaf = index + 1 == fields.len();
            if is_leaf {
                let ty = RecordFieldType::Scalar(infer_scalar_field_type(field));
                self.insert_field(&current_record, field, ty);
            } else {
                let nested_record = format!("{current_record}{}", pascal_case(field));
                self.insert_field(
                    &current_record,
                    field,
                    RecordFieldType::Record(nested_record.clone()),
                );
                current_record = nested_record;
            }
        }
    }

    fn insert_field(&mut self, record: &str, field: &str, ty: RecordFieldType) {
        let layout = self.ensure_record(record);
        if let Some(existing) = layout.fields.iter_mut().find(|item| item.name == field) {
            existing.ty = merge_field_type(&existing.ty, &ty);
            return;
        }
        layout.fields.push(RecordField {
            name: field.to_string(),
            ty,
        });
    }

    fn ensure_record(&mut self, name: &str) -> &mut RecordLayout {
        if let Some(index) = self.records.iter().position(|record| record.name == name) {
            return &mut self.records[index];
        }
        self.records.push(RecordLayout {
            name: name.to_string(),
            fields: Vec::new(),
        });
        self.records
            .last_mut()
            .expect("record was just inserted")
    }

    fn emit_definitions(&self) -> String {
        let mut emitted = String::new();
        let mut records = self.records.clone();
        records.sort_by_key(|record| record_depth(&record.name));
        records.reverse();
        for record in records {
            emitted.push_str("#[derive(Clone, Copy, Debug, Eq, PartialEq)]\n");
            emitted.push_str(&format!("pub struct {} {{\n", record.name));
            for field in record.fields {
                let ty = match field.ty {
                    RecordFieldType::Scalar(ty) => ty.to_string(),
                    RecordFieldType::Record(name) => name,
                };
                emitted.push_str(&format!("    pub {}: {},\n", field.name, ty));
            }
            emitted.push_str("}\n\n");
        }
        emitted
    }
}

fn merge_field_type(existing: &RecordFieldType, incoming: &RecordFieldType) -> RecordFieldType {
    if existing == incoming {
        existing.clone()
    } else if matches!(existing, RecordFieldType::Scalar("usize"))
        || matches!(incoming, RecordFieldType::Scalar("usize"))
    {
        RecordFieldType::Scalar("usize")
    } else {
        incoming.clone()
    }
}

fn record_depth(name: &str) -> usize {
    name.chars().filter(|ch| ch.is_ascii_uppercase()).count()
}

fn infer_scalar_field_type(field: &str) -> &'static str {
    if field.ends_with("len") || field.ends_with("size") {
        "usize"
    } else {
        "u32"
    }
}

fn rust_record_type_name(c_type: &str) -> String {
    let normalized = normalize_type(c_type)
        .trim_start_matches("const ")
        .trim_end_matches('*')
        .trim()
        .trim_start_matches("struct ")
        .trim_end_matches("_t")
        .to_string();
    pascal_case(&normalized)
}

fn record_type_name_from_var(name: &str) -> String {
    pascal_case(name)
}

fn pascal_case(value: &str) -> String {
    let mut out = String::new();
    let mut uppercase_next = true;
    for ch in value.chars() {
        if ch == '_' || ch == '-' || ch == ' ' {
            uppercase_next = true;
        } else if uppercase_next {
            out.extend(ch.to_uppercase());
            uppercase_next = false;
        } else {
            out.push(ch);
        }
    }
    out
}

fn emit_record_pointer_expr(expr: &str) -> String {
    if let Some(path) = parse_record_pointer_member_path(expr) {
        let mut out = path.root;
        for field in path.fields {
            out.push('.');
            out.push_str(&field);
        }
        out
    } else {
        translate_expr(expr)
    }
}
