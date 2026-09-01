#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PLACEMENT_SPEC = ROOT / "worldgen-spec" / "never-nether-structures.json"

APPROVED_BY_SOURCE: dict[str, tuple[str, ...]] = {
    "hearths": (
        "hearths:crimson_tower",
        "hearths:warped_tower",
        "hearths:netherrack_spiral",
    ),
    "dungeons_and_taverns": (
        "nova_structures:nether_port",
        "nova_structures:nether_keep",
        "nova_structures:hamlet",
        "nova_structures:piglin_outstation",
        "nova_structures:piglin_donjon",
        "nova_structures:sealing_halls",
        "nova_structures:nether_skeleton_tower_fort",
        "nova_structures:nether_skeleton_tower_warped",
        "nova_structures:nether_skeleton_tower_crimson",
        "nova_structures:nether_skeleton_tower_soul",
        "nova_structures:piglin_camp",
        "nova_structures:piglin_camp_collony",
    ),
    "explorify": ("explorify:black_spiral",),
    "structory_towers": (
        "structory_towers:nether/fortress_tower",
        "structory_towers:nether/strange_outpost",
        "structory_towers:nether/warped_outpost",
    ),
    "better_monuments": ("repurposed_structures:monument_nether",),
}

REQUIRED_SOURCES = tuple(APPROVED_BY_SOURCE)
APPROVED_IDS = {item for values in APPROVED_BY_SOURCE.values() for item in values}

# Any third-party terrain/dimension/placement definition is deliberately excluded.
BANNED_RESOURCE_PREFIXES = (
    "dimension/",
    "dimension_type/",
    "worldgen/noise_settings/",
    "worldgen/density_function/",
    "worldgen/noise/",
    "worldgen/structure_set/",
)

# Runtime code keys NeverNether placement from these aliases. Never change these
# silently after a worldgen release has shipped.
def alias_id(structure_id: str) -> str:
    namespace, path = structure_id.split(":", 1)
    safe = f"{namespace}__{path}".replace("/", "__")
    return f"neverfolia:never_nether/start/{safe}"


def resource_path(resource_id: str, registry_dir: str, suffix: str = ".json") -> PurePosixPath:
    namespace, path = resource_id.split(":", 1)
    return PurePosixPath("data") / namespace / registry_dir / f"{path}{suffix}"


def structure_path(structure_id: str) -> PurePosixPath:
    return resource_path(structure_id, "worldgen/structure")


def pool_path(pool_id: str) -> PurePosixPath:
    return resource_path(pool_id, "worldgen/template_pool")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def read_json_bytes(payload: bytes, label: str) -> dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - include filename in pack builder error
        raise SystemExit(f"Invalid JSON in {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Expected JSON object in {label}")
    return value


@dataclass(frozen=True)
class SourceArchive:
    key: str
    path: Path
    sha256: str


class PackFiles:
    def __init__(self) -> None:
        self.files: dict[PurePosixPath, bytes] = {}

    def put(self, path: PurePosixPath | str, payload: bytes) -> None:
        p = PurePosixPath(path)
        if p.is_absolute() or ".." in p.parts:
            raise SystemExit(f"Unsafe pack path: {p}")
        self.files[p] = payload

    def get(self, path: PurePosixPath | str) -> bytes | None:
        return self.files.get(PurePosixPath(path))

    def remove(self, path: PurePosixPath | str) -> None:
        self.files.pop(PurePosixPath(path), None)

    def write_zip(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(self.files, key=str):
                zf.writestr(str(path), self.files[path])


def find_pack_root(zf: zipfile.ZipFile, archive: Path) -> PurePosixPath:
    candidates: list[PurePosixPath] = []
    for raw in zf.namelist():
        p = PurePosixPath(raw)
        if p.name == "pack.mcmeta":
            candidates.append(p.parent)
    if not candidates:
        raise SystemExit(f"{archive.name}: pack.mcmeta not found")
    candidates.sort(key=lambda p: (len(p.parts), str(p)))
    return candidates[0]


def normalized_entries(archive: Path) -> dict[PurePosixPath, bytes]:
    with zipfile.ZipFile(archive) as zf:
        root = find_pack_root(zf, archive)
        prefix = "" if str(root) == "." else f"{root.as_posix().rstrip('/')}/"
        result: dict[PurePosixPath, bytes] = {}
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if prefix and not name.startswith(prefix):
                continue
            rel = name[len(prefix):] if prefix else name
            p = PurePosixPath(rel)
            if not p.parts or ".." in p.parts:
                continue
            result[p] = zf.read(info)
        return result


def is_structure_definition(path: PurePosixPath) -> bool:
    parts = path.parts
    return len(parts) >= 5 and parts[0] == "data" and parts[2:4] == ("worldgen", "structure") and path.suffix == ".json"


def id_from_structure_path(path: PurePosixPath) -> str:
    namespace = path.parts[1]
    rel = PurePosixPath(*path.parts[4:]).with_suffix("").as_posix()
    return f"{namespace}:{rel}"


def resource_tail(path: PurePosixPath) -> str | None:
    if len(path.parts) < 3 or path.parts[0] != "data":
        return None
    return PurePosixPath(*path.parts[2:]).as_posix()


def copy_allowed_source_files(pack: PackFiles, source: SourceArchive) -> None:
    entries = normalized_entries(source.path)
    approved_for_source = set(APPROVED_BY_SOURCE[source.key])

    for path, payload in entries.items():
        if not path.parts or path.parts[0] != "data":
            continue

        tail = resource_tail(path)
        if tail is None:
            continue
        if any(tail.startswith(prefix) for prefix in BANNED_RESOURCE_PREFIXES):
            continue

        # Only explicitly approved structure definitions are accepted.
        if is_structure_definition(path):
            sid = id_from_structure_path(path)
            if sid not in approved_for_source:
                continue
            pack.put(path, payload)
            continue

        namespace = path.parts[1] if len(path.parts) > 1 else ""

        # D&T's Nether Keep intentionally depends on its minecraft:nether_fortress
        # jigsaw assets. Do not copy unrelated minecraft namespace changes.
        if namespace == "minecraft":
            allowed_minecraft_dependency = (
                "nether_fortress" in path.parts
                and (
                    tail.startswith("worldgen/template_pool/")
                    or tail.startswith("structure/")
                    or tail.startswith("structures/")
                    or tail.startswith("worldgen/processor_list/")
                    or tail.startswith("loot_table/")
                    or tail.startswith("loot_tables/")
                )
            )
            if not allowed_minecraft_dependency:
                continue

        # Custom namespace data is inert unless referenced by an approved structure.
        # Copying it keeps the first TEST1 importer robust while structure sets and
        # all dimension/terrain overrides remain excluded above.
        pack.put(path, payload)


def copy_core(pack: PackFiles, core: Path) -> None:
    entries = normalized_entries(core)
    for path, payload in entries.items():
        pack.put(path, payload)


def sanitize_processor_lists(pack: PackFiles) -> int:
    """Remove processor entries requiring non-vanilla runtime processor codecs.

    The Better Monuments compatibility pack references Repurposed Structures custom
    processor types. TEST1 intentionally degrades those visual processors rather than
    requiring the Repurposed Structures mod at runtime.
    """
    changed = 0
    for path in list(pack.files):
        tail = resource_tail(path)
        if not tail or not tail.startswith("worldgen/processor_list/") or path.suffix != ".json":
            continue
        value = read_json_bytes(pack.files[path], str(path))
        processors = value.get("processors")
        if not isinstance(processors, list):
            continue
        filtered = []
        for processor in processors:
            if not isinstance(processor, dict):
                filtered.append(processor)
                continue
            ptype = processor.get("processor_type") or processor.get("type")
            if isinstance(ptype, str) and ":" in ptype and not ptype.startswith("minecraft:"):
                changed += 1
                continue
            filtered.append(processor)
        if filtered != processors:
            value["processors"] = filtered
            pack.put(path, json_bytes(value))
    return changed


def rewrite_approved_structures(pack: PackFiles, placement: dict) -> list[dict]:
    profiles: dict[str, dict] = placement["vertical_profiles"]
    entries_by_id: dict[str, dict] = {}
    for group_name, group in placement["placement_groups"].items():
        for item in group["structures"]:
            copied = dict(item)
            copied["group"] = group_name
            entries_by_id[item["id"]] = copied

    rewritten: list[dict] = []
    for sid in sorted(APPROVED_IDS):
        spath = structure_path(sid)
        payload = pack.get(spath)
        if payload is None:
            raise SystemExit(f"Required approved structure missing after import: {sid} ({spath})")
        structure = read_json_bytes(payload, str(spath))

        source_pool = structure.get("start_pool")
        if not isinstance(source_pool, str) or ":" not in source_pool:
            raise SystemExit(f"{sid}: expected string start_pool, got {source_pool!r}")

        source_pool_path = pool_path(source_pool)
        source_pool_payload = pack.get(source_pool_path)
        if source_pool_payload is None:
            raise SystemExit(f"{sid}: start pool {source_pool} missing at {source_pool_path}")

        alias = alias_id(sid)
        alias_path = pool_path(alias)
        pack.put(alias_path, source_pool_payload)

        # All approved external structures use the native jigsaw codec in NeverNether.
        # The Nether Monument compatibility definition is converted away from its
        # Repurposed Structures custom structure codec here.
        structure["type"] = "minecraft:jigsaw"
        structure["start_pool"] = alias
        structure.pop("project_start_to_heightmap", None)

        spec_entry = entries_by_id[sid]
        profile_name = spec_entry["vertical_profile"]
        profile = profiles[profile_name]
        preferred_min = int(profile["preferred_y"][0])
        # Placeholder only. NeverFolia's native placement hook resolves terrain-aware Y.
        structure["start_height"] = {"absolute": preferred_min}

        # Custom compat-only keys which are not part of vanilla JigsawStructure.
        for key in (
            "valid_biome_radius_check",
            "cannot_spawn_in_liquid",
            "min_height_limit",
            "max_height_limit",
        ):
            structure.pop(key, None)

        pack.put(spath, json_bytes(structure))
        rewritten.append(
            {
                "id": sid,
                "group": spec_entry["group"],
                "profile": profile_name,
                "source_start_pool": source_pool,
                "neverfolia_start_pool": alias,
            }
        )
    return rewritten


def write_structure_sets(pack: PackFiles, placement: dict) -> None:
    for group_name, group in placement["placement_groups"].items():
        structures = [
            {"structure": entry["id"], "weight": entry["weight"]}
            for entry in group["structures"]
        ]
        value = {
            "structures": structures,
            "placement": group["placement"],
        }
        path = resource_path(
            f"neverfolia:never_nether/{group_name}",
            "worldgen/structure_set",
        )
        pack.put(path, json_bytes(value))


def validate_output(pack: PackFiles, placement: dict) -> None:
    for path, payload in pack.files.items():
        if path.suffix == ".json":
            read_json_bytes(payload, str(path))

    for sid in APPROVED_IDS:
        structure = read_json_bytes(pack.files[structure_path(sid)], sid)
        if structure.get("type") != "minecraft:jigsaw":
            raise SystemExit(f"{sid}: integration output is not native minecraft:jigsaw")
        expected_alias = alias_id(sid)
        if structure.get("start_pool") != expected_alias:
            raise SystemExit(f"{sid}: start_pool alias mismatch")
        if pool_path(expected_alias) not in pack.files:
            raise SystemExit(f"{sid}: aliased start pool is missing")

    # Third-party structure sets must never survive the import.
    for path in pack.files:
        tail = resource_tail(path)
        if not tail or not tail.startswith("worldgen/structure_set/"):
            continue
        if len(path.parts) < 2 or path.parts[1] != "neverfolia":
            raise SystemExit(f"Third-party structure_set survived import: {path}")

    expected_sets = set(placement["placement_groups"])
    found_sets = {
        path.stem
        for path in pack.files
        if len(path.parts) >= 6
        and path.parts[:4] == ("data", "neverfolia", "worldgen", "structure_set")
        and path.parts[4] == "never_nether"
        and path.suffix == ".json"
    }
    if found_sets != expected_sets:
        raise SystemExit(f"NeverNether structure_set mismatch: {sorted(found_sets)} != {sorted(expected_sets)}")


def build(
    core: Path,
    sources: dict[str, Path],
    output: Path,
) -> None:
    missing = [key for key in REQUIRED_SOURCES if key not in sources]
    if missing:
        raise SystemExit(f"Missing required source archive(s): {', '.join(missing)}")

    placement = json.loads(PLACEMENT_SPEC.read_text(encoding="utf-8"))
    pack = PackFiles()
    copy_core(pack, core)

    source_records: list[SourceArchive] = []
    for key in REQUIRED_SOURCES:
        path = sources[key]
        if not path.is_file():
            raise SystemExit(f"Source archive not found: {key}={path}")
        record = SourceArchive(key=key, path=path, sha256=sha256(path))
        source_records.append(record)
        copy_allowed_source_files(pack, record)

    removed_processors = sanitize_processor_lists(pack)
    rewritten = rewrite_approved_structures(pack, placement)
    write_structure_sets(pack, placement)

    integration_manifest = {
        "id": "NN-DEV-1-structures-test1",
        "minecraft": "26.2",
        "placement_profile": placement["profile"],
        "source_archives": [
            {"key": item.key, "filename": item.path.name, "sha256": item.sha256}
            for item in source_records
        ],
        "approved_structure_count": len(rewritten),
        "approved_structures": rewritten,
        "removed_non_minecraft_processor_entries": removed_processors,
        "runtime_external_mod_dependency": False,
        "third_party_structure_sets_imported": False,
    }
    pack.put("nevernether-structure-integration-manifest.json", json_bytes(integration_manifest))
    validate_output(pack, placement)
    pack.write_zip(output)

    print(f"Built {output}")
    print(f"  approved structures: {len(rewritten)}")
    print(f"  files: {len(pack.files)}")
    print(f"  removed custom runtime processor entries: {removed_processors}")


def fake_pool(name: str) -> dict:
    return {
        "name": name,
        "fallback": "minecraft:empty",
        "elements": [],
    }


def create_synthetic_source(path: Path, key: str, ids: Iterable[str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "pack.mcmeta",
            json.dumps({"pack": {"description": f"synthetic {key}", "pack_format": 107}}),
        )
        for sid in ids:
            namespace, resource = sid.split(":", 1)
            pool = f"{namespace}:synthetic/{resource}"
            structure = {
                "type": "minecraft:jigsaw",
                "biomes": "#minecraft:is_nether",
                "step": "surface_structures",
                "spawn_overrides": {},
                "terrain_adaptation": "none",
                "start_pool": pool,
                "size": 1,
                "start_height": {"absolute": 32},
                "max_distance_from_center": 32,
                "use_expansion_hack": False,
            }
            zf.writestr(str(structure_path(sid)), json.dumps(structure))
            zf.writestr(str(pool_path(pool)), json.dumps(fake_pool(pool)))

        # Prove the importer rejects third-party placement and terrain overrides.
        zf.writestr(
            f"data/{key}/worldgen/structure_set/should_not_survive.json",
            json.dumps({"structures": [], "placement": {}}),
        )
        zf.writestr(
            "data/minecraft/worldgen/noise_settings/nether.json",
            json.dumps({"synthetic_bad_override": True}),
        )


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="nevernether-structure-selftest-") as tmp_raw:
        tmp = Path(tmp_raw)
        core = tmp / "core.zip"
        # Minimal core marker; source's attempted nether noise override must not replace it.
        with zipfile.ZipFile(core, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("pack.mcmeta", json.dumps({"pack": {"description": "core", "pack_format": 107}}))
            zf.writestr(
                "data/minecraft/worldgen/noise_settings/nether.json",
                json.dumps({"neverfolia_core_marker": True}),
            )

        sources: dict[str, Path] = {}
        for key, ids in APPROVED_BY_SOURCE.items():
            archive = tmp / f"{key}.zip"
            create_synthetic_source(archive, key, ids)
            sources[key] = archive

        output = tmp / "integration.zip"
        build(core, sources, output)

        with zipfile.ZipFile(output) as zf:
            noise = json.loads(zf.read("data/minecraft/worldgen/noise_settings/nether.json"))
            if noise != {"neverfolia_core_marker": True}:
                raise SystemExit("SELF-TEST: source terrain override replaced NeverNether Core")
            names = set(zf.namelist())
            if any("should_not_survive" in name for name in names):
                raise SystemExit("SELF-TEST: third-party structure set survived")
            manifest = json.loads(zf.read("nevernether-structure-integration-manifest.json"))
            if manifest["approved_structure_count"] != 20:
                raise SystemExit("SELF-TEST: expected exactly 20 approved custom structures")

    print("[NeverFolia][NeverNether structures] SELF-TEST OK")


def parse_source(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("source must use key=/path/to/archive.zip")
    key, value = raw.split("=", 1)
    if key not in APPROVED_BY_SOURCE:
        raise argparse.ArgumentTypeError(
            f"unknown source key {key!r}; expected one of {', '.join(REQUIRED_SOURCES)}"
        )
    return key, Path(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the licensing-safe NeverNether TEST1 structure integration pack"
    )
    parser.add_argument("--core", type=Path, help="NeverNether Core ZIP")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        type=parse_source,
        metavar="KEY=ZIP",
        help="Exact third-party source archive; repeat for each required source",
    )
    parser.add_argument("--output", type=Path, help="Output integration ZIP")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    if args.core is None or args.output is None:
        parser.error("--core and --output are required unless --self-test is used")
    sources = dict(args.source)
    if len(sources) != len(args.source):
        parser.error("duplicate --source key")
    build(args.core, sources, args.output)


if __name__ == "__main__":
    main()
