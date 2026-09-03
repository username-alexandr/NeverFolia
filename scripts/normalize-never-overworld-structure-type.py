#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

BAD = "minecraft:jigusaw"
GOOD = "minecraft:jigsaw"
PREFIX = "data/neverfolia/worldgen/structure/"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld structures type] {message}")


def normalize_bytes(payload: bytes, *, expect_bad: int | None = 8) -> tuple[bytes, int]:
    src = zipfile.ZipFile(io.BytesIO(payload), "r")
    out = io.BytesIO()
    changed = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
        for info in src.infolist():
            raw = src.read(info.filename)
            if info.filename.startswith(PREFIX) and info.filename.endswith(".json"):
                value = json.loads(raw)
                if value.get("type") == BAD:
                    value["type"] = GOOD
                    raw = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
                    changed += 1
            dst.writestr(info, raw)
    src.close()
    if expect_bad is not None and changed != expect_bad:
        fail(f"expected {expect_bad} legacy '{BAD}' structure types, changed {changed}")
    return out.getvalue(), changed


def normalize(path: Path) -> None:
    payload, changed = normalize_bytes(path.read_bytes())
    with tempfile.NamedTemporaryFile(prefix="nr-structure-type-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
    try:
        temp.write_bytes(payload)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    with zipfile.ZipFile(path) as zf:
        wrong = []
        good = 0
        for name in zf.namelist():
            if not name.startswith(PREFIX) or not name.endswith(".json"):
                continue
            value = json.loads(zf.read(name))
            if value.get("type") == BAD:
                wrong.append(name)
            if value.get("type") == GOOD:
                good += 1
    if wrong:
        fail(f"legacy type survived in: {wrong}")
    if good < 8:
        fail(f"expected at least 8 '{GOOD}' NeverOverworld structures, got {good}")
    print("[NeverFolia][NeverOverworld structures type] NORMALIZE OK")
    print(f"  corrected: {changed}")
    print(f"  validated jigsaw structures: {good}")
    print(f"  pack: {path}")


def self_test() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(8):
            zf.writestr(
                f"{PREFIX}test_{i}.json",
                json.dumps({"type": BAD, "start_pool": f"neverfolia:test_{i}"}),
            )
        zf.writestr("data/minecraft/worldgen/structure/village.json", json.dumps({"type": GOOD}))
    fixed, changed = normalize_bytes(buf.getvalue())
    if changed != 8:
        fail(f"SELF-TEST: changed {changed} entries")
    with zipfile.ZipFile(io.BytesIO(fixed)) as zf:
        for i in range(8):
            value = json.loads(zf.read(f"{PREFIX}test_{i}.json"))
            if value.get("type") != GOOD:
                fail(f"SELF-TEST: test_{i} not normalized")
    print("[NeverFolia][NeverOverworld structures type] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize legacy NeverOverworld jigsaw structure type typo")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required unless --self-test is used")
    if not args.input.is_file():
        fail(f"pack not found: {args.input}")
    normalize(args.input)


if __name__ == "__main__":
    main()
