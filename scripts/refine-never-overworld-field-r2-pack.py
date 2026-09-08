#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
NOISE_SETTINGS = "data/minecraft/worldgen/noise_settings/overworld.json"
DEEP = {
    "neverfolia:never_overworld/deep_cavern": ("high", 1.70, -0.72),
    "neverfolia:never_overworld/deep_tunnel": ("low_abs", 4.80, -0.50),
    "neverfolia:never_overworld/deep_chasm": ("low_abs", 9.50, -0.52),
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][field-r2 pack] {message}")


def dump(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def contains_noise(value: object, noise_id: str) -> bool:
    if isinstance(value, dict):
        if value.get("type") == "minecraft:noise" and value.get("noise") == noise_id:
            return True
        return any(contains_noise(v, noise_id) for v in value.values())
    if isinstance(value, list):
        return any(contains_noise(v, noise_id) for v in value)
    return False


def add(a: object, b: object) -> dict:
    return {"type": "minecraft:add", "argument1": a, "argument2": b}


def mul(a: object, b: object) -> dict:
    return {"type": "minecraft:mul", "argument1": a, "argument2": b}


def clamp(value: object, minimum: float, maximum: float) -> dict:
    return {"type": "minecraft:clamp", "input": value, "min": minimum, "max": maximum}


def smooth_choice(node: dict, noise_id: str, mode: str, strength: float, floor: float) -> dict:
    source = node.get("input")
    if mode == "high":
        threshold = float(node.get("min_inclusive"))
        raw = mul(add(source, -threshold), -strength)
    else:
        threshold = float(node.get("max_exclusive"))
        raw = mul(add(threshold, mul(source, -1.0)), -strength)
    return clamp(raw, floor, 0.0)


def refine(value: object) -> object:
    if isinstance(value, list):
        return [refine(v) for v in value]
    if not isinstance(value, dict):
        return value
    node = {k: refine(v) for k, v in value.items()}
    if node.get("type") != "minecraft:range_choice":
        return node
    for noise_id, (mode, strength, floor) in DEEP.items():
        if contains_noise(node.get("input"), noise_id):
            return smooth_choice(node, noise_id, mode, strength, floor)
    return node


def count_deep_range_choices(value: object) -> int:
    if isinstance(value, dict):
        own = int(value.get("type") == "minecraft:range_choice" and any(contains_noise(value.get("input"), n) for n in DEEP))
        return own + sum(count_deep_range_choices(v) for v in value.values())
    if isinstance(value, list):
        return sum(count_deep_range_choices(v) for v in value)
    return 0


def transform(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    if MANIFEST not in entries or NOISE_SETTINGS not in entries:
        fail("NeverOverworld core entries missing")
    noise = json.loads(entries[NOISE_SETTINGS])
    before = noise["noise_router"]["final_density"]
    if count_deep_range_choices(before) != 3:
        fail(f"expected exactly three hard deep carve gates after field-r1, got {count_deep_range_choices(before)}")
    after = refine(before)
    if count_deep_range_choices(after) != 0:
        fail("hard deep carve gates survived field-r2 smoothing")
    noise["noise_router"]["final_density"] = after
    entries[NOISE_SETTINGS] = dump(noise)
    manifest = json.loads(entries[MANIFEST])
    manifest["field_regression_profile"] = "field-r2"
    manifest["deep_density_profile"] = "field-r2-continuous-carve-r6"
    manifest["deep_rectilinear_gate_removed"] = True
    entries[MANIFEST] = dump(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(entries):
            target.writestr(name, entries[name])
    return out.getvalue()


def apply_pack(path: Path) -> None:
    payload = transform(path.read_bytes())
    with tempfile.NamedTemporaryFile(prefix="nr-field-r2-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name); temp.write_bytes(payload)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][field-r2 pack] CONTINUOUS DEEP CAVE PROFILE APPLIED")
    print("  cavern/tunnel/chasm hard range gates: removed")


def self_test() -> None:
    cavern = {"type":"minecraft:range_choice","input":{"type":"minecraft:noise","noise":"neverfolia:never_overworld/deep_cavern","xz_scale":0.85,"y_scale":0.72},"min_inclusive":0.56,"max_exclusive":2.0,"when_in_range":-0.72,"when_out_of_range":0.0}
    tunnel = {"type":"minecraft:range_choice","input":{"type":"minecraft:abs","argument":{"type":"minecraft:noise","noise":"neverfolia:never_overworld/deep_tunnel","xz_scale":1.8,"y_scale":1.25}},"min_inclusive":0.0,"max_exclusive":0.105,"when_in_range":-0.50,"when_out_of_range":0.0}
    chasm = {"type":"minecraft:mul","argument1":{"type":"minecraft:range_choice","input":{"type":"minecraft:abs","argument":{"type":"minecraft:noise","noise":"neverfolia:never_overworld/deep_chasm","xz_scale":1.35,"y_scale":0.60}},"min_inclusive":0.0,"max_exclusive":0.055,"when_in_range":-0.52,"when_out_of_range":0.0},"argument2":{"type":"minecraft:y_clamped_gradient","from_y":-208,"to_y":-128,"from_value":1.0,"to_value":0.0}}
    root={"type":"minecraft:add","argument1":cavern,"argument2":{"type":"minecraft:add","argument1":tunnel,"argument2":chasm}}
    if count_deep_range_choices(root) != 3:
        fail("SELF-TEST: fixture hard-gate count drifted")
    patched=refine(root)
    if count_deep_range_choices(patched) != 0:
        fail("SELF-TEST: hard gates survived")
    text=json.dumps(patched)
    if text.count('minecraft:clamp') != 3:
        fail("SELF-TEST: expected three smooth clamps")
    print("[NeverFolia][field-r2 pack] SELF-TEST OK")


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.input is None:
        parser.error("--input is required")
    self_test(); apply_pack(args.input.resolve())


if __name__ == "__main__":
    main()
