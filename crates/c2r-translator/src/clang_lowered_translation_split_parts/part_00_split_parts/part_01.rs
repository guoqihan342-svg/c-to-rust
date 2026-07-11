
fn slice_source_typedefs(spec: &SliceSpec) -> String {
    let mut aliases: BTreeMap<String, &'static str> = BTreeMap::new();
    let mut structs = collect_struct_names(&spec.c_source);
    for signature in &spec.c_boundary.signatures {
        collect_struct_names_from_type(&signature.return_type, &mut structs);
        for parameter in &signature.parameters {
            collect_struct_names_from_type(&parameter.c_type, &mut structs);
        }
    }
    for signature in &spec.c_boundary.signatures {
        collect_typedef_alias_from_type(&signature.return_type, true, &mut aliases);
        for parameter in &signature.parameters {
            collect_typedef_alias_from_type(&parameter.c_type, false, &mut aliases);
        }
    }
    collect_typedef_alias_from_type(
        spec.c_boundary
            .signatures
            .iter()
            .find(|signature| signature.function == spec.function_name)
            .map(|signature| signature.return_type.as_str())
            .unwrap_or_default(),
        true,
        &mut aliases,
    );

    aliases
        .into_iter()
        .map(|(name, kind)| match kind {
            "int" => format!("typedef int {name};\n"),
            _ if record_name_for_typedef_alias(&name, &structs).is_some() => {
                let record = record_name_for_typedef_alias(&name, &structs)
                    .expect("record alias checked above");
                format!("typedef struct {record} *{name};\n")
            }
            _ => format!("typedef void *{name};\n"),
        })
        .collect::<String>()
}

fn slice_source_constants(spec: &SliceSpec) -> String {
    let mut constants: BTreeMap<String, String> = BTreeMap::new();
    let build_profile_defines = build_profile_define_names(spec);
    let source_definitions = collect_defined_object_like_identifiers(&spec.c_source);
    for dependency in &spec.c_boundary.direct_dependencies {
        if dependency.kind != "constant" || dependency.name.trim().is_empty() {
            continue;
        }
        if build_profile_defines.contains(&dependency.name)
            || source_definitions.contains(&dependency.name)
        {
            continue;
        }
        if let Some(value) = dependency.value.as_ref().and_then(json_numeric_literal) {
            constants.insert(dependency.name.clone(), value);
        }
    }
    for name in collect_object_like_uppercase_identifiers(&spec.c_source) {
        if build_profile_defines.contains(&name) || source_definitions.contains(&name) {
            continue;
        }
        constants.entry(name).or_insert_with(|| "0".to_string());
    }

    constants
        .into_iter()
        .map(|(name, value)| format!("enum {{ {name} = {value} }};\n"))
        .collect::<String>()
}

fn collect_defined_object_like_identifiers(source: &str) -> BTreeSet<String> {
    let searchable_source = c_source_without_strings_and_comments(source);
    let mut definitions = collect_object_like_macro_definitions(&searchable_source);
    definitions.extend(collect_enum_constant_definitions(&searchable_source));
    definitions
}

fn collect_object_like_macro_definitions(source: &str) -> BTreeSet<String> {
    let mut definitions = BTreeSet::new();
    for line in source.lines() {
        let Some(rest) = line.trim_start().strip_prefix('#') else {
            continue;
        };
        let rest = rest.trim_start();
        let Some(rest) = rest.strip_prefix("define") else {
            continue;
        };
        if rest.as_bytes().first().is_some_and(|byte| is_c_ident_continue(*byte)) {
            continue;
        }
        let rest = rest.trim_start();
        let name_len = rest.bytes().take_while(|byte| is_c_ident_continue(*byte)).count();
        if name_len == 0 || rest.as_bytes().get(name_len) == Some(&b'(') {
            continue;
        }
        definitions.insert(rest[..name_len].to_string());
    }
    definitions
}

fn collect_enum_constant_definitions(source: &str) -> BTreeSet<String> {
    let bytes = source.as_bytes();
    let mut definitions = BTreeSet::new();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_identifier_at(source, index, "enum") {
            index += 1;
            continue;
        }
        let enum_end = index + "enum".len();
        let Some(open_brace) = enum_definition_body_open(source, enum_end) else {
            index = enum_end;
            continue;
        };
        index = open_brace + 1;
        let mut brace_depth = 1usize;
        let mut paren_depth = 0usize;
        let mut expects_name = true;
        while index < bytes.len() && brace_depth > 0 {
            match bytes[index] {
                b'{' => {
                    brace_depth += 1;
                    index += 1;
                }
                b'}' => {
                    brace_depth -= 1;
                    index += 1;
                }
                b'(' => {
                    paren_depth += 1;
                    index += 1;
                }
                b')' => {
                    paren_depth = paren_depth.saturating_sub(1);
                    index += 1;
                }
                b',' if brace_depth == 1 && paren_depth == 0 => {
                    expects_name = true;
                    index += 1;
                }
                byte if brace_depth == 1 && expects_name && is_c_ident_start(byte) => {
                    let start = index;
                    index += 1;
                    while index < bytes.len() && is_c_ident_continue(bytes[index]) {
                        index += 1;
                    }
                    definitions.insert(source[start..index].to_string());
                    expects_name = false;
                }
                _ => index += 1,
            }
        }
    }
    definitions
}

fn enum_definition_body_open(source: &str, mut index: usize) -> Option<usize> {
    let bytes = source.as_bytes();
    while index < bytes.len() && bytes[index].is_ascii_whitespace() {
        index += 1;
    }
    if index < bytes.len() && is_c_ident_start(bytes[index]) {
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        while index < bytes.len() && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
    }
    (index < bytes.len() && bytes[index] == b'{').then_some(index)
}

fn is_identifier_at(source: &str, index: usize, expected: &str) -> bool {
    let bytes = source.as_bytes();
    let end = index.saturating_add(expected.len());
    end <= bytes.len()
        && &source[index..end] == expected
        && (index == 0 || !is_c_ident_continue(bytes[index - 1]))
        && (end == bytes.len() || !is_c_ident_continue(bytes[end]))
}

fn build_profile_define_names(spec: &SliceSpec) -> BTreeSet<String> {
    spec.build_profile
        .defines
        .iter()
        .filter_map(|define| {
            let name = define.split_once('=').map(|(name, _)| name).unwrap_or(define);
            let name = name.trim();
            (!name.is_empty()
                && name.as_bytes().first().is_some_and(|byte| is_c_ident_start(*byte))
                && name.bytes().all(is_c_ident_continue))
            .then(|| name.to_string())
        })
        .collect()
}

fn slice_source_function_prototypes(spec: &SliceSpec) -> String {
    spec.c_boundary
        .signatures
        .iter()
        .filter(|signature| {
            !signature.function.trim().is_empty() && signature.function != spec.function_name
        })
        .map(signature_prototype)
        .collect::<String>()
}

fn signature_prototype(signature: &crate::CSignature) -> String {
    let params = if signature.parameters.is_empty() {
        "void".to_string()
    } else {
        signature
            .parameters
            .iter()
            .enumerate()
            .map(|(index, parameter)| {
                let name = if parameter.name.trim().is_empty() {
                    format!("arg{index}")
                } else {
                    parameter.name.clone()
                };
                format!("{} {}", parameter.c_type.trim(), name)
            })
            .collect::<Vec<_>>()
            .join(", ")
    };
    format!(
        "{} {}({});\n",
        signature.return_type.trim(),
        signature.function.trim(),
        params
    )
}

fn collect_struct_names(source: &str) -> BTreeSet<String> {
    let tokens = c_identifier_tokens(source);
    let mut names = BTreeSet::new();
    for window in tokens.windows(2) {
        if window[0] == "struct" && !is_builtin_type_token(&window[1]) {
            names.insert(window[1].clone());
        }
    }
    names
}

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
