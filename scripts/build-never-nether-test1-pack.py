#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_BUILDER = ROOT / "scripts" / "build-never-nether-core-pack.py"
STRUCTURE_IMPORTER = ROOT / "scripts" / "build-never-nether-structure-pack.py"
STRUCTURE_HARDENER = ROOT / "scripts" / "harden-never-nether-structure-pack.py"

SOURCE_KEYS = (
    "hearths",
    "dungeons_and_taverns",
    "explorify",
    "structory_towers",
    "better_monuments",
)


def run(*args: object) -> None:
    command = [sys.executable, *(str(arg) for arg in args)]
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(sources: dict[str, Path], output: Path) -> None:
    missing = [key for key in SOURCE_KEYS if key not in sources]
    if missing:
        raise SystemExit(f"Missing TEST1 source archive(s): {', '.join(missing)}")

    for key, path in sources.items():
        if not path.is_file():
            raise SystemExit(f"Source archive not found: {key}={path}")

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="nevernether-test1-build-") as tmp_raw:
        tmp = Path(tmp_raw)
        core = tmp / "NeverNether-Core-NN-DEV-1-test1.zip"
        imported = tmp / "NeverNether-Structures-NN-DEV-1-test1.imported.zip"

        run(CORE_BUILDER, "--output", core)

        importer_args: list[object] = [STRUCTURE_IMPORTER, "--core", core]
        for key in SOURCE_KEYS:
            importer_args.extend(("--source", f"{key}={sources[key].resolve()}"))
        importer_args.extend(("--output", imported))
        run(*importer_args)

        run(STRUCTURE_HARDENER, "--input", imported, "--output", output)

    digest = sha256(output)
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")

    print("[NeverFolia][NeverNether TEST1] BUILD OK")
    print(f"  pack: {output}")
    print(f"  sha256: {digest}")
    print(f"  checksum: {checksum_path}")


def self_test() -> None:
    run(STRUCTURE_IMPORTER, "--self-test")
    run(STRUCTURE_HARDENER, "--self-test")
    with tempfile.TemporaryDirectory(prefix="nevernether-test1-core-") as tmp_raw:
        core = Path(tmp_raw) / "core.zip"
        run(CORE_BUILDER, "--output", core)
        if not core.is_file() or core.stat().st_size == 0:
            raise SystemExit("TEST1 SELF-TEST: core builder produced no output")
    print("[NeverFolia][NeverNether TEST1] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the complete licensing-safe NeverNether NN-DEV-1 TEST1 datapack"
    )
    parser.add_argument("--hearths", type=Path, help="Hearths v1.0.5 source ZIP")
    parser.add_argument(
        "--dungeons-and-taverns",
        dest="dungeons_and_taverns",
        type=Path,
        help="Dungeons and Taverns v5.3.2 source ZIP",
    )
    parser.add_argument("--explorify", type=Path, help="Explorify v1.6.5 source ZIP")
    parser.add_argument(
        "--structory-towers",
        dest="structory_towers",
        type=Path,
        help="Structory Towers v1.0.17 source ZIP",
    )
    parser.add_argument(
        "--better-monuments",
        dest="better_monuments",
        type=Path,
        help="Repurposed Structures / Better Monuments v7 compatibility ZIP",
    )
    parser.add_argument("--output", type=Path, help="Final hardened TEST1 datapack ZIP")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if args.output is None:
        parser.error("--output is required unless --self-test is used")

    sources = {
        key: value
        for key, value in (
            ("hearths", args.hearths),
            ("dungeons_and_taverns", args.dungeons_and_taverns),
            ("explorify", args.explorify),
            ("structory_towers", args.structory_towers),
            ("better_monuments", args.better_monuments),
        )
        if value is not None
    }
    build(sources, args.output)


if __name__ == "__main__":
    main()
