英文镜像见 `README.en.md`。

# CFG Template

This template records C control-flow evidence before Rust draft generation.

中文说明：CFG evidence 记录 functions、basic blocks、edges、branches、returns、unsupported control-flow nodes 和 source spans。遇到 goto、switch fallthrough、setjmp/longjmp、computed goto 或 inline assembly 等未支持控制流时，必须显式记录并阻止自动成功声明。

## Files

- `cfg.schema.json`
- `cfg.example.json`
- `checklist.md`
