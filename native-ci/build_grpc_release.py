"""Build exact, SHA256-verified release sdist; retain provenance."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

package, version, url, expected, commit = sys.argv[1:]
stage = Path(os.environ['STAGE'])
stage.mkdir(parents=True, exist_ok=True)
source = Path('source').resolve()
actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
assert actual == commit, (actual, commit)
archive = stage / url.rsplit('/', 1)[-1]
urllib.request.urlretrieve(url, archive)
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
assert sha == expected, (sha, expected)
# Short build paths also avoid MSVC response-file length limits.
root = Path(os.environ['RUNNER_TEMP']) / 'src'
root.mkdir(exist_ok=True)
with tarfile.open(archive) as tar:
    tar.extractall(root, filter='data')
extracted = next(p for p in root.iterdir() if p.is_dir())
relative = Path('tools/distrib/python/grpcio_tools/setup.py') if package == 'grpcio-tools' else Path('setup.py')
comparison = (extracted/'setup.py').read_bytes().replace(b'\r\n', b'\n') == (source/relative).read_bytes().replace(b'\r\n', b'\n')
assert comparison, 'sdist setup.py differs from exact tag checkout'
manifest = {'package': package, 'version': version, 'source_commit_witness': commit, 'build_input': 'published release sdist', 'sdist_url': url, 'sdist_sha256': sha, 'setup_py_matches_tag': comparison, 'git_source_is_not_build_input': True}
(stage/'provenance.json').write_text(json.dumps(manifest, indent=2))
env = os.environ.copy()
env['PIP_CONSTRAINT'] = str(Path(__file__).with_name('build-constraints.txt').resolve())
manifest['build_constraints'] = Path(env['PIP_CONSTRAINT']).read_text()
(stage/'provenance.json').write_text(json.dumps(manifest, indent=2))
env['GRPC_PYTHON_BUILD_EXT_COMPILER_JOBS'] = '4'
env['GRPC_PYTHON_BUILD_USE_SHORT_TEMP_DIR_NAME'] = '1'
# Old prepared sdists select POSIX during Cython generation. Regenerate from
# unchanged bundled .pyx using the release's exact Cython, on Windows itself.
if version == '1.72.2' and package == 'grpcio':
    cpp = extracted/'src/python/grpcio/grpc/_cython/cygrpc.cpp'
    manifest['cython_before_sha256'] = hashlib.sha256(cpp.read_bytes()).hexdigest()
    cpp.unlink()
    subprocess.run([sys.executable, '-m', 'cython', '--cplus', '-3', str(cpp.with_suffix('.pyx'))], check=True)
    assert '#include <unistd.h>' not in cpp.read_text(encoding='utf-8')
    manifest['cython_after_sha256'] = hashlib.sha256(cpp.read_bytes()).hexdigest()
    manifest['cython'] = '3.1.1; regenerated for native Windows from unchanged release .pyx'
manifest['msvc_compile_dispatch'] = 'harness-only bounded 4-worker MSVC override; same compiler flags'
manifest['installed_build_environment'] = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
(stage/'provenance.json').write_text(json.dumps(manifest, indent=2))
with (stage/'build.log').open('w', encoding='utf-8') as log:
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('msvc_parallel.py').resolve()), 'bdist_wheel', '--dist-dir', str(stage)], cwd=extracted, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=2100)
print((stage/'build.log').read_text(encoding='utf-8')[-18000:])
result.check_returncode()
