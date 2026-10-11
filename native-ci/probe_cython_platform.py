"""Reproduce platform-dependent Cython output from the exact release."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

p = argparse.ArgumentParser()
p.add_argument('archive', type=Path)
p.add_argument('destination', type=Path)
p.add_argument('--regenerate', action='store_true')
a = p.parse_args()
a.destination.mkdir(parents=True, exist_ok=True)
with tarfile.open(a.archive) as tar:
    tar.extractall(a.destination, filter='data')
root = a.destination/'grpcio-1.72.2'
source = root/'src/python/grpcio/grpc/_cython/cygrpc.pyx'
cpp = source.with_suffix('.cpp')
before = hashlib.sha256(cpp.read_bytes()).hexdigest()
if a.regenerate:
    cpp.unlink()
    subprocess.run([sys.executable, '-m', 'cython', '--cplus', '-3', '-E', 'UNAME_SYSNAME=Windows', '-I', str(source.parent), str(source)], check=True)
text = cpp.read_text()
result = {'regenerated': a.regenerate, 'before_sha256': before, 'after_sha256': hashlib.sha256(cpp.read_bytes()).hexdigest(), 'unconditional_unistd': '#include <unistd.h>' in text, 'native_compile': False}
print(json.dumps(result))
assert not result['unconditional_unistd'], 'release generated POSIX path despite Windows target'
assert 'send(' in text, 'Windows socket writer missing'
