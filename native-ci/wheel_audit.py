"""Strict native wheel integrity audit; usable without third-party modules."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import zipfile


def audit(path):
    path = Path(path)
    result = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "pe": []}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert len(names) == len(set(names)), "duplicate zip entries"
        record = next(n for n in names if n.endswith('.dist-info/RECORD'))
        rows = list(csv.reader(io.StringIO(z.read(record).decode())))
        assert {r[0] for r in rows} == {n for n in names if not n.endswith('/')}, 'RECORD coverage'
        for name, digest, size in rows:
            raw = z.read(name)
            if name != record:
                algo, encoded = digest.split('=', 1)
                actual = base64.urlsafe_b64encode(hashlib.new(algo, raw).digest()).rstrip(b'=').decode()
                assert actual == encoded, f'RECORD hash {name}'
                assert len(raw) == int(size), f'RECORD size {name}'
            if raw.startswith(b'MZ'):
                off = struct.unpack_from('<I', raw, 0x3c)[0]
                assert raw[off:off+4] == b'PE\0\0', name
                machine = struct.unpack_from('<H', raw, off+4)[0]
                result['pe'].append({'path': name, 'machine': hex(machine)})
        result['records'] = len(rows)
        result['metadata'] = z.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
        result['wheel'] = z.read(next(n for n in names if n.endswith('.dist-info/WHEEL'))).decode()
    assert result['pe'], 'no native PE'
    assert all(x['machine'] == '0xaa64' for x in result['pe']), result['pe']
    assert 'win_arm64' in path.name, path.name
    return result


def negative_control(path):
    """Prove corruption is rejected, not just that an audit returns zero."""
    src = Path(path)
    bad = src.parent / ('corrupt-' + src.name)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(bad, 'w') as zout:
        target = next(n for n in zin.namelist() if n.endswith('.py'))
        for name in zin.namelist():
            zout.writestr(name, zin.read(name) + (b'\n# corrupt\n' if name == target else b''))
    try:
        try:
            audit(bad)
        except AssertionError as exc:
            assert 'RECORD' in str(exc), str(exc)
            return str(exc)
        raise AssertionError('corrupt wheel accepted')
    finally:
        bad.unlink()


if __name__ == '__main__':
    wheels = sorted(Path(sys.argv[1]).glob('*.whl'))
    assert wheels, 'no wheels'
    reports = []
    for wheel in wheels:
        report = audit(wheel)
        report['corruption_negative'] = negative_control(wheel)
        reports.append(report)
    text = json.dumps(reports, indent=2)
    Path(sys.argv[1], 'wheel-audit.json').write_text(text)
    print(text)
