#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "worldgen-spec" / "never-nether.json"
STRUCTURES_SPEC = ROOT / "worldgen-spec" / "never-nether-structures.json"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether spec] {message}")


def require_range(name: str, value: object, *, positive: bool = True) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        fail(f"{name} must be a two-element array")
    lo, hi = value
    if not isinstance(lo, int) or not isinstance(hi, int):
        fail(f"{name} values must be integers")
    if lo > hi:
        fail(f"{name} must satisfy min <= max, got {value}")
    if positive and (lo <= 0 or hi <= 0):
        fail(f"{name} values must be positive, got {value}")
    return lo, hi


def inclusive_size(lo: int, hi: int) -> int:
    return hi - lo + 1


def validate_core_spec(data: dict) -> tuple[int, int, dict, dict]:
    if data.get("worldgen_version") != "NN-DEV-1":
        fail("worldgen_version must currently be NN-DEV-1")

    dim = data["dimension"]
    min_y = dim["min_y"]
    height = dim["height"]
    max_y = min_y + height - 1

    if min_y != -128:
        fail(f"dimension.min_y must be -128, got {min_y}")
    if height != 1024:
        fail(f"dimension.height must be 1024, got {height}")
    if max_y != 895:
        fail(f"dimension max Y must resolve to 895, got {max_y}")

    body = dim["generated_body"]
    roof = dim["roof_construction_zone"]

    if (body["min_y"], body["max_y"]) != (-128, 383):
        fail(f"generated body must be -128..383, got {body}")
    if inclusive_size(body["min_y"], body["max_y"]) != 512:
        fail("generated body must be exactly 512 blocks tall")

    if (roof["min_y"], roof["max_y"]) != (384, 895):
        fail(f"roof construction zone must be 384..895, got {roof}")
    if inclusive_size(roof["min_y"], roof["max_y"]) != 512:
        fail("roof construction zone must be exactly 512 blocks tall")
    if body["max_y"] + 1 != roof["min_y"]:
        fail("generated body and roof construction zone must be contiguous")
    if roof["max_y"] != max_y:
        fail("roof construction zone must end at the dimension maximum Y")

    lava = dim["primary_lava_level"]
    if lava != 32:
        fail(f"primary lava level must be Y=32, got {lava}")
    if not body["min_y"] <= lava <= body["max_y"]:
        fail("primary lava level must be inside the generated body")

    bands = data["bands"]
    expected_bands = {
        "deep": (-120, -32),
        "lower_lava": (-32, 96),
        "main": (64, 260),
        "upper": (220, 376),
    }
    for name, expected in expected_bands.items():
        band = bands[name]
        actual = (band["min_y"], band["max_y"])
        if actual != expected:
            fail(f"band {name} must be {expected[0]}..{expected[1]}, got {actual[0]}..{actual[1]}")
        if actual[0] < body["min_y"] or actual[1] > body["max_y"]:
            fail(f"band {name} must stay inside the generated body")

    require_range("mega_caverns.width", data["mega_caverns"]["width"])
    require_range("mega_caverns.height", data["mega_caverns"]["height"])
    require_range("mega_caverns.length", data["mega_caverns"]["length"])
    require_range("mega_caverns.regional_spacing", data["mega_caverns"]["regional_spacing"])

    caves = data["secondary_caves"]
    for cave_name, cave in caves.items():
        require_range(f"secondary_caves.{cave_name}.width", cave["width"])
        require_range(f"secondary_caves.{cave_name}.height", cave["height"])
        if "length" in cave:
            require_range(f"secondary_caves.{cave_name}.length", cave["length"])

    for chasm_name, chasm in data["vertical_chasms"].items():
        if not isinstance(chasm, dict):
            continue
        require_range(f"vertical_chasms.{chasm_name}.width", chasm["width"])
        require_range(f"vertical_chasms.{chasm_name}.height", chasm["height"])

    for mass_name in ("small", "medium", "large", "very_large"):
        require_range(f"hanging_masses.{mass_name}", data["hanging_masses"][mass_name])

    magma = data["magma_chambers"]
    for chamber_name in ("ordinary", "large", "giant"):
        chamber = magma[chamber_name]
        require_range(f"magma_chambers.{chamber_name}.width", chamber["width"])
        require_range(f"magma_chambers.{chamber_name}.height", chamber["height"])

    structures = data["structure_density"]
    for key in ("tier_a_distance", "tier_b_distance", "tier_c_distance", "nether_monument_distance"):
        require_range(f"structure_density.{key}", structures[key])

    monument_min, monument_max = structures["nether_monument_distance"]
    _, tier_a_max = structures["tier_a_distance"]
    if monument_min <= tier_a_max:
        fail("Nether Monument minimum distance must be greater than normal Tier A maximum distance")
    if (monument_min, monument_max) != (3000, 4000):
        fail("Nether Monument approved target must remain 3000..4000 blocks")

    det = data["determinism"]
    if det["shared_mutable_rng"] is not False:
        fail("shared mutable RNG must remain disabled")
    if det["neighbor_chunk_generation_for_decisions"] is not False:
        fail("worldgen decisions may not force neighbor chunk generation")
    if det["order_independent"] is not True:
        fail("worldgen must remain order-independent")

    return min_y, max_y, body, roof


def validate_structure_spec(data: dict, core: dict) -> None:
    if data.get("schema") != 1:
        fail("structure manifest schema must be 1")
    if data.get("worldgen_id") != "NN-DEV-1":
        fail("structure manifest worldgen_id must be NN-DEV-1")

    rules = data["global_rules"]
    body = core["dimension"]["generated_body"]
    roof = core["dimension"]["roof_construction_zone"]
    if rules["generated_min_y"] != body["min_y"] or rules["generated_max_y"] != body["max_y"]:
        fail("structure manifest generated body must match core spec")
    if rules["roof_build_min_y"] != roof["min_y"] or rules["roof_build_max_y"] != roof["max_y"]:
        fail("structure manifest roof build zone must match core spec")
    if rules["normal_structures_above_generated_body"] is not False:
        fail("normal structures must remain disabled above the generated body")
    if rules["fast_locate_generates_chunks"] is not False:
        fail("Fast Locate must never generate chunks")
    if rules["deterministic_candidate_rejection"] is not True:
        fail("candidate rejection must remain deterministic")

    baseline = data["vanilla_baseline"]
    required_vanilla = {
        "minecraft:fortress",
        "minecraft:bastion_remnant",
        "minecraft:ruined_portal_nether",
        "minecraft:nether_fossil",
    }
    if set(baseline["structures"]) != required_vanilla:
        fail("vanilla baseline structure set changed unexpectedly")
    if baseline["preserve_source_placement_for_test1"] is not True:
        fail("TEST1 must preserve vanilla 26.2 placement for baseline structures")

    expected_groups = {
        "custom_major": (80, 32, 56447193, (1000, 1600)),
        "custom_medium": (44, 16, 616309338, (500, 900)),
        "custom_ambient": (20, 8, 1845125230, (250, 450)),
        "nether_monument": (192, 64, 1243969273, (3000, 4000)),
    }
    groups = data["placement_groups"]
    if set(groups) != set(expected_groups):
        fail(f"unexpected placement groups: {sorted(groups)}")

    all_ids: list[str] = []
    for name, (spacing, separation, salt, target) in expected_groups.items():
        group = groups[name]
        placement = group["placement"]
        if placement["type"] != "minecraft:random_spread":
            fail(f"{name} placement must be minecraft:random_spread")
        actual = (placement["spacing"], placement["separation"], placement["salt"])
        if actual != (spacing, separation, salt):
            fail(f"{name} placement changed: expected {(spacing, separation, salt)}, got {actual}")
        if spacing <= separation:
            fail(f"{name} spacing must be greater than separation")
        if tuple(group["target_successful_distance_blocks"]) != target:
            fail(f"{name} successful distance target changed")
        for entry in group["structures"]:
            sid = entry["id"]
            if sid in all_ids:
                fail(f"structure {sid} appears in multiple custom placement groups")
            if not isinstance(entry.get("weight"), int) or entry["weight"] <= 0:
                fail(f"structure {sid} must have a positive integer weight")
            if entry.get("vertical_profile") not in data["vertical_profiles"]:
                fail(f"structure {sid} references unknown vertical profile")
            all_ids.append(sid)

    if len(all_ids) != 20:
        fail(f"custom structure manifest must contain 20 non-vanilla structures, got {len(all_ids)}")

    profiles = data["vertical_profiles"]
    for name, profile in profiles.items():
        preferred = require_range(f"vertical_profiles.{name}.preferred_y", profile["preferred_y"], positive=False)
        hard = require_range(f"vertical_profiles.{name}.hard_y", profile["hard_y"], positive=False)
        if hard[0] < body["min_y"] or hard[1] > body["max_y"]:
            fail(f"vertical profile {name} escapes generated body: {hard}")
        if preferred[0] < hard[0] or preferred[1] > hard[1]:
            fail(f"vertical profile {name} preferred range must stay inside hard range")

    monument = groups["nether_monument"]["structures"]
    if len(monument) != 1 or monument[0]["id"] != "repurposed_structures:monument_nether":
        fail("Nether Monument group must contain only repurposed_structures:monument_nether")
    if monument[0].get("requires_large_lava_basin") is not True:
        fail("Nether Monument must require a large lava basin")
    lava_profile = profiles["lava_sea_landmark"]
    if lava_profile.get("lava_surface_y") != 32 or lava_profile.get("requires_lava") is not True:
        fail("Nether Monument lava profile must remain anchored to Y=32")

    rejection = data["candidate_rejection"]
    if rejection["never_search_nearby_on_failure"] is not True:
        fail("candidate rejection may not synchronously search nearby")
    if rejection["never_generate_neighbor_chunks"] is not True:
        fail("candidate rejection may not generate neighbor chunks")
    if rejection["reject_if_bounding_box_min_y_below"] != -123:
        fail("floor structure safety boundary must remain Y=-123 for TEST1")
    if rejection["reject_if_bounding_box_max_y_above"] != 378:
        fail("roof structure safety boundary must remain Y=378 for TEST1")
    if rejection["roof_safety_margin_blocks"] != 5 or rejection["floor_safety_margin_blocks"] != 5:
        fail("structure bedrock safety margins must remain 5 blocks for TEST1")


def main() -> int:
    core = json.loads(SPEC.read_text(encoding="utf-8"))
    structure_spec = json.loads(STRUCTURES_SPEC.read_text(encoding="utf-8"))

    min_y, max_y, body, roof = validate_core_spec(core)
    validate_structure_spec(structure_spec, core)

    lava = core["dimension"]["primary_lava_level"]
    print("[NeverFolia][NeverNether spec] OK")
    print(f"  dimension: Y={min_y}..{max_y} (1024 blocks)")
    print(f"  generated body: Y={body['min_y']}..{body['max_y']} (512 blocks)")
    print(f"  roof construction zone: Y={roof['min_y']}..{roof['max_y']} (512 blocks)")
    print(f"  primary lava level: Y={lava}")
    print("  custom structures: 20 across 4 deterministic placement groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
