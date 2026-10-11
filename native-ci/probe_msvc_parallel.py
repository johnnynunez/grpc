"""Exercise actual setuptools MSVC dispatch with a timed spawn witness."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

import setuptools
from distutils.ccompiler import new_compiler

if '--patched' in sys.argv:
    from msvc_parallel import enable
    enable(4)

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    files = []
    for n in range(4):
        p = root / f'unit{n}.c'
        p.write_text(f'int unit{n}(void) {{ return {n}; }}\n')
        files.append(str(p))
    compiler = new_compiler(compiler='msvc')
    native = '--native' in sys.argv
    if native:
        compiler.initialize()
    else:
        compiler.initialized = True
        compiler.cc = 'cl.exe'
        compiler.compile_options = ['/nologo']
        compiler.compile_options_debug = ['/nologo']
    real_spawn = compiler.spawn
    active = maximum = 0
    lock = threading.Lock()
    def spawn(command, **kwargs):
        global active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.1)
        if native:
            real_spawn(command, **kwargs)
        with lock:
            active -= 1
    compiler.spawn = spawn
    outputs = compiler.compile(files, output_dir=str(root/'objects'))
    report = {'max_concurrent_compiler_calls': maximum, 'objects': len(outputs), 'patched': '--patched' in sys.argv, 'native_compile': native}
    if native:
        import struct
        report['coff_machines'] = [hex(struct.unpack_from('<H', Path(obj).read_bytes())[0]) for obj in outputs]
        # /GL objects use Microsoft's intermediate format, not normal COFF.
        assert all(Path(obj).stat().st_size > 0 for obj in outputs)
    print(json.dumps(report))
    assert maximum == 4, 'MSVC override bypasses base-class parallel patch'
    assert len(set(outputs)) == 4
