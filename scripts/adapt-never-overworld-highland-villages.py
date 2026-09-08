#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
EXTRA = {
    "village_plains": ["minecraft:meadow", "minecraft:cherry_grove"],
    "village_taiga": ["minecraft:old_growth_pine_taiga", "minecraft:old_growth_spruce_taiga"],
    "village_snowy": ["minecraft:grove", "minecraft:snowy_slopes"],
    "village_savanna": ["minecraft:savanna_plateau", "minecraft:windswept_savanna"],
    "village_desert": ["minecraft:badlands", "minecraft:wooded_badlands", "minecraft:eroded_badlands"],
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld highland villages] {message}")


def dump(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def transform(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    if MANIFEST not in entries:
        fail("NeverOverworld manifest missing")
    for name, values in EXTRA.items():
        path = f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"
        if path in entries:
            fail(f"pack already overrides {path}; merge policy must be reviewed")
        entries[path] = dump({"replace": False, "values": values})
    manifest = json.loads(entries[MANIFEST])
    manifest["village_surface_policy"] = "strict-dry-highland-r6-radius8"
    manifest["village_dry_samples"] = 9
    manifest["village_dry_radius"] = 8
    manifest["village_spacing"] = 34
    manifest["village_highland_biomes"] = EXTRA
    entries[MANIFEST] = dump(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(entries):
            target.writestr(name, entries[name])
    return out.getvalue()


def apply_pack(path: Path) -> None:
    payload = transform(path.read_bytes())
    with tempfile.NamedTemporaryFile(prefix="nr-highland-villages-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
        temp.write_bytes(payload)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][NeverOverworld highland villages] STRICT RADIUS8 HIGHLAND POLICY APPLIED")
    print("  dry prefilter: 9/9 samples, radius=8")
    print("  persisted village bbox zero-water audit remains authoritative")
    print("  structure spacing: vanilla 34")


def self_test() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, dump({"schema": 1}))
    result = transform(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        manifest = json.loads(z.read(MANIFEST))
        for name, values in EXTRA.items():
            tag = json.loads(z.read(f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"))
            if tag != {"replace": False, "values": values}:
                fail(f"SELF-TEST: wrong biome tag for {name}: {tag}")
    if manifest.get("village_surface_policy") != "strict-dry-highland-r6-radius8":
        fail("SELF-TEST: manifest marker missing")
    if manifest.get("village_dry_samples") != 9 or manifest.get("village_dry_radius") != 8:
        fail(f"SELF-TEST: radius8 R6 dry contract mismatch: {manifest}")
    print("[NeverFolia][NeverOverworld highland villages] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.input is None:
        parser.error("--input is required")
    self_test()
    apply_pack(args.input.resolve())


if __name__ == "__main__":
    main()
