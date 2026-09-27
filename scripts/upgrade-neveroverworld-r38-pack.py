#!/usr/bin/env python3
"""Replace only the pinned D&T drowned function, using an atomic ZIP rewrite."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

FUNCTION = 'data/nova_structures/function/jockey/make_drowned_into_jockey.mcfunction'
OUTPUT = b'# R38: one owning-entity spawn/ride/consume transaction.\nneverfolia:dnt drowned_mount\n'
KNOWN = {
    'execute at @s run summon minecraft:zombie_nautilus ~ ~ ~ {PersistenceRequired:1b,Tags:["dnt_jockey_mount_tmp"]}\nexecute at @s run ride @s mount @e[type=minecraft:zombie_nautilus,tag=dnt_jockey_mount_tmp,distance=..2,sort=nearest,limit=1]',
    'execute summon zombie_nautilus run execute at @s run ride @n[type=drowned] mount @s\nneverfolia:dnt clear_saddle',
}


def upgrade(path: Path) -> dict:
    path = Path(path)
    temporary = None
    try:
        with zipfile.ZipFile(path) as src:
            names = src.namelist()
            if len(names) != len(set(names)):
                raise ValueError('duplicate ZIP entry')
            if FUNCTION not in names:
                return {'pack': path.name, 'function_present': False, 'modified': False}
            previous = src.read(FUNCTION)
            if previous == OUTPUT:
                return {'pack': path.name, 'function_present': True, 'modified': False}
            if previous.decode('utf-8').strip() not in KNOWN:
                raise ValueError('Unknown drowned-controller source contract')
            with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.zip', delete=False) as handle:
                temporary = Path(handle.name)
            with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as target:
                target.comment = src.comment
                for info in src.infolist():
                    data = OUTPUT if info.filename == FUNCTION else src.read(info)
                    # writestr mutates ZipInfo.header_offset/CRC/sizes. Never hand it
                    # the source reader's own object: later src.read would consult
                    # destination offsets and report false overlapping entries.
                    target.writestr(copy.copy(info), data)
            with zipfile.ZipFile(temporary) as target:
                if target.namelist() != names or target.comment != src.comment:
                    raise ValueError('ZIP inventory or archive comment changed')
                for info in src.infolist():
                    expected = OUTPUT if info.filename == FUNCTION else src.read(info)
                    if target.read(info.filename) != expected:
                        raise ValueError('Unexpected file mutation: ' + info.filename)
            # Source and output handles are closed before replacement (also valid
            # on Windows). CRC/read errors leave the original archive untouched.
        with temporary.open('rb') as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        'pack': path.name, 'function_present': True, 'modified': True,
        'previous_function_sha256': hashlib.sha256(previous).hexdigest(),
        'new_function_sha256': hashlib.sha256(OUTPUT).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = upgrade(args.input)
    if args.report:
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
