#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_BUILDER = ROOT / "scripts" / "build-never-nether-core-pack.py"
STRUCTURE_IMPORTER = ROOT / "scripts" / "build-never-nether-structure-pack.py"
STRUCTURE_HARDENER = ROOT / "scripts" / "harden-never-nether-structure-pack.py"
FINGERPRINT_TOOL = ROOT / "scripts" / "fingerprint-never-nether-pack.py"
SOURCE_MANIFEST = ROOT / "worldgen-sources" / "never-nether" / "manifest.json"

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


def load_source_manifest() -> dict:
    manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("worldgen_id") != "NN-DEV-1":
        raise SystemExit("NeverNether source manifest worldgen_id mismatch")
    if manifest.get("minecraft") != "26.2":
        raise SystemExit("NeverNether source manifest Minecraft version mismatch")
    return manifest


def validate_sources(
    sources: dict[str, Path],
    *,
    require_pinned: bool,
) -> list[dict]:
    manifest = load_source_manifest()
    manifest_sources = manifest["sources"]

    missing = [key for key in SOURCE_KEYS if key not in sources]
    if missing:
        raise SystemExit(f"Missing TEST1 source archive(s): {', '.join(missing)}")

    observed: list[dict] = []
    unpinned: list[str] = []
    for key in SOURCE_KEYS:
        path = sources[key]
        if not path.is_file():
            raise SystemExit(f"Source archive not found: {key}={path}")

        expected = manifest_sources[key]
        expected_name = expected["filename"]
        if path.name != expected_name:
            raise SystemExit(
                f"{key}: exact source filename required: {expected_name!r}, got {path.name!r}"
            )

        actual_hash = sha256(path)
        expected_hash = expected.get("sha256")
        if expected_hash is not None and actual_hash.lower() != expected_hash.lower():
            raise SystemExit(
                f"{key}: SHA-256 mismatch for {path.name}: expected {expected_hash}, got {actual_hash}"
            )
        if expected_hash is None:
            unpinned.append(key)

        observed.append(
            {
                "key": key,
                "version": expected["version"],
                "filename": expected_name,
                "sha256": actual_hash,
                "manifest_sha256": expected_hash,
                "hash_status": "pinned_verified" if expected_hash else "observed_unpinned",
            }
        )

    if require_pinned and unpinned:
        raise SystemExit(
            "Source manifest is not release-complete; missing pinned SHA-256 for: "
            + ", ".join(unpinned)
        )
    return observed


def inject_source_lock(output: Path, observed_sources: list[dict]) -> None:
    source_lock = {
        "schema": 1,
        "worldgen_id": "NN-DEV-1",
        "minecraft": "26.2",
        "test_profile": "TEST1",
        "source_manifest": "worldgen-sources/never-nether/manifest.json",
        "sources": observed_sources,
    }
    with zipfile.ZipFile(output, "a", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(
            "nevernether-test1-source-lock.json",
            json.dumps(source_lock, indent=2, ensure_ascii=False) + "\n",
        )


def build(
    sources: dict[str, Path],
    output: Path,
    *,
    require_pinned: bool,
) -> None:
    observed_sources = validate_sources(sources, require_pinned=require_pinned)

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

    inject_source_lock(output, observed_sources)
    run(FINGERPRINT_TOOL, "--input", output, "--inject")

    digest = sha256(output)
    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")

    print("[NeverFolia][NeverNether TEST1] BUILD OK")
    print(f"  pack: {output}")
    print(f"  sha256: {digest}")
    print(f"  checksum: {checksum_path}")
    for item in observed_sources:
        print(f"  source/{item['key']}: {item['sha256']} ({item['hash_status']})")


def self_test() -> None:
    manifest = load_source_manifest()
    for key in SOURCE_KEYS:
        source = manifest["sources"].get(key)
        if not isinstance(source, dict):
            raise SystemExit(f"TEST1 SELF-TEST: source manifest missing {key}")
        if not source.get("filename") or not source.get("version"):
            raise SystemExit(f"TEST1 SELF-TEST: source manifest incomplete for {key}")

    pinned_monument = manifest["sources"]["better_monuments"].get("sha256")
    if pinned_monument != "c76cd5ab549974b051a352a633abd2f78a916acc40392bc53ba0581c3116a8c9":
        raise SystemExit("TEST1 SELF-TEST: Better Monuments source hash changed unexpectedly")

    run(STRUCTURE_IMPORTER, "--self-test")
    run(STRUCTURE_HARDENER, "--self-test")
    run(FINGERPRINT_TOOL, "--self-test")
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
    parser.add_argument(
        "--require-pinned-sources",
        action="store_true",
        help="Refuse the build unless every required source has a pinned SHA-256 in the manifest",
    )
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
    build(sources, args.output, require_pinned=args.require_pinned_sources)


if __name__ == "__main__":
    main()
