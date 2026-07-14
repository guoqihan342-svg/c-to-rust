cmake_minimum_required(VERSION 3.16)
project(build_ir_equivalence_extended C)

find_package(Threads REQUIRED)
add_library(core STATIC src/core.c)
target_include_directories(core PUBLIC include)
target_compile_definitions(core PRIVATE CORE_SCALE=3)
add_executable(program src/main.c)
target_link_libraries(program PRIVATE core Threads::Threads)
