"""Restore the committed synthetic research snapshot (standard library only)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def restore(root: Path, verify_only: bool = False) -> None:
    release = root / 'artifacts/research'
    manifest = json.loads((release / 'manifest.json').read_text(encoding='utf8'))
    for entry in manifest['archives']:
        archive = release / entry['file']
        if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Archive checksum mismatch: {archive.name}')
        with zipfile.ZipFile(archive) as source:
            for info in source.infolist():
                name = PurePosixPath(info.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in info.filename:
                    raise ValueError('Unsafe archive path')
                target = (root / entry['destination'] / Path(*name.parts)).resolve()
                if not target.is_relative_to((root / '.cache').resolve()):
                    raise ValueError('Archive destination outside .cache')
                data = source.read(info)
                expected = entry['files'][info.filename]
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError(f'File checksum mismatch: {info.filename}')
                if target.exists():
                    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                        raise ValueError(f'Existing file differs; preserved: {target}')
                elif verify_only:
                    raise ValueError(f'Missing restored file: {target}')
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
        print(f'Verified {len(entry["files"])} files: {entry["destination"]}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    restore(ROOT, args.verify_only)
