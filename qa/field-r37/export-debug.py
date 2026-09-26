#!/usr/bin/env python3
"""Export an isolated CI fixture, not credentials, caches or a deployed world."""
from pathlib import Path
import os
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
OUT = ROOT / 'artifacts/diagnostics.zip'
OUT.parent.mkdir(exist_ok=True)
count = 0

def add_tree(z, root, prefix, suffixes=None):
    global count
    if not root.is_dir():
        return
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        if suffixes is not None and path.suffix not in suffixes:
            continue
        if '.git' in path.parts:
            continue
        z.write(path, str(Path(prefix) / path.relative_to(root)))
        count += 1

with zipfile.ZipFile(OUT, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as z:
    tracked = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
    for name in tracked:
        path = ROOT / name
        if name and path.is_file() and not path.is_symlink():
            z.write(path, 'repo/' + name)
            count += 1
    z.writestr('SOURCE-COMMIT.txt', subprocess.check_output(['git','rev-parse','HEAD']))
    folia = ROOT / '.work/Folia'
    add_tree(z, folia/'folia-server/src', 'materialized/folia-server/src', {'.java'})
    add_tree(z, folia/'folia-api/src', 'materialized/folia-api/src', {'.java'})
    add_tree(z, ROOT/'.work/external-structures-r19', 'upstream-packs', {'.zip'})
    # Only the ephemeral loopback-bound CI fixture. No user/server directories.
    add_tree(z, ROOT/'.work/field-r36-water-square-seed', 'fixture')
    add_tree(z, ROOT/'.work/field-r37-water-only', 'water-only-fixture')
    for name in ('server.jar','R37DungeonQa.jar','pack-input-bundler.jar'):
        path = ROOT/'artifacts'/name
        if path.is_file():
            z.write(path, 'build/' + name)
    # The CI JDK, including legal notices, makes the fixture runnable without
    # downloading a different JDK or Maven dependencies during diagnosis.
    java_home = Path(os.environ.get('JAVA_HOME', '/nonexistent'))
    if java_home.is_dir():
        add_tree(z, java_home, 'jdk')
print(f'[R37 debug] exported {count} files, {OUT.stat().st_size} bytes')
