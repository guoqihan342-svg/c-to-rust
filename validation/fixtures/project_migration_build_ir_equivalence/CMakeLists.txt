cmake_minimum_required(VERSION 3.16)
project(build_ir_equivalence C)

add_executable(program src/unit.c)
target_compile_definitions(program PRIVATE VALUE=7)
