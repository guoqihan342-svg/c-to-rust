use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AddI32PairAliasCase {
    Disjoint,
    LhsRhsReadAlias,
    LhsOutOverlapRisk,
    RhsOutOverlapRisk,
}

impl AddI32PairAliasCase {
    pub fn from_fixture(value: &str) -> Option<Self> {
        match value {
            "disjoint" => Some(Self::Disjoint),
            "lhs_rhs_read_alias" => Some(Self::LhsRhsReadAlias),
            "lhs_out_overlap_risk" => Some(Self::LhsOutOverlapRisk),
            "rhs_out_overlap_risk" => Some(Self::RhsOutOverlapRisk),
            _ => None,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::Disjoint => "disjoint",
            Self::LhsRhsReadAlias => "lhs_rhs_read_alias",
            Self::LhsOutOverlapRisk => "lhs_out_overlap_risk",
            Self::RhsOutOverlapRisk => "rhs_out_overlap_risk",
        }
    }

    fn is_safe_noalias(self) -> bool {
        matches!(self, Self::Disjoint | Self::LhsRhsReadAlias)
    }

    fn alias_matrix(self) -> Vec<String> {
        match self {
            Self::Disjoint => vec![
                "lhs-rhs:disjoint".to_owned(),
                "lhs-out:disjoint".to_owned(),
                "rhs-out:disjoint".to_owned(),
            ],
            Self::LhsRhsReadAlias => vec![
                "lhs-rhs:read_read_alias_allowed".to_owned(),
                "lhs-out:disjoint".to_owned(),
                "rhs-out:disjoint".to_owned(),
            ],
            Self::LhsOutOverlapRisk => vec![
                "lhs-rhs:disjoint".to_owned(),
                "lhs-out:overlap_risk_rejected".to_owned(),
                "rhs-out:disjoint".to_owned(),
            ],
            Self::RhsOutOverlapRisk => vec![
                "lhs-rhs:disjoint".to_owned(),
                "lhs-out:disjoint".to_owned(),
                "rhs-out:overlap_risk_rejected".to_owned(),
            ],
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct AddI32PairPtrArithReport {
    pub return_code: i32,
    pub status: &'static str,
    pub len: i32,
    pub lhs: Vec<i32>,
    pub rhs: Vec<i32>,
    pub out_values: Vec<i32>,
    pub source_reads: &'static str,
    pub canonical_reads: &'static str,
    pub source_writes: &'static str,
    pub canonical_writes: &'static str,
    pub write_count: usize,
    pub safe_noalias_precondition: bool,
    pub alias_case: &'static str,
    pub alias_matrix: Vec<String>,
}

pub fn add_i32_pair_ptr_arith(
    lhs: &[i32],
    rhs: &[i32],
    alias_case: AddI32PairAliasCase,
) -> AddI32PairPtrArithReport {
    let safe_noalias_precondition = alias_case.is_safe_noalias();
    let len = lhs.len().min(rhs.len());
    if !safe_noalias_precondition {
        return AddI32PairPtrArithReport {
            return_code: -1,
            status: "rejected_overlap_risk",
            len: len as i32,
            lhs: lhs[..len].to_vec(),
            rhs: rhs[..len].to_vec(),
            out_values: Vec::new(),
            source_reads: "*(lhs + i), *(rhs + i) under i < len",
            canonical_reads: "lhs[i], rhs[i]",
            source_writes: "*(out + i) under i < len",
            canonical_writes: "out[i]",
            write_count: 0,
            safe_noalias_precondition,
            alias_case: alias_case.as_str(),
            alias_matrix: alias_case.alias_matrix(),
        };
    }

    let mut out_values = Vec::with_capacity(len);
    for index in 0..len {
        out_values.push(lhs[index] + rhs[index]);
    }

    AddI32PairPtrArithReport {
        return_code: 0,
        status: "ok",
        len: len as i32,
        lhs: lhs[..len].to_vec(),
        rhs: rhs[..len].to_vec(),
        out_values,
        source_reads: "*(lhs + i), *(rhs + i) under i < len",
        canonical_reads: "lhs[i], rhs[i]",
        source_writes: "*(out + i) under i < len",
        canonical_writes: "out[i]",
        write_count: len,
        safe_noalias_precondition,
        alias_case: alias_case.as_str(),
        alias_matrix: alias_case.alias_matrix(),
    }
}
