fn execute_step(state: &mut ReplayState, operation: &Operation) -> StepReport {
    match execute_operation(state, operation) {
        Ok(fields) => StepReport {
            id: operation.id.clone(),
            op: operation.op.clone(),
            status: "ok".to_string(),
            code: "OK".to_string(),
            fields,
        },
        Err(err) => StepReport {
            id: operation.id.clone(),
            op: operation.op.clone(),
            status: "error".to_string(),
            code: err.code().to_string(),
            fields: vec![("message".to_string(), json_string(&err.to_string()))],
        },
    }
}

fn execute_operation(
    state: &mut ReplayState,
    operation: &Operation,
) -> Result<Vec<(String, String)>> {
    match operation.op.as_str() {
        "kv.set" => {
            let key = operation.required("key")?;
            let value = operation.required("value")?;
            state.kv.set(&key, value.as_bytes())?;
            Ok(vec![
                ("key".to_string(), json_string(&key)),
                ("value".to_string(), json_string(&value)),
            ])
        }
        "kv.get" => {
            let key = operation.required("key")?;
            let value = state.kv.get(&key)?;
            Ok(vec![(
                "value".to_string(),
                optional_bytes_json(value.as_deref()),
            )])
        }
        "kv.delete" => {
            let key = operation.required("key")?;
            state.kv.delete(&key)?;
            Ok(vec![("key".to_string(), json_string(&key))])
        }
        "kv.entries" => Ok(vec![(
            "entries".to_string(),
            kv_entries_json(&state.kv.entries()),
        )]),
        "kv.compact" => {
            state.kv.compact()?;
            Ok(vec![(
                "image_hash".to_string(),
                json_string(&state.kv.image_hash()?),
            )])
        }
        "kv.reopen" => {
            state.kv.reopen()?;
            Ok(vec![(
                "image_hash".to_string(),
                json_string(&state.kv.image_hash()?),
            )])
        }
        "kv.image_hash" => Ok(vec![(
            "image_hash".to_string(),
            json_string(&state.kv.image_hash()?),
        )]),
        "ts.append" => {
            let timestamp = operation.required_i64("timestamp")?;
            let value = operation.required("value")?;
            let id = state.ts.append(timestamp, value.as_bytes())?;
            Ok(vec![
                ("entry_id".to_string(), id.to_string()),
                ("timestamp".to_string(), timestamp.to_string()),
                ("value".to_string(), json_string(&value)),
            ])
        }
        "ts.query" => {
            let from = operation.required_i64("from")?;
            let to = operation.required_i64("to")?;
            Ok(vec![(
                "entries".to_string(),
                ts_entries_json(&state.ts.query(from, to)),
            )])
        }
        "ts.count_status" => {
            let from = operation.required_i64("from")?;
            let to = operation.required_i64("to")?;
            let status = parse_status(&operation.required("status")?)?;
            let count = state.ts.count_by_status(from, to, status);
            Ok(vec![("count".to_string(), count.to_string())])
        }
        "ts.set_status" => {
            let id = operation.required_u64("entry_id")?;
            let status = parse_status(&operation.required("status")?)?;
            state.ts.set_status(id, status)?;
            Ok(vec![
                ("entry_id".to_string(), id.to_string()),
                ("ts_status".to_string(), json_string(status_name(status))),
            ])
        }
        "ts.reopen" => {
            state.ts.reopen()?;
            Ok(vec![(
                "image_hash".to_string(),
                json_string(&state.ts.image_hash()?),
            )])
        }
        "ts.image_hash" => Ok(vec![(
            "image_hash".to_string(),
            json_string(&state.ts.image_hash()?),
        )]),
        other => Err(Error::Cli(format!("unknown fixture operation {other}"))),
    }
}

impl Operation {
    fn required(&self, name: &str) -> Result<String> {
        self.fields
            .get(name)
            .cloned()
            .ok_or_else(|| Error::Parse(format!("operation {} missing field {name}", self.id)))
    }

    fn required_i64(&self, name: &str) -> Result<i64> {
        self.required(name)?
            .parse()
            .map_err(|_| Error::Parse(format!("operation {} invalid i64 field {name}", self.id)))
    }

    fn required_u64(&self, name: &str) -> Result<u64> {
        self.required(name)?
            .parse()
            .map_err(|_| Error::Parse(format!("operation {} invalid u64 field {name}", self.id)))
    }
}
