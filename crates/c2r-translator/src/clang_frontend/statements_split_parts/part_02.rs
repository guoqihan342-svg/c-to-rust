#[cfg(feature = "typed-ir")]
enum AssignmentCallComparisonNormalization {
    NotMatched,
    Rejected(String),
    Accepted {
        assignment: ClangStmtSkeleton,
        condition: ClangExprSkeleton,
    },
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Copy)]
enum DoWhileTailWrappedNode {
    Assignment,
    Call,
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Copy)]
enum AssignmentCallComparisonContext {
    DoWhileTail,
    IfCondition,
}

#[cfg(feature = "typed-ir")]
impl AssignmentCallComparisonContext {
    fn label(self) -> &'static str {
        match self {
            Self::DoWhileTail => "do-while tail",
            Self::IfCondition => "if condition",
        }
    }

    fn error_kind(self) -> &'static str {
        match self {
            Self::DoWhileTail => "invalid_do_stmt",
            Self::IfCondition => "invalid_if_stmt",
        }
    }

    fn comparison_operator(self, opcode: Option<&str>) -> Option<ClangBinaryOperator> {
        match (self, opcode) {
            (_, Some("==")) => Some(ClangBinaryOperator::Eq),
            (_, Some("!=")) => Some(ClangBinaryOperator::Neq),
            (_, Some("<")) => Some(ClangBinaryOperator::Lt),
            (_, Some("<=")) => Some(ClangBinaryOperator::Le),
            (_, Some(">")) => Some(ClangBinaryOperator::Gt),
            (_, Some(">=")) => Some(ClangBinaryOperator::Ge),
            _ => None,
        }
    }
}

#[cfg(feature = "typed-ir")]
include!("part_02_split_parts/part_00.rs");
include!("part_02_split_parts/part_01.rs");
include!("part_02_split_parts/part_02.rs");
