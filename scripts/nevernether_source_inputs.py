"""Archive/structure dependency inspection; no external assets embedded here.

This is a source-level preflight, not Minecraft's registry codec or a runtime
worldgen test. Absent vanilla resources are delegated to the server and recorded.
"""
from __future__ import annotations

from collections import Counter, deque
import gzip
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

TARGET_FORMAT = (107, 1)
MAX_ENTRY = 32 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
RESOURCE_ID = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")
LEGACY_DIRS = {"structures": "structure", "loot_tables": "loot_table",
               "functions": "function", "predicates": "predicate",
               "item_modifiers": "item_modifier"}
PROVIDED_TAG = "#repurposed_structures:has_structure/monuments/nether"


def safe_path(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if (not name or "\\" in name or p.is_absolute() or ".." in p.parts
            or ":" in name or str(p) == "."):
        raise ValueError(f"Unsafe archive/resource path: {name!r}")
    return p


def json_object(raw: bytes, label: str) -> dict:
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {label}")
    return value


def version(value: object, *, upper: bool = False) -> tuple[int, int]:
    if type(value) is int and value >= 0:
        return value, 2147483647 if upper else 0
    if (isinstance(value, list) and len(value) == 2
            and all(type(n) is int and n >= 0 for n in value)):
        return tuple(value)
    raise ValueError(f"Invalid pack version: {value!r}")


def format_bounds(entry: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    if "min_format" in entry or "max_format" in entry:
        lo = version(entry["min_format"])
        hi = version(entry["max_format"], upper=True)
    else:
        formats = entry.get("formats", entry.get("supported_formats", entry.get("pack_format")))
        if isinstance(formats, dict):
            lo = version(formats["min_inclusive"])
            hi = version(formats["max_inclusive"], upper=True)
        elif isinstance(formats, list) and len(formats) == 2:
            lo, hi = version(formats[0]), version(formats[1], upper=True)
        else:
            lo, hi = version(formats), version(formats, upper=True)
    if lo > hi:
        raise ValueError("Reversed pack format range")
    return lo, hi


class Archive:
    """Resolve data-pack overlays in declared order, keeping original resources.

    Legacy directories are not converted here: a singular resource is authoritative
    for 26.2. A legacy-only dependency is a blocker, never silently upgraded.
    """
    def __init__(self, path: Path, target: tuple[int, int] = TARGET_FORMAT):
        self.path = path
        self.target = target
        self.entries: dict[PurePosixPath, bytes] = {}
        self.provenance: dict[PurePosixPath, str] = {}
        self.active_overlays: list[str] = []
        self.compatibility_changes: list[dict] = []
        self.decoded: dict[PurePosixPath, dict] = {}
        with zipfile.ZipFile(path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            if len(infos) > 50000 or sum(i.file_size for i in infos) > MAX_ARCHIVE:
                raise ValueError("Source archive exceeds inspection limits")
            seen: set[PurePosixPath] = set()
            for info in infos:
                p = safe_path(info.filename)
                if p in seen:
                    raise ValueError(f"Duplicate ZIP path: {p}")
                seen.add(p)
                if info.file_size > MAX_ENTRY or info.flag_bits & 1:
                    raise ValueError(f"Oversized or encrypted ZIP entry: {p}")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError(f"Symlink ZIP entry: {p}")
            roots = [p.parent for p in seen if p.name == "pack.mcmeta"]
            if len(roots) != 1:
                raise ValueError(f"Expected exactly one pack.mcmeta, found {len(roots)}")
            root = roots[0]
            prefix = "" if str(root) == "." else str(root) + "/"
            raw: dict[PurePosixPath, bytes] = {}
            for info in infos:
                # Reading verifies CRCs; nothing is extracted to an input directory.
                payload = zf.read(info)
                if info.filename.startswith(prefix):
                    raw[safe_path(info.filename[len(prefix):])] = payload
        self.metadata = json_object(raw[PurePosixPath("pack.mcmeta")], "pack.mcmeta")
        lo, hi = format_bounds(self.metadata["pack"])
        if not lo <= target <= hi:
            raise ValueError(f"Archive does not declare support for format {target}: {lo}..{hi}")
        # Preserve root files and root data only; do not include inactive overlays.
        for p, payload in raw.items():
            if len(p.parts) == 1 or p.parts[0] == "data":
                self.entries[p], self.provenance[p] = payload, str(p)
        for item in self.metadata.get("overlays", {}).get("entries", []):
            directory = safe_path(item["directory"])
            lo, hi = format_bounds(item)
            if lo <= target <= hi:
                self.active_overlays.append(str(directory))
                prefix = str(directory) + "/"
                for p, payload in raw.items():
                    if str(p).startswith(prefix):
                        rel = safe_path(str(p)[len(prefix):])
                        if rel.parts[0] == "data":
                            self.entries[rel], self.provenance[rel] = payload, str(p)

    def decode(self, path: PurePosixPath) -> dict:
        if path not in self.decoded:
            raw = self.entries[path]
            if path.suffix == ".nbt":
                if raw.startswith(b"\x1f\x8b"):
                    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as fh:
                        raw = fh.read(MAX_ENTRY + 1)
                    if len(raw) > MAX_ENTRY:
                        raise ValueError(f"NBT payload too large: {path}")
                spec = importlib.util.spec_from_file_location(
                    "nn_source_nbt", Path(__file__).with_name("hash-never-nether-chunks.py"))
                if spec is None or spec.loader is None:
                    raise RuntimeError("NBT reader unavailable")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                value = module.parse_nbt(raw)
                if not isinstance(value, dict):
                    raise ValueError(f"Expected NBT compound: {path}")
                self.decoded[path] = value
            else:
                self.decoded[path] = json_object(raw, str(path))
        return self.decoded[path]


def resource_path(registry: str, ident: str) -> PurePosixPath:
    ident = ident if ":" in ident else "minecraft:" + ident
    if not RESOURCE_ID.fullmatch(ident):
        raise ValueError(f"Invalid resource id: {ident!r}")
    ns, name = ident.split(":", 1)
    safe_path(name)
    return PurePosixPath("data", ns, registry, name + (".nbt" if registry == "structure" else ".json"))



def apply_server_compatibility(archive: Archive, source_key: str) -> None:
    """Explicit optional mod integrations only. No generic mod-codec deletion.

    These independent empty-pool overrides leave each tower's NBT unchanged;
    the Waystones/Fabric Waystones mini-pieces are not imported on native Folia.
    """
    spec_path = Path(__file__).resolve().parents[1] / "worldgen-spec/never-nether-source-compat.json"
    config = json.loads(spec_path.read_text(encoding="utf-8"))
    for ident, rule in config["optional_mod_pool_overrides"].get(source_key, {}).items():
        if rule["replacement"] != "empty_pool":
            raise ValueError(f"Unknown compatibility override for {ident}")
        path = resource_path("worldgen/template_pool", ident)
        if path not in archive.entries:
            raise ValueError(f"Expected optional-mod pool is missing: {ident}")
        replacement = {"name": ident, "fallback": "minecraft:empty", "elements": [
            {"weight": 1, "element": {"element_type": "minecraft:empty_pool_element"}}
        ]}
        archive.entries[path] = (json.dumps(replacement, indent=2) + "\n").encode()
        archive.decoded.pop(path, None)
        archive.provenance[path] = "neverfolia-authored/optional-mod-pool-override"
        archive.compatibility_changes.append({"resource": str(path), "policy": "empty_optional_mod_pool", "reason": rule["reason"]})


def inspect_dependencies(archive: Archive, structure_ids: list[str] | tuple[str, ...]) -> dict:
    pending = deque()
    selected: set[PurePosixPath] = set()
    queued: set[PurePosixPath] = set()
    external: set[tuple[str, str]] = set()
    missing: set[tuple[str, str, str]] = set()
    blockers: set[tuple[str, str, str]] = set()
    provided: set[tuple[str, str]] = set()
    edges: set[tuple[str, str, str]] = set()
    counts: Counter[str] = Counter()

    def ref(registry: str, ident: str, origin: str, required: bool = True) -> None:
        if not isinstance(ident, str) or not ident:
            raise ValueError(f"Invalid reference in {origin}: {ident!r}")
        path = resource_path(registry, ident)
        canonical = ident if ":" in ident else "minecraft:" + ident
        edges.add((origin, registry, canonical))
        if path in archive.entries:
            if path not in queued:
                queued.add(path)
                pending.append((registry, path))
        elif canonical.startswith("minecraft:"):
            external.add((registry, canonical))
        elif (registry == "tags/worldgen/biome" and "#" + canonical == PROVIDED_TAG
              and "repurposed_structures:monument_nether" in structure_ids):
            provided.add((registry, canonical))
        elif required:
            missing.add((registry, canonical, origin))

    def codec(value: object, kind: str, origin: str) -> None:
        if isinstance(value, str) and ":" in value and not value.startswith("minecraft:"):
            blockers.add((kind, value, origin))

    def walk(value: object, registry: str, origin: str) -> None:
        if isinstance(value, list):
            for child in value:
                walk(child, registry, origin)
            return
        if not isinstance(value, dict):
            return
        for field in ("element_type", "processor_type", "predicate_type"):
            codec(value.get(field), field, origin)
        if registry == "worldgen/structure" and "start_pool" in value:
            ref("worldgen/template_pool", value["start_pool"], origin)
            typ = value.get("type")
            if typ != "repurposed_structures:generic_jigsaw_structure":
                codec(typ, "structure_type", origin)
            biomes = value.get("biomes")
            if isinstance(biomes, str) and biomes.startswith("#"):
                ref("tags/worldgen/biome", biomes[1:], origin)
        if registry == "worldgen/template_pool":
            if isinstance(value.get("fallback"), str):
                ref("worldgen/template_pool", value["fallback"], origin)
            element = value.get("element_type", "")
            if "location" in value and isinstance(value["location"], str):
                ref("structure", value["location"], origin)
            if element == "minecraft:feature_pool_element" and isinstance(value.get("feature"), str):
                ref("worldgen/placed_feature", value["feature"], origin)
            if isinstance(value.get("processors"), str):
                ref("worldgen/processor_list", value["processors"], origin)
        if registry == "structure":
            if isinstance(value.get("pool"), str):
                ref("worldgen/template_pool", value["pool"], origin)
            if isinstance(value.get("LootTable"), str):
                ref("loot_table", value["LootTable"], origin)
            if isinstance(value.get("loot_table"), str):
                ref("loot_table", value["loot_table"], origin)
            # Non-vanilla NBT ids require an explicit runtime adapter, not deletion.
            codec(value.get("id"), "nbt_id", origin)
            codec(value.get("Name"), "palette_or_state", origin)
            if isinstance(value.get("Command"), str) and value["Command"]:
                blockers.add(("embedded_command_requires_review", "command_block", origin))
        if registry == "worldgen/placed_feature":
            if isinstance(value.get("feature"), str):
                ref("worldgen/configured_feature", value["feature"], origin)
            codec(value.get("type"), "placement_type", origin)
        if registry == "worldgen/configured_feature":
            codec(value.get("type"), "feature_type", origin)
            for field in ("feature", "default"):
                if isinstance(value.get(field), str):
                    ref("worldgen/placed_feature", value[field], origin)
        if registry == "worldgen/processor_list" and isinstance(value.get("pillar_processor_list"), str):
            ref("worldgen/processor_list", value["pillar_processor_list"], origin)
        if registry in ("loot_table", "predicate", "item_modifier"):
            typ = value.get("type")
            if typ == "minecraft:loot_table":
                ident = value.get("value", value.get("name"))
                if isinstance(ident, str):
                    ref("loot_table", ident, origin)
            if value.get("function") == "minecraft:set_loot_table" and isinstance(value.get("name"), str):
                ref("loot_table", value["name"], origin)
            if value.get("condition") == "minecraft:reference":
                ref("predicate", value["name"], origin)
            if value.get("function") == "minecraft:reference":
                ref("item_modifier", value["name"], origin)
            for field in ("type", "function", "condition"):
                codec(value.get(field), "loot_" + field, origin)
        if registry.startswith("tags/") and isinstance(value.get("values"), list):
            for member in value["values"]:
                required = True
                if isinstance(member, dict):
                    required = member.get("required", True)
                    member = member.get("id")
                if isinstance(member, str) and member.startswith("#"):
                    ref(registry, member[1:], origin, required)
                elif isinstance(member, str):
                    ref(registry[len("tags/"):], member, origin, required)
        for child in value.values():
            walk(child, registry, origin)

    for sid in sorted(structure_ids):
        ref("worldgen/structure", sid, "approved_structure")
    while pending:
        registry, path = pending.popleft()
        selected.add(path)
        counts[registry] += 1
        value = archive.decode(path)
        if registry == "structure":
            size = value.get("size")
            if (not isinstance(size, list) or len(size) != 3
                    or any(type(n) is not int or n < 0 for n in size)):
                raise ValueError(f"Invalid structure NBT size: {path}")
        walk(value, registry, str(path))
    return {
        "target_data_pack_format": list(archive.target),
        "approved_structure_ids": sorted(structure_ids),
        "active_overlays": archive.active_overlays,
        "compatibility_changes": archive.compatibility_changes,
        "selected_files": [str(p) for p in sorted(selected)],
        "selected_counts": dict(sorted(counts.items())),
        "selected_resource_bytes": sum(len(archive.entries[p]) for p in selected),
        "selected_overlay_files": {str(p): archive.provenance[p] for p in sorted(selected)
                                   if str(p) != archive.provenance[p] and archive.provenance[p] != "neverfolia-authored/optional-mod-pool-override"},
        "external_vanilla_references_unverified": [list(x) for x in sorted(external)],
        "missing_required_references": [list(x) for x in sorted(missing)],
        "unsupported_or_review_required": [list(x) for x in sorted(blockers)],
        "provided_by_neverfolia_hardener": [list(x) for x in sorted(provided)],
        "reference_edges": [list(x) for x in sorted(edges)],
        "source_dependency_preflight_passed": not missing and not blockers,
        "runtime_validated": False,
        "coverage": "Known structure/pool/NBT/processor/feature/loot/biome-tag references; not Minecraft registry validation",
    }


def selected_files(archive: Archive, result: dict) -> dict[PurePosixPath, bytes]:
    if not result["source_dependency_preflight_passed"]:
        raise ValueError("Refusing import: missing dependencies or unsupported runtime content")
    return {PurePosixPath(p): archive.entries[PurePosixPath(p)] for p in result["selected_files"]}
