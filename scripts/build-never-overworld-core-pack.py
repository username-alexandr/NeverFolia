#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MINECRAFT_VERSION = "26.2"
WORLDGEN_ID = "NR-DEV-1"
DIM_MIN_Y = -512
DIM_HEIGHT = 1024
DIM_MAX_Y = DIM_MIN_Y + DIM_HEIGHT - 1
VANILLA_MIN_Y = -64
DEEP_BLEND_START_Y = -96
DEEP_FOCUS_Y = -180
DEEP_BOTTOM_Y = -440
FLOOD_LEVEL = 128
PACK_FORMAT_MIN = [107, 1]
PACK_FORMAT_MAX = 107
ORE_STAGE_INDEX = 6
NATIVE_GENERATED_FLUID_POLICY = "neverfolia-native-generated-fluid-filter-v1"


def write_json(root: Path, rel: str, value) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add(a, b):
    return {"type": "minecraft:add", "argument1": a, "argument2": b}


def mul(a, b):
    return {"type": "minecraft:mul", "argument1": a, "argument2": b}


def gradient(from_y, to_y, from_value, to_value):
    return {
        "type": "minecraft:y_clamped_gradient",
        "from_y": from_y,
        "to_y": to_y,
        "from_value": from_value,
        "to_value": to_value,
    }


def noise(name: str, xz_scale=1.0, y_scale=1.0):
    return {
        "type": "minecraft:noise",
        "noise": f"neverfolia:never_overworld/{name}",
        "xz_scale": xz_scale,
        "y_scale": y_scale,
    }


def absolute(argument):
    return {"type": "minecraft:abs", "argument": argument}


def choice(input_value, min_inclusive, max_exclusive, when_in_range, when_out_of_range=0.0):
    return {
        "type": "minecraft:range_choice",
        "input": input_value,
        "min_inclusive": min_inclusive,
        "max_exclusive": max_exclusive,
        "when_in_range": when_in_range,
        "when_out_of_range": when_out_of_range,
    }


def placed_ore(feature: str, count: int, min_y: int, max_y: int, distribution: str):
    return {
        "feature": f"minecraft:{feature}",
        "placement": [
            {"type": "minecraft:count", "count": count},
            {"type": "minecraft:in_square"},
            {
                "type": "minecraft:height_range",
                "height": {
                    "type": f"minecraft:{distribution}",
                    "min_inclusive": {"absolute": min_y},
                    "max_inclusive": {"absolute": max_y},
                },
            },
            {"type": "minecraft:biome"},
        ],
    }


def inner_server_jar(server_jar: Path) -> zipfile.ZipFile:
    with zipfile.ZipFile(server_jar) as outer:
        candidates = [
            name
            for name in outer.namelist()
            if name.startswith("META-INF/versions/") and name.endswith("/folia-26.2.jar")
        ]
        if len(candidates) != 1:
            raise SystemExit(
                f"Expected exactly one embedded Folia 26.2 server jar in {server_jar}, got {candidates}"
            )
        payload = outer.read(candidates[0])
    return zipfile.ZipFile(io.BytesIO(payload))


def load_json(zf: zipfile.ZipFile, name: str):
    try:
        return json.loads(zf.read(name))
    except KeyError as exc:
        raise SystemExit(f"Missing vanilla 26.2 resource in built server JAR: {name}") from exc


def build_pack(root: Path, server_jar: Path) -> None:
    if DIM_MAX_Y != 511:
        raise SystemExit(f"NR-DEV-1 height contract drifted: max_y={DIM_MAX_Y}")
    if DIM_MIN_Y % 16 or DIM_HEIGHT % 16:
        raise SystemExit("Minecraft dimension min_y/height must be multiples of 16")

    with inner_server_jar(server_jar) as vanilla:
        dimension_type = load_json(vanilla, "data/minecraft/dimension_type/overworld.json")
        noise_settings = load_json(vanilla, "data/minecraft/worldgen/noise_settings/overworld.json")
        overworld_tag = load_json(vanilla, "data/minecraft/tags/worldgen/biome/is_overworld.json")

        biome_ids = [
            value
            for value in overworld_tag.get("values", [])
            if isinstance(value, str) and value.startswith("minecraft:")
        ]
        if not biome_ids:
            raise SystemExit("Vanilla #minecraft:is_overworld biome tag is empty")

        biomes: dict[str, dict] = {}
        for biome_id in biome_ids:
            name = biome_id.split(":", 1)[1]
            biomes[name] = load_json(vanilla, f"data/minecraft/worldgen/biome/{name}.json")

    if dimension_type.get("min_y") != VANILLA_MIN_Y or dimension_type.get("height") != 384:
        raise SystemExit(
            "Unexpected vanilla 26.2 Overworld dimension contract: "
            f"min_y={dimension_type.get('min_y')} height={dimension_type.get('height')}"
        )
    vanilla_noise = noise_settings.get("noise", {})
    if vanilla_noise.get("min_y") != VANILLA_MIN_Y or vanilla_noise.get("height") != 384:
        raise SystemExit(
            "Unexpected vanilla 26.2 Overworld noise contract: "
            f"min_y={vanilla_noise.get('min_y')} height={vanilla_noise.get('height')}"
        )

    # Preserve the complete vanilla 26.2 Overworld above its old floor and only
    # widen the legal dimension/noise interval. These vanilla inputs are extracted
    # from the exact NeverFolia server JAR used for the test/build.
    dimension_type["min_y"] = DIM_MIN_Y
    dimension_type["height"] = DIM_HEIGHT
    dimension_type["logical_height"] = DIM_HEIGHT
    noise_settings["noise"]["min_y"] = DIM_MIN_Y
    noise_settings["noise"]["height"] = DIM_HEIGHT

    vanilla_final_density = noise_settings["noise_router"]["final_density"]

    # Separate deep density domain. Blend from custom geology back into the exact
    # vanilla final density between Y=-96 and Y=-64 to avoid a hard seam.
    deep_base = add(0.72, mul(noise("deep_mass", 0.55, 0.35), 0.28))
    deep_carving = add(
        choice(noise("deep_cavern", 0.85, 0.55), 0.56, 2.0, -1.25),
        add(
            choice(absolute(noise("deep_tunnel", 1.8, 1.25)), 0.0, 0.105, -0.78),
            choice(absolute(noise("deep_chasm", 1.55, 0.16)), 0.0, 0.055, -0.95),
        ),
    )
    bottom_guard = mul(gradient(DIM_MIN_Y, DIM_MIN_Y + 32, 1.0, 0.0), 2.8)
    deep_density = {
        "type": "minecraft:squeeze",
        "argument": {
            "type": "minecraft:interpolated",
            "argument": mul(0.82, add(add(deep_base, deep_carving), bottom_guard)),
        },
    }
    custom_weight = gradient(DEEP_BLEND_START_Y, VANILLA_MIN_Y, 1.0, 0.0)
    vanilla_weight = gradient(DEEP_BLEND_START_Y, VANILLA_MIN_Y, 0.0, 1.0)
    blended_deep = add(mul(custom_weight, deep_density), mul(vanilla_weight, vanilla_final_density))
    noise_settings["noise_router"]["final_density"] = choice(
        "minecraft:y",
        DIM_MIN_Y,
        VANILLA_MIN_Y,
        blended_deep,
        vanilla_final_density,
    )

    custom_noises = {
        "deep_mass": (-8, [1.0, 0.55]),
        "deep_cavern": (-7, [1.0, 0.60]),
        "deep_tunnel": (-5, [1.0, 0.50]),
        "deep_chasm": (-7, [1.0, 0.45]),
    }

    # Extra placements are strictly below the vanilla range. Existing vanilla
    # ore distributions at Y>=-64 therefore remain unchanged.
    deep_features = {
        "deep_ore_iron": placed_ore("ore_iron", 14, -480, -96, "trapezoid"),
        "deep_ore_gold": placed_ore("ore_gold", 5, -420, -96, "uniform"),
        "deep_ore_redstone": placed_ore("ore_redstone", 7, -480, -96, "uniform"),
        "deep_ore_lapis": placed_ore("ore_lapis", 2, -360, -96, "trapezoid"),
        "deep_ore_diamond": placed_ore("ore_diamond_buried", 4, -480, -128, "uniform"),
        "deep_ore_copper": placed_ore("ore_copper_small", 4, -320, -96, "trapezoid"),
        "deep_tuff": placed_ore("ore_tuff", 3, -480, -96, "uniform"),
    }
    deep_feature_ids = [f"neverfolia:{name}" for name in deep_features]

    # Vanilla generated-fluid feature references are deliberately preserved.
    # NR-DEV-1's Java-side NeverOverworldFluidFeatures policy owns whether these
    # placed features execute. Keeping the exact registry lists here prevents the
    # datapack from silently becoming a second source of fluid-generation policy.
    for name, biome in biomes.items():
        stages = biome.get("features")
        if not isinstance(stages, list) or len(stages) <= ORE_STAGE_INDEX:
            raise SystemExit(f"Overworld biome {name!r} has no ore feature stage {ORE_STAGE_INDEX}")
        if not isinstance(stages[ORE_STAGE_INDEX], list):
            raise SystemExit(f"Overworld biome {name!r} ore feature stage is not a list")
        stages[ORE_STAGE_INDEX].extend(deep_feature_ids)

    write_json(
        root,
        "pack.mcmeta",
        {
            "pack": {
                "description": "NeverOverworld Core TEST1 — NR-DEV-1 / NeverFolia 26.2",
                "min_format": PACK_FORMAT_MIN,
                "max_format": PACK_FORMAT_MAX,
            }
        },
    )
    write_json(root, "data/minecraft/dimension_type/overworld.json", dimension_type)
    write_json(root, "data/minecraft/worldgen/noise_settings/overworld.json", noise_settings)

    for name, (first_octave, amplitudes) in custom_noises.items():
        write_json(
            root,
            f"data/neverfolia/worldgen/noise/never_overworld/{name}.json",
            {"firstOctave": first_octave, "amplitudes": amplitudes},
        )
    for name, feature in deep_features.items():
        write_json(root, f"data/neverfolia/worldgen/placed_feature/{name}.json", feature)
    for name, biome in biomes.items():
        write_json(root, f"data/minecraft/worldgen/biome/{name}.json", biome)

    write_json(
        root,
        "neveroverworld-test1-manifest.json",
        {
            "schema": 1,
            "worldgen_id": WORLDGEN_ID,
            "minecraft": MINECRAFT_VERSION,
            "dimension": "minecraft:overworld",
            "dimension_min_y": DIM_MIN_Y,
            "dimension_max_y": DIM_MAX_Y,
            "dimension_height": DIM_HEIGHT,
            "vanilla_upper_from_y": VANILLA_MIN_Y,
            "deep_blend_start_y": DEEP_BLEND_START_Y,
            "deep_focus_y": DEEP_FOCUS_Y,
            "deep_bottom_y": DEEP_BOTTOM_Y,
            "terrain_mode": "VANILLA_FLOODED",
            "flood_level": FLOOD_LEVEL,
            "flood_phase": "neverfolia-light-barrier-surface-connected-chunk-owned-v3",
            "flood_seed": "minecraft:OCEAN_FLOOR_WG-open-columns-at-y128",
            "sealed_cavity_policy": "remain-dry-without-surface-connected-air-path",
            "underground_fluid_policy": "native-lava-free-aquifer-plus-light-barrier-surface-connected-flood",
            "generated_fluid_feature_policy": NATIVE_GENERATED_FLUID_POLICY,
            "vanilla_fluid_feature_lists": "preserved-from-built-server-jar",
            "upper_generation": "vanilla-26.2-from-built-server-jar",
            "deep_generation": "neverfolia-density-v1",
            "deep_biomes": [
                "minecraft:lush_caves",
                "minecraft:dripstone_caves",
                "minecraft:sulfur_caves",
                "minecraft:deep_dark",
            ],
            "deep_placed_features": list(deep_features),
        },
    )


def build_zip(server_jar: Path, output: Path) -> None:
    server_jar = server_jar.resolve()
    output = output.resolve()
    if not server_jar.is_file():
        raise SystemExit(f"NeverFolia JAR not found: {server_jar}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="neveroverworld-core-") as tmp_raw:
        root = Path(tmp_raw)
        build_pack(root, server_jar)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root).as_posix())
    print("[NeverFolia][NeverOverworld] Core TEST1 pack built")
    print(f"  worldgen: {WORLDGEN_ID}")
    print(f"  range: Y={DIM_MIN_Y}..{DIM_MAX_Y}")
    print(f"  vanilla upper: Y>={VANILLA_MIN_Y}")
    print(f"  fluid features: preserved in pack; filtered natively by NeverFolia")
    print(f"  flood: surface-connected air up to Y={FLOOD_LEVEL}; sealed cavities stay dry")
    print(f"  output: {output}")


def self_test() -> None:
    if DIM_MIN_Y != -512 or DIM_MAX_Y != 511 or DIM_HEIGHT != 1024:
        raise SystemExit("NR-DEV-1 dimension contract self-test failed")
    if VANILLA_MIN_Y != -64 or DEEP_BLEND_START_Y != -96:
        raise SystemExit("NR-DEV-1 vanilla/deep transition self-test failed")
    if FLOOD_LEVEL != 128:
        raise SystemExit("NR-DEV-1 flood contract self-test failed")
    if NATIVE_GENERATED_FLUID_POLICY != "neverfolia-native-generated-fluid-filter-v1":
        raise SystemExit("NR-DEV-1 native generated-fluid policy marker drifted")
    sample = placed_ore("ore_iron", 1, -480, -96, "uniform")
    if sample["placement"][2]["height"]["min_inclusive"]["absolute"] != -480:
        raise SystemExit("NR-DEV-1 placed ore self-test failed")
    density = choice("minecraft:y", -512, -64, 1.0, 0.0)
    if density["type"] != "minecraft:range_choice" or density["input"] != "minecraft:y":
        raise SystemExit("NR-DEV-1 density self-test failed")
    print("[NeverFolia][NeverOverworld] CORE BUILDER NATIVE-FLUID SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build NeverOverworld NR-DEV-1 Core TEST1 pack")
    parser.add_argument("--server-jar", type=Path, help="Built NeverFolia Paperclip JAR")
    parser.add_argument("--output", type=Path, help="Output datapack ZIP")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.server_jar is None or args.output is None:
        parser.error("--server-jar and --output are required unless --self-test is used")
    build_zip(args.server_jar, args.output)


if __name__ == "__main__":
    main()
