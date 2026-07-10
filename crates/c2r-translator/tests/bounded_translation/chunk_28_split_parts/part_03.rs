#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_rejects_escape_rebind_and_second_root() {
    let cases = ["call_escape", "rebind", "return_escape", "second_root"];
    for case in cases {
        let function_name = format!("reject_{case}_projection");
        let mut ast = interior_reborrow_fixture(&function_name);
        let function = interior_reborrow_function_mut(&mut ast, &function_name);
        match case {
            "call_escape" => {
                let body = interior_reborrow_body_mut(function);
                body[1] = serde_json::json!({
                    "kind": "CallExpr",
                    "type": { "qualType": "void" },
                    "inner": [
                        {
                            "kind": "DeclRefExpr",
                            "type": { "qualType": "void (struct Node *)" },
                            "referencedDecl": { "kind": "FunctionDecl", "name": "consume" }
                        },
                        {
                            "kind": "ImplicitCastExpr",
                            "castKind": "LValueToRValue",
                            "type": { "qualType": "struct Node *" },
                            "inner": [{
                                "kind": "DeclRefExpr",
                                "type": {
                                    "qualType": "NodeRef",
                                    "desugaredQualType": "struct Node *"
                                },
                                "referencedDecl": { "kind": "VarDecl", "name": "cursor" }
                            }]
                        }
                    ]
                });
            }
            "rebind" => {
                let body = interior_reborrow_body_mut(function);
                body[1]["inner"][0] = serde_json::json!({
                    "kind": "DeclRefExpr",
                    "type": {
                        "qualType": "NodeRef",
                        "desugaredQualType": "struct Node *"
                    },
                    "referencedDecl": { "kind": "VarDecl", "name": "cursor" }
                });
            }
            "return_escape" => {
                let body = interior_reborrow_body_mut(function);
                body[2]["inner"][0] = serde_json::json!({
                    "kind": "DeclRefExpr",
                    "type": {
                        "qualType": "NodeRef",
                        "desugaredQualType": "struct Node *"
                    },
                    "referencedDecl": { "kind": "VarDecl", "name": "cursor" }
                });
            }
            "second_root" => {
                let children = function["inner"].as_array_mut().unwrap();
                children.insert(1, serde_json::json!({
                    "kind": "ParmVarDecl",
                    "name": "other",
                    "type": { "qualType": "struct Owner *" }
                }));
            }
            _ => unreachable!(),
        }
        let reason = interior_reborrow_failure(&ast, &function_name);
        assert!(
            reason.contains("interior reborrow")
                || reason.contains("pointer")
                || reason.contains("return")
                || reason.contains("record"),
            "{case}: {reason}"
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_interior_reborrow_rejects_qualifiers_second_arrow_and_inventory_conflict() {
    for case in ["const", "volatile", "atomic", "second_arrow", "inventory"] {
        let function_name = format!("reject_{case}_projection");
        let mut ast = interior_reborrow_fixture(&function_name);
        match case {
            "const" | "volatile" | "atomic" => {
                let qualifier = match case {
                    "const" => "const struct Node *",
                    "volatile" => "volatile struct Node *",
                    _ => "_Atomic(struct Node *)",
                };
                ast["inner"][3]["type"]["qualType"] = serde_json::json!(qualifier);
            }
            "second_arrow" => {
                let function = interior_reborrow_function_mut(&mut ast, &function_name);
                let body = interior_reborrow_body_mut(function);
                body[1]["inner"][0]["isArrow"] = serde_json::json!(true);
            }
            "inventory" => {
                let duplicate = ast["inner"][2]["inner"][0].clone();
                ast["inner"][2]["inner"].as_array_mut().unwrap().push(duplicate);
            }
            _ => unreachable!(),
        }
        let reason = interior_reborrow_failure(&ast, &function_name);
        assert!(!reason.is_empty(), "{case} must fail closed");
    }
}
