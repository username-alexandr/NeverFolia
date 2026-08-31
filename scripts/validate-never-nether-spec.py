#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "worldgen-spec" / "never-nether.json"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether spec] {message}")


def require_range(name: str, value: object) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        fail(f"{name} must be a two-element array")
    lo, hi = value
    if not isinstance(lo, int) or not isinstance(hi, int):
        fail(f"{name} values must be integers")
    if lo <= 0 or hi <= 0 or lo > hi:
        fail(f"{name} must satisfy 0 < min <= max, got {value}")
    return lo, hi


def inclusive_size(lo: int, hi: int) -> int:
    return hi - lo + 1


def main() -> int:
    data = json.loads(SPEC.read_text(encoding="utf-8"))

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
    tier_a_min, tier_a_max = structures["tier_a_distance"]
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

    print("[NeverFolia][NeverNether spec] OK")
    print(f"  dimension: Y={min_y}..{max_y} ({height} blocks)")
    print(f"  generated body: Y={body['min_y']}..{body['max_y']} (512 blocks)")
    print(f"  roof construction zone: Y={roof['min_y']}..{roof['max_y']} (512 blocks)")
    print(f"  primary lava level: Y={lava}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
