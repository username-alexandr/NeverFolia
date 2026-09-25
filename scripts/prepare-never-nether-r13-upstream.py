#!/usr/bin/env python3
"""Reuse the inspected preparation script with an immutable diagnostic upstream.

The ordinary preparation script and its default branch policy are not modified.
Only its clone operation is substituted, before branding and pre-apply patches.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = '14b7fee5c866fca9a40ede4a58998fb928140f65'
SOURCE_SHA256 = '6a2cf083025ebace4611ec5791fe2afde114c9fe1b3df989a52d30bd15dee4b3'
OLD = 'git clone --depth 1 --branch "${FOLIA_REF}" "https://github.com/${FOLIA_REPOSITORY}.git" "${FOLIA_DIR}"'
NEW = '''git init --quiet "${FOLIA_DIR}"
git -C "${FOLIA_DIR}" remote add origin "https://github.com/${FOLIA_REPOSITORY}.git"
git -C "${FOLIA_DIR}" fetch --depth 1 origin ''' + PIN + '''
git -C "${FOLIA_DIR}" checkout --quiet --detach FETCH_HEAD
test "$(git -C "${FOLIA_DIR}" rev-parse HEAD)" = ''' + PIN


def transform(raw: bytes) -> str:
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('The inspected upstream preparation script changed; review before running')
    text = raw.decode('utf-8')
    if text.count(OLD) != 1:
        raise ValueError('Expected exactly one upstream clone operation')
    return text.replace(OLD, NEW, 1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-only', action='store_true')
    args = p.parse_args()
    original = ROOT / 'scripts/prepare-upstream.sh'
    text = transform(original.read_bytes())
    subprocess.run(['bash', '-n'], input=text, text=True, check=True)
    if args.check_only:
        print('Pinned R13 bootstrap contract verified; no repository fetched or modified')
        return
    print('Diagnostic upstream pinned to ' + PIN, flush=True)
    # Keep the temporary script beside its source so the existing dirname-based
    # ROOT_DIR, branding and pre-apply logic retain their exact original meaning.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', prefix='.r13-pinned-',
                                     dir=original.parent, encoding='utf-8') as script:
        script.write(text)
        script.flush()
        subprocess.run(['bash', script.name], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
