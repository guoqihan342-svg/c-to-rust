/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <flashdb.h>

/* slice: flashdb/real-fdb-kv-del */
/* function: fdb_kv_del */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-del.json */
/* fixture cases: 1 */
/* observable outputs: return_code */
/* fixture case: uninit-delete input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-del.json expected_outputs={"return_code": 7} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
fdb_err_t fdb_kv_del(fdb_kvdb_t db, const char *key);

int main(void) {
  puts("oracle harness draft for fdb_kv_del");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-del.json");
  struct fdb_kvdb uninit_delete_db = {0};
  uninit_delete_db.parent.name = "unit-kv";
  static const char uninit_delete_key[] = "boot_count";
  fdb_err_t actual_uninit_delete_return_code = fdb_kv_del(&uninit_delete_db, uninit_delete_key);
  if (actual_uninit_delete_return_code != (fdb_err_t)7u) {
    fprintf(stderr, "uninit-delete return_code mismatch: expected 7 got %d\n", (int)actual_uninit_delete_return_code);
    return 1;
  }
  puts("fixture case uninit-delete return_code matched");
  return 0;
}
