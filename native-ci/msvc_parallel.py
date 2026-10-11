"""Bound MSVC compile dispatch in the verification harness, not gRPC source."""
from concurrent.futures import ThreadPoolExecutor


def enable(jobs=4):
    import setuptools  # Install the distutils alias used by build_ext.
    from distutils.compilers.C.msvc import Compiler
    original = Compiler.compile

    def compile_parallel(self, sources, output_dir=None, macros=None, include_dirs=None,
                         debug=False, extra_preargs=None, extra_postargs=None, depends=None):
        # Initialize VC environment once, before concurrent compiler calls.
        if not self.initialized:
            self.initialize()
        def compile_one(source):
            return original(self, [source], output_dir, macros, include_dirs, debug,
                            list(extra_preargs) if extra_preargs else None,
                            list(extra_postargs) if extra_postargs else None, depends)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            return [obj for batch in pool.map(compile_one, sources) for obj in batch]

    Compiler.compile = compile_parallel


if __name__ == '__main__':
    import os
    import runpy
    import sys
    enable(int(os.environ.get('GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS', '4')))
    sys.argv = ['setup.py', *sys.argv[1:]]
    runpy.run_path('setup.py', run_name='__main__')
