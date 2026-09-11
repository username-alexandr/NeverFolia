#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_SCRIPT = HERE / "audit-never-overworld-large-dry-caverns-r8.py"

spec = importlib.util.spec_from_file_location("nr_r8_cavern_audit_impl", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import {BASE_SCRIPT}")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def generated_chunks(region: Path):
    for path in sorted(region.glob("r.*.*.mca")):
        match = REGION_RE.match(path.name)
        if match is None:
            continue
        rx, rz = map(int, match.groups())
        with path.open("rb") as handle:
            header = handle.read(4096)
        if len(header) < 4096:
            continue
        for index in range(1024):
            packed = int.from_bytes(header[index * 4 : index * 4 + 4], "big")
            if packed == 0:
                continue
            lx = index & 31
            lz = index >> 5
            yield rx * 32 + lx, rz * 32 + lz


module.generated_chunks = generated_chunks

if __name__ == "__main__":
    module.main()
