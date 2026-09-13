#!/usr/bin/env python3
"""Inspect available pinned NeverNether inputs. Exit 2 means a blocked source set.

Produces a source-only report, never a datapack, region edit or asset upload.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from nevernether_source_inputs import Archive, apply_server_compatibility, inspect_dependencies

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "worldgen-sources/never-nether/manifest.json"


def importer():
    spec = importlib.util.spec_from_file_location("nn_source_importer", ROOT / "scripts/build-never-nether-structure-pack.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing structure importer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def audit_sources(directory: Path) -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    module = importer()
    missing, sources, invalid = [], [], []
    approved_count = len(module.APPROVED_IDS)
    found_count = passed_count = 0
    for key, ids in module.APPROVED_BY_SOURCE.items():
        entry = spec["sources"][key]
        path = directory / entry["filename"]
        if not path.is_file():
            missing.append({"key": key, "filename": entry["filename"], "structure_count": len(ids)})
            continue
        record = {"key": key, "filename": path.name, "sha256": digest(path),
                  "size_bytes": path.stat().st_size}
        pinned = entry.get("sha256")
        record["hash_status"] = "pinned_verified" if pinned else "observed_unpinned"
        try:
            if pinned and record["sha256"] != pinned:
                raise ValueError("SHA-256 differs from the pinned source manifest")
            archive = Archive(path)
            record["archive_crc_verified"] = True
            if key in ("structory_towers", "dungeons_and_taverns"):
                raw = inspect_dependencies(archive, ids)
                record["before_source_compatibility"] = {
                    "missing_required_references": raw["missing_required_references"],
                    "unsupported_or_review_required": raw["unsupported_or_review_required"]}
                apply_server_compatibility(archive, key)
            record["source_report"] = inspect_dependencies(archive, ids)
            record["structures"] = [inspect_dependencies(archive, [sid]) for sid in ids]
            found_count += sum(not any(m[0] == "worldgen/structure" and m[1] == sid
                                      for m in result["missing_required_references"])
                               for sid, result in zip(ids, record["structures"]))
            passed_count += sum(result["source_dependency_preflight_passed"] for result in record["structures"])
        except Exception as exc:  # Untrusted archive failures cannot become a passing report.
            record["error"] = f"{type(exc).__name__}: {exc}"
            invalid.append(key)
        sources.append(record)
    extras = []
    # Metadata/hashes only: Amplified terrain is deliberately not a transformation
    # source; Witch Huts is outside the approved Nether import set.
    for name, reason in (
        ("Amplified_Nether_v1.2.15.zip", "excluded_separate_terrain_generator"),
        ("Repurposed_Structures-Better_Witch_Huts_v5.zip", "excluded_overworld_content"),
        ("Repurposed_Structures-Better_Witch_Huts_v5 (1).zip", "excluded_overworld_content"),
    ):
        path = directory / name
        if path.is_file():
            extras.append({"filename": name, "sha256": digest(path), "size_bytes": path.stat().st_size, "reason": reason})
    hashes: dict[str, list[str]] = {}
    for item in extras:
        hashes.setdefault(item["sha256"], []).append(item["filename"])
    complete = not missing and not invalid and passed_count == approved_count
    return {
        "schema": 1, "audit": "nevernether-source-preflight-r3", "worldgen_id": spec["worldgen_id"],
        "source_manifest": str(MANIFEST.relative_to(ROOT)), "target_data_pack_format": [107, 1],
        "status": "source_preflight_passed" if complete else "blocked",
        "approved_custom_structure_count": approved_count,
        "supplied_structure_definition_count": found_count,
        "structures_passing_source_dependency_preflight": passed_count,
        "missing_sources": missing, "invalid_sources": invalid, "sources": sources,
        "excluded_inputs": extras, "identical_duplicate_inputs": [names for names in hashes.values() if len(names) > 1],
        "release_ready": False, "runtime_validated": False,
        "assets_written_or_uploaded": False,
        "interpretation": [
            "Source preflight is not a Minecraft registry boot, NBT data-fixer or worldgen test.",
            "Absent vanilla references are recorded but require validation against the exact server.",
            "No third-party content is committed to the repository by this tool.",
            "Passing structures are not reported as installed or tested in a world.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.source_dir.is_dir():
        parser.error("Source directory does not exist")
    if args.output.suffix.lower() != ".json":
        parser.error("Output must be a .json report, not a source archive")
    report = audit_sources(args.source_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Source preflight: {report['status']}; supplied {report['supplied_structure_definition_count']}/20; "
          f"dependency preflight passed {report['structures_passing_source_dependency_preflight']}/20")
    print(f"Report: {args.output}")
    return 0 if report["status"] == "source_preflight_passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
