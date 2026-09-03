#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "worldgen-spec/never-overworld-structures.json"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld structures] {message}")


def validate_deep_rule(name: str, rule: dict, expected_range: list[int]) -> None:
    if not rule.get("deep_extension_enabled"):
        fail(f"{name} deep extension is not enabled")
    if rule.get("upper_vanilla_placement_preserved") is not False:
        fail(f"{name} upper vanilla placement must be disabled in VANILLA_FLOODED")
    hard = rule.get("deep_hard_y")
    if hard != expected_range:
        fail(f"{name} deep_hard_y={hard!r}, expected {expected_range!r}")
    if hard[0] < -512 or hard[1] > -64:
        fail(f"{name} deep range escaped custom deep domain: {hard}")


def main() -> None:
    data = json.loads(SPEC.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("worldgen_id") != "NR-DEV-1":
        fail("invalid schema/worldgen_id")

    rules = data.get("global_rules", {})
    expected = {
        "dimension_min_y": -512,
        "dimension_max_y": 511,
        "vanilla_upper_from_y": -64,
        "flood_level_y": 128,
        "deterministic_candidate_rejection": True,
        "never_search_nearby_on_failure": True,
        "never_generate_neighbor_chunks": True,
        "generation_time_neighbor_chunk_reads": False,
        "generation_time_cross_chunk_writes": False,
        "fast_locate_generates_chunks": False,
    }
    for key, value in expected.items():
        if rules.get(key) != value:
            fail(f"global rule drift: {key}={rules.get(key)!r}, expected {value!r}")

    baseline = data.get("vanilla_baseline", {})
    vanilla = set(baseline.get("structures", []))
    for required in ("minecraft:mineshaft", "minecraft:trial_chambers", "minecraft:ancient_city"):
        if required not in vanilla:
            fail(f"vanilla baseline missing {required}")
    if "minecraft:stronghold" in vanilla:
        fail("minecraft:stronghold must not be in NeverOverworld baseline")
    disabled = set(baseline.get("disabled_structures", []))
    if "minecraft:stronghold" not in disabled:
        fail("minecraft:stronghold must be explicitly disabled")

    special = baseline.get("special_rules", {})
    stronghold = special.get("stronghold", {})
    if stronghold.get("enabled") is not False:
        fail("stronghold special rule must be enabled=false")
    validate_deep_rule("mineshaft", special.get("mineshaft", {}), [-448, -112])
    validate_deep_rule("trial_chambers", special.get("trial_chambers", {}), [-320, -96])

    flood = baseline.get("flood_surface_policy", {})
    if flood.get("minimum_dry_surface_y") != 129 or flood.get("reject_submerged_surface_starts") is not True:
        fail("flood surface structure policy drifted")
    dry_only = set(flood.get("dry_land_only", []))
    for required in (
        "minecraft:village_plains",
        "minecraft:village_desert",
        "minecraft:village_savanna",
        "minecraft:village_snowy",
        "minecraft:village_taiga",
        "minecraft:woodland_mansion",
        "minecraft:pillager_outpost",
        "minecraft:swamp_hut",
    ):
        if required not in dry_only:
            fail(f"dry-land-only flooded structure policy missing {required}")
    if dry_only & set(flood.get("water_native_allowed", [])):
        fail("structure cannot be both dry-only and water-native")

    profiles = data.get("vertical_profiles", {})
    groups = data.get("placement_groups", {})
    if set(groups) != {"deep_major", "deep_medium", "deep_ambient"}:
        fail(f"unexpected placement groups: {sorted(groups)}")

    structure_ids: set[str] = set()
    salts: set[int] = set()
    total = 0
    for group_name, group in groups.items():
        placement = group.get("placement", {})
        if placement.get("type") != "minecraft:random_spread":
            fail(f"{group_name} is not random_spread")
        spacing = placement.get("spacing")
        separation = placement.get("separation")
        salt = placement.get("salt")
        if not isinstance(spacing, int) or not isinstance(separation, int) or spacing <= separation or separation < 1:
            fail(f"{group_name} invalid spacing/separation")
        if not isinstance(salt, int) or salt in salts:
            fail(f"{group_name} invalid/duplicate salt")
        salts.add(salt)
        structures = group.get("structures", [])
        if not structures:
            fail(f"{group_name} has no structures")
        for entry in structures:
            sid = entry.get("id")
            profile = entry.get("vertical_profile")
            if not isinstance(sid, str) or not sid.startswith("neverfolia:"):
                fail(f"custom structure must use neverfolia namespace: {sid!r}")
            if sid in structure_ids:
                fail(f"duplicate structure id: {sid}")
            structure_ids.add(sid)
            if profile not in profiles:
                fail(f"{sid} references missing vertical profile {profile!r}")
            if not isinstance(entry.get("weight"), int) or entry["weight"] < 1:
                fail(f"{sid} invalid weight")
            total += 1

    for name, profile in profiles.items():
        hard = profile.get("hard_y")
        if not isinstance(hard, list) or len(hard) != 2 or hard[0] >= hard[1]:
            fail(f"profile {name} invalid hard_y")
        if hard[0] < -512 or hard[1] > 128:
            fail(f"profile {name} escaped NR-DEV-1 placement domain: {hard}")

    reject = data.get("candidate_rejection", {})
    for key in (
        "sample_only_candidate_chunk",
        "sample_absolute_noise_without_chunk_loads",
        "candidate_failure_consumes_no_neighbor_state",
    ):
        if reject.get(key) is not True:
            fail(f"candidate rejection invariant missing: {key}")

    locate = data.get("fast_locate", {})
    if locate.get("native") is not True or locate.get("generates_chunks") is not False:
        fail("fast locate must be native and non-generating")
    if locate.get("terrain_precheck") != "seed_and_absolute_noise_only":
        fail("fast locate terrain precheck must be absolute-noise-only")

    print("[NeverFolia][NeverOverworld structures] NR-DEV-1 FIELD-R1 STRUCTURE CONTRACT OK")
    print(f"  vanilla baseline structures: {len(vanilla)}")
    print("  stronghold/end portal: disabled")
    print("  mineshaft: deep-only Y=-448..-112")
    print("  trial chambers: deep-only Y=-320..-96")
    print(f"  custom native structure/dungeon ids: {total}")
    print("  placement: deterministic candidate grid, no neighbor generation")
    print("  locate: native candidate-grid search, generates_chunks=false")


if __name__ == "__main__":
    main()
