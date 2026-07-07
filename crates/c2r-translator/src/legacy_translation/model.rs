#[derive(Clone, Debug)]
struct ParsedFunction {
    name: String,
    return_type: String,
    params: Vec<Param>,
    body: String,
}

#[derive(Clone, Debug)]
struct Param {
    name: String,
    c_type: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct ParsedStatement {
    text: String,
    kind: StatementKind,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum StatementKind {
    PrimitiveDeclaration,
    Assignment,
    CompoundAssignment,
    IncDec,
    Return,
    SimpleCall,
    If,
    While,
    For,
    BoundedInputBufferRead,
    PointerWrite,
    UnsupportedLValue,
    Expression,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Declaration {
    c_type: String,
    name: String,
    initializer: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Assignment {
    target: String,
    value: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct CompoundAssignment {
    target: String,
    operator: String,
    value: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct IncDecStatement {
    target: String,
    delta_operator: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct UnsupportedControlFlow {
    kind: &'static str,
    detail: Option<String>,
}

impl UnsupportedControlFlow {
    fn label(&self) -> String {
        match &self.detail {
            Some(detail) => format!("{}:{detail}", self.kind),
            None => self.kind.to_string(),
        }
    }

    fn block_id(&self) -> String {
        match &self.detail {
            Some(detail) => format!("{}-{}", self.kind, sanitize_cfg_id(detail)),
            None => self.kind.to_string(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum LValue {
    SimpleIdentifier {
        name: String,
    },
    PointerField {
        base: String,
        field: String,
    },
    DerefIdentifier {
        base: String,
    },
    BoundedPointerIndex {
        base: String,
        index: String,
    },
    BoundedPointerArithmeticIndex {
        base: String,
        index: String,
        source: String,
    },
    Unsupported {
        reason: String,
    },
}
