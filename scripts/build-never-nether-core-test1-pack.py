#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_BUILDER = ROOT / "scripts/build-never-nether-core-pack.py"
BASALT_BLOBS_OVERRIDE = Path("data/minecraft/worldgen/placed_feature/basalt_blobs.json")
DELTA_OVERRIDE = Path("data/minecraft/worldgen/placed_feature/delta.json")
MANIFEST = Path("nevernether-core-manifest.json")


def load_base_builder():
    spec = importlib.util.spec_from_file_location("nevernether_core_builder", BASE_BUILDER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load base NeverNether builder: {BASE_BUILDER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finalize_pack_tree(root: Path) -> None:
    basalt_override = root / BASALT_BLOBS_OVERRIDE
    if not basalt_override.is_file():
        raise SystemExit(
            "Expected diagnostic basalt_blobs override is missing; base builder contract changed"
        )
    basalt_override.unlink()

    delta_override = root / DELTA_OVERRIDE
    if not delta_override.is_file():
        raise SystemExit("Deterministic delta override is missing")

    manifest_path = root / MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["replaced_vanilla_placed_features"] = ["delta"]
    manifest.pop("diagnostic_disabled_placed_features", None)
    manifest["netherrack_replace_blobs_mode"] = "vanilla_geometry_chunk_owned_v1"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build(output: Path) -> None:
    base = load_base_builder()
    with tempfile.TemporaryDirectory(prefix="nevernether-core-test1-") as tmp:
        root = Path(tmp) / "pack"
        root.mkdir()
        base.build_pack(root)
        finalize_pack_tree(root)
        base.validate_json(root)

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="nevernether-core-test1-selftest-") as tmp:
        output = Path(tmp) / "NeverNether-Core.zip"
        build(output)
        with zipfile.ZipFile(output) as zf:
            names = set(zf.namelist())
            manifest = json.loads(zf.read(MANIFEST.as_posix()))
            delta = json.loads(zf.read(DELTA_OVERRIDE.as_posix()))

        assert BASALT_BLOBS_OVERRIDE.as_posix() not in names
        assert DELTA_OVERRIDE.as_posix() in names
        assert manifest["replaced_vanilla_placed_features"] == ["delta"]
        assert "diagnostic_disabled_placed_features" not in manifest
        assert manifest["netherrack_replace_blobs_mode"] == "vanilla_geometry_chunk_owned_v1"
        assert delta["placement"][0] == {"type": "minecraft:count", "count": 0}
    print("[NeverFolia][NeverNether core TEST1] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the finalized NeverNether 26.2 TEST1 core datapack"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.output is None:
        parser.error("--output is required unless --self-test is used")
    build(args.output)
    print(f"Built finalized TEST1 core pack: {args.output}")


if __name__ == "__main__":
    main()
