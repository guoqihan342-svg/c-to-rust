project('build_ir_equivalence_extended', 'c')
threads = dependency('threads')
core = static_library('core', 'src/core.c', include_directories: include_directories('include'), c_args: ['-DCORE_SCALE=3'])
executable('program', 'src/main.c', link_with: core, dependencies: threads)
