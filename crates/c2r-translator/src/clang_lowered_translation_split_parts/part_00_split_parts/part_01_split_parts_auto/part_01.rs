
fn collect_complete_struct_names(source: &str) -> BTreeSet<String> {
    let searchable_source = c_source_without_strings_and_comments(source);
    let bytes = searchable_source.as_bytes();
    let mut names = BTreeSet::new();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_c_ident_start(bytes[index]) {
            index += 1;
            continue;
        }
        let keyword_start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        if &searchable_source[keyword_start..index] != "struct" {
            continue;
        }

        while index < bytes.len() && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        if index >= bytes.len() || !is_c_ident_start(bytes[index]) {
            continue;
        }
        let name_start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        let name = &searchable_source[name_start..index];
        while index < bytes.len() && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        if index < bytes.len() && bytes[index] == b'{' {
            names.insert(name.to_string());
        }
    }
    names
}

fn collect_struct_names_from_type(c_type: &str, names: &mut BTreeSet<String>) {
    let tokens = c_identifier_tokens(c_type);
    for window in tokens.windows(2) {
        if window[0] == "struct" && !is_builtin_type_token(&window[1]) {
            names.insert(window[1].clone());
        }
    }
}

fn collect_typedef_alias_from_type(
    c_type: &str,
    return_position: bool,
    aliases: &mut BTreeMap<String, &'static str>,
) {
    let mut previous_was_struct = false;
    for token in c_identifier_tokens(c_type) {
        if previous_was_struct {
            previous_was_struct = false;
            continue;
        }
        if token == "struct" {
            previous_was_struct = true;
            continue;
        }
        if is_builtin_type_token(&token) {
            continue;
        }
        let kind = if token.ends_with("_err_t") || (return_position && !token.ends_with("_t")) {
            "int"
        } else {
            "void_ptr"
        };
        aliases.entry(token).or_insert(kind);
    }
}

fn record_name_for_typedef_alias<'a>(
    alias: &str,
    structs: &'a BTreeSet<String>,
) -> Option<&'a str> {
    let record = alias.strip_suffix("_t")?;
    structs.get(record).map(String::as_str)
}

fn collect_object_like_uppercase_identifiers(source: &str) -> BTreeSet<String> {
    let mut result = BTreeSet::new();
    let searchable_source = c_source_without_strings_and_comments(source);
    let bytes = searchable_source.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_c_ident_start(bytes[index]) {
            index += 1;
            continue;
        }
        let start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        let ident = &source[start..index];
        let mut lookahead = index;
        while lookahead < bytes.len() && bytes[lookahead].is_ascii_whitespace() {
            lookahead += 1;
        }
        if ident.chars().any(|ch| ch.is_ascii_lowercase())
            || !ident.chars().any(|ch| ch.is_ascii_uppercase())
            || is_reserved_object_like_identifier(ident)
            || (lookahead < bytes.len() && bytes[lookahead] == b'(')
        {
            continue;
        }
        result.insert(ident.to_string());
    }
    result
}

fn c_source_without_strings_and_comments(source: &str) -> String {
    let mut result = String::with_capacity(source.len());
    let bytes = source.as_bytes();
    let mut index = 0usize;
    while index < bytes.len() {
        if bytes[index] == b'"' || bytes[index] == b'\'' {
            let quote = bytes[index];
            push_identifier_scan_blank(&mut result, bytes[index]);
            index += 1;
            while index < bytes.len() {
                let byte = bytes[index];
                if byte == b'\\' {
                    push_identifier_scan_blank(&mut result, byte);
                    index += 1;
                    if index < bytes.len() {
                        push_identifier_scan_blank(&mut result, bytes[index]);
                        index += 1;
                    }
                    continue;
                }
                push_identifier_scan_blank(&mut result, byte);
                index += 1;
                if byte == quote {
                    break;
                }
            }
            continue;
        }
        if bytes[index] == b'/' && index + 1 < bytes.len() && bytes[index + 1] == b'/' {
            push_identifier_scan_blank(&mut result, bytes[index]);
            push_identifier_scan_blank(&mut result, bytes[index + 1]);
            index += 2;
            while index < bytes.len() {
                let byte = bytes[index];
                push_identifier_scan_blank(&mut result, byte);
                index += 1;
                if byte == b'\n' {
                    break;
                }
            }
            continue;
        }
        if bytes[index] == b'/' && index + 1 < bytes.len() && bytes[index + 1] == b'*' {
            push_identifier_scan_blank(&mut result, bytes[index]);
            push_identifier_scan_blank(&mut result, bytes[index + 1]);
            index += 2;
            while index < bytes.len() {
                let byte = bytes[index];
                if byte == b'*' && index + 1 < bytes.len() && bytes[index + 1] == b'/' {
                    push_identifier_scan_blank(&mut result, byte);
                    push_identifier_scan_blank(&mut result, bytes[index + 1]);
                    index += 2;
                    break;
                }
                push_identifier_scan_blank(&mut result, byte);
                index += 1;
            }
            continue;
        }
        if bytes[index].is_ascii() {
            result.push(bytes[index] as char);
        } else {
            result.push(' ');
        }
        index += 1;
    }
    result
}

fn push_identifier_scan_blank(result: &mut String, byte: u8) {
    if byte == b'\n' {
        result.push('\n');
    } else {
        result.push(' ');
    }
}

fn is_reserved_object_like_identifier(ident: &str) -> bool {
    matches!(ident, "NULL")
}

fn c_identifier_tokens(text: &str) -> Vec<String> {
    text.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
        .filter(|token| !token.is_empty())
        .map(str::to_string)
        .collect()
}

fn is_builtin_type_token(token: &str) -> bool {
    matches!(
        token,
        "void"
            | "char"
            | "signed"
            | "unsigned"
            | "short"
            | "int"
            | "long"
            | "float"
            | "double"
            | "const"
            | "volatile"
            | "restrict"
            | "bool"
            | "_Bool"
            | "size_t"
            | "int8_t"
            | "uint8_t"
            | "int16_t"
            | "uint16_t"
            | "int32_t"
            | "uint32_t"
            | "int64_t"
            | "uint64_t"
    )
}

fn is_c_ident_start(byte: u8) -> bool {
    byte == b'_' || byte.is_ascii_alphabetic()
}

fn is_c_ident_continue(byte: u8) -> bool {
    byte == b'_' || byte.is_ascii_alphanumeric()
}

fn is_c_identifier(value: &str) -> bool {
    let mut bytes = value.bytes();
    let Some(first) = bytes.next() else {
        return false;
    };
    is_c_ident_start(first) && bytes.all(is_c_ident_continue)
}
