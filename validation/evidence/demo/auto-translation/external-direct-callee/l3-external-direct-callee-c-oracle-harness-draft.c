/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>

/* slice: demo/external-direct-callee */
/* function: call_helper_chain */
/* fixture input: validation/l2_slices/fixtures/external-direct-callee-c-oracle.json */
/* fixture cases: 3 */
/* observable outputs: return_value, status, external_callee_call_count, external_callee_contexts, external_callee_bindings, source_calls */
/* fixture case: negative-two input_ref=cases[0] expected_ref=validation/evidence/demo/l3-external-direct-callee-c-oracle.json expected_outputs={"external_callee_bindings": ["helper_add_one:int->int", "helper_add_one:int->int", "helper_add_one:int->int"], "external_callee_call_count": 3, "external_callee_contexts": ["declaration_initializer", "assignment", "return"], "return_value": 1, "source_calls": ["int first = helper_add_one(value)", "value = helper_add_one(first)", "return helper_add_one(value)"], "status": "ok"} */
/* fixture case: zero input_ref=cases[2] expected_ref=validation/evidence/demo/l3-external-direct-callee-c-oracle.json expected_outputs={"external_callee_bindings": ["helper_add_one:int->int", "helper_add_one:int->int", "helper_add_one:int->int"], "external_callee_call_count": 3, "external_callee_contexts": ["declaration_initializer", "assignment", "return"], "return_value": 3, "source_calls": ["int first = helper_add_one(value)", "value = helper_add_one(first)", "return helper_add_one(value)"], "status": "ok"} */
/* fixture case: seven input_ref=cases[4] expected_ref=validation/evidence/demo/l3-external-direct-callee-c-oracle.json expected_outputs={"external_callee_bindings": ["helper_add_one:int->int", "helper_add_one:int->int", "helper_add_one:int->int"], "external_callee_call_count": 3, "external_callee_contexts": ["declaration_initializer", "assignment", "return"], "return_value": 10, "source_calls": ["int first = helper_add_one(value)", "value = helper_add_one(first)", "return helper_add_one(value)"], "status": "ok"} */
/* source file: validation/l2_slices/tools/generate_external_direct_callee_oracle.py (sha256: e79a6c596f72e8ffd312f323f3bc65564b5cf0c608c92ac3ce8ce388f8816a69) */
/* source file: validation/l2_slices/tools/generate_external_direct_callee_oracle.py (sha256: e79a6c596f72e8ffd312f323f3bc65564b5cf0c608c92ac3ce8ce388f8816a69) */
/* source file: validation/l2_slices/fixtures/external-direct-callee-c-oracle.json (sha256: unknown) */
int call_helper_chain(int value);

int main(void) {
  puts("oracle harness draft for call_helper_chain");
  puts("fixture input: validation/l2_slices/fixtures/external-direct-callee-c-oracle.json");
  /* TODO: load fixture values, call the target function, and compare observable outputs. */
  return 0;
}
