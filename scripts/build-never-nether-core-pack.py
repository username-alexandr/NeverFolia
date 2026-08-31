#!/usr/bin/env python3
import argparse
import json
import tempfile
import zipfile
from pathlib import Path


def write_json(root: Path, rel: str, value) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add(a, b):
    return {"type": "minecraft:add", "argument1": a, "argument2": b}


def mul(a, b):
    return {"type": "minecraft:mul", "argument1": a, "argument2": b}


def minimum(a, b):
    return {"type": "minecraft:min", "argument1": a, "argument2": b}


def gradient(from_y, to_y, from_value, to_value):
    return {
        "type": "minecraft:y_clamped_gradient",
        "from_y": from_y,
        "to_y": to_y,
        "from_value": from_value,
        "to_value": to_value,
    }


def noise(name, xz_scale=1.0, y_scale=1.0):
    return {
        "type": "minecraft:noise",
        "noise": f"neverfolia:never_nether/{name}",
        "xz_scale": xz_scale,
        "y_scale": y_scale,
    }


def choice(input_value, min_inclusive, max_exclusive, when_in_range, when_out_of_range=0.0):
    return {
        "type": "minecraft:range_choice",
        "input": input_value,
        "min_inclusive": min_inclusive,
        "max_exclusive": max_exclusive,
        "when_in_range": when_in_range,
        "when_out_of_range": when_out_of_range,
    }


def biome_floor(biome: str, block: str):
    return {
        "type": "minecraft:condition",
        "if_true": {"type": "minecraft:biome", "biome_is": biome},
        "then_run": {
            "type": "minecraft:condition",
            "if_true": {
                "type": "minecraft:stone_depth",
                "surface_type": "floor",
                "offset": 0,
                "add_surface_depth": True,
                "secondary_depth_range": 0,
            },
            "then_run": {"type": "minecraft:block", "result_state": {"Name": block}},
        },
    }


def build_pack(root: Path) -> None:
    write_json(
        root,
        "pack.mcmeta",
        {
            "pack": {
                "description": "NeverNether Core TEST — NeverFolia 26.2",
                "min_format": [107, 1],
                "max_format": 107,
            }
        },
    )

    write_json(
        root,
        "data/minecraft/dimension_type/the_nether.json",
        {
            "ambient_light": 0.1,
            "attributes": {
                "minecraft:gameplay/bed_rule": {
                    "can_set_spawn": "never",
                    "can_sleep": "never",
                    "explodes": True,
                },
                "minecraft:gameplay/can_start_raid": False,
                "minecraft:gameplay/fast_lava": True,
                "minecraft:gameplay/piglins_zombify": False,
                "minecraft:gameplay/respawn_anchor_works": True,
                "minecraft:gameplay/sky_light_level": 4.0,
                "minecraft:gameplay/snow_golem_melts": True,
                "minecraft:gameplay/water_evaporates": True,
                "minecraft:visual/ambient_light_color": "#302821",
                "minecraft:visual/default_dripstone_particle": {
                    "type": "minecraft:dripping_dripstone_lava"
                },
                "minecraft:visual/fog_end_distance": 96.0,
                "minecraft:visual/fog_start_distance": 10.0,
                "minecraft:visual/sky_light_color": "#7a7aff",
                "minecraft:visual/sky_light_factor": 0.0,
            },
            "cardinal_light": "nether",
            "coordinate_scale": 8.0,
            "has_ceiling": True,
            "has_ender_dragon_fight": False,
            "has_fixed_time": True,
            "has_skylight": False,
            "height": 1024,
            "infiniburn": "#minecraft:infiniburn_nether",
            "logical_height": 1024,
            "min_y": -128,
            "monster_spawn_block_light_limit": 15,
            "monster_spawn_light_level": 7,
            "skybox": "none",
            "timelines": "#minecraft:in_nether",
        },
    )

    custom_noises = {
        "mega_cavern": (-9, [1.0, 0.55]),
        "secondary_cave": (-6, [1.0, 0.7, 0.35]),
        "chasm": (-7, [1.0, 0.5]),
        "hanging_mass": (-8, [1.0, 0.55]),
        "magma_chamber": (-8, [1.0, 0.6]),
    }
    for name, (first_octave, amplitudes) in custom_noises.items():
        write_json(
            root,
            f"data/neverfolia/worldgen/noise/never_nether/{name}.json",
            {"firstOctave": first_octave, "amplitudes": amplitudes},
        )

    write_json(
        root,
        "data/neverfolia/worldgen/density_function/never_nether/base_mass.json",
        {
            "type": "minecraft:old_blended_noise",
            "smear_scale_multiplier": 8.0,
            "xz_factor": 110.0,
            "xz_scale": 0.18,
            "y_factor": 90.0,
            "y_scale": 0.28,
        },
    )

    lower_weight = minimum(
        gradient(-64, 16, 0.0, 1.0),
        gradient(96, 176, 1.0, 0.0),
    )
    upper_weight = minimum(
        gradient(96, 240, 0.0, 1.0),
        gradient(336, 384, 1.0, 0.0),
    )
    deep_weight = gradient(-32, -112, 0.0, 1.0)

    terms = [
        mul(lower_weight, -0.16),
        choice(noise("mega_cavern", 1.0, 0.75), 0.56, 2.0, -0.52),
        choice(noise("secondary_cave", 1.35, 1.05), 0.64, 2.0, -0.22),
        choice(noise("chasm", 1.8, 0.18), 0.68, 2.0, -0.48),
        mul(deep_weight, choice(noise("magma_chamber", 0.95, 0.55), 0.60, 2.0, -0.42)),
        mul(upper_weight, choice(noise("hanging_mass", 0.75, 0.55), 0.58, 2.0, 0.34)),
        mul(gradient(-128, -96, 1.0, 0.0), 2.6),
        mul(gradient(344, 384, 0.0, 1.0), 2.8),
    ]

    core = "neverfolia:never_nether/base_mass"
    for term in terms:
        core = add(core, term)

    write_json(
        root,
        "data/neverfolia/worldgen/density_function/never_nether/final_density.json",
        {
            "type": "minecraft:squeeze",
            "argument": {
                "type": "minecraft:interpolated",
                "argument": mul(0.64, core),
            },
        },
    )

    bedrock_floor = {
        "type": "minecraft:condition",
        "if_true": {
            "type": "minecraft:vertical_gradient",
            "random_name": "neverfolia:bedrock_floor",
            "true_at_and_below": {"above_bottom": 0},
            "false_at_and_above": {"above_bottom": 5},
        },
        "then_run": {"type": "minecraft:block", "result_state": {"Name": "minecraft:bedrock"}},
    }
    bedrock_roof = {
        "type": "minecraft:condition",
        "if_true": {
            "type": "minecraft:not",
            "invert": {
                "type": "minecraft:vertical_gradient",
                "random_name": "neverfolia:bedrock_roof",
                "true_at_and_below": {"below_top": 5},
                "false_at_and_above": {"below_top": 0},
            },
        },
        "then_run": {"type": "minecraft:block", "result_state": {"Name": "minecraft:bedrock"}},
    }
    surface_rule = {
        "type": "minecraft:sequence",
        "sequence": [
            bedrock_floor,
            bedrock_roof,
            biome_floor("minecraft:basalt_deltas", "minecraft:blackstone"),
            biome_floor("minecraft:soul_sand_valley", "minecraft:soul_soil"),
            biome_floor("minecraft:crimson_forest", "minecraft:crimson_nylium"),
            biome_floor("minecraft:warped_forest", "minecraft:warped_nylium"),
            {"type": "minecraft:block", "result_state": {"Name": "minecraft:netherrack"}},
        ],
    }

    write_json(
        root,
        "data/minecraft/worldgen/noise_settings/nether.json",
        {
            "aquifers_enabled": False,
            "default_block": {"Name": "minecraft:netherrack"},
            "default_fluid": {"Name": "minecraft:lava", "Properties": {"level": "0"}},
            "disable_mob_generation": False,
            "legacy_random_source": True,
            "noise": {"height": 512, "min_y": -128, "size_horizontal": 1, "size_vertical": 2},
            "noise_router": {
                "barrier": 0.0,
                "continents": 0.0,
                "depth": 0.0,
                "erosion": 0.0,
                "final_density": "neverfolia:never_nether/final_density",
                "fluid_level_floodedness": 0.0,
                "fluid_level_spread": 0.0,
                "lava": 0.0,
                "preliminary_surface_level": 0.0,
                "ridges": 0.0,
                "temperature": {
                    "type": "minecraft:shifted_noise",
                    "noise": "minecraft:nether/temperature",
                    "shift_x": 0.0,
                    "shift_y": 0.0,
                    "shift_z": 0.0,
                    "xz_scale": 0.25,
                    "y_scale": 0.0,
                },
                "vegetation": {
                    "type": "minecraft:shifted_noise",
                    "noise": "minecraft:nether/vegetation",
                    "shift_x": 0.0,
                    "shift_y": 0.0,
                    "shift_z": 0.0,
                    "xz_scale": 0.25,
                    "y_scale": 0.0,
                },
                "vein_gap": 0.0,
                "vein_ridged": 0.0,
                "vein_toggle": 0.0,
            },
            "ore_veins_enabled": False,
            "sea_level": 32,
            "spawn_target": [],
            "surface_rule": surface_rule,
        },
    )

    write_json(
        root,
        "nevernether-core-manifest.json",
        {
            "id": "NN-DEV-1-core-test1",
            "minecraft": "26.2",
            "dimension_min_y": -128,
            "dimension_height": 1024,
            "generated_min_y": -128,
            "generated_height": 512,
            "generated_max_y": 383,
            "roof_build_min_y": 384,
            "roof_build_max_y": 895,
            "lava_level": 32,
        },
    )


def validate_json(root: Path) -> None:
    for path in root.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the NeverNether 26.2 core test datapack")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="nevernether-core-") as tmp:
        root = Path(tmp) / "pack"
        root.mkdir()
        build_pack(root)
        validate_json(root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            args.output.unlink()
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    print(f"Built {args.output}")


if __name__ == "__main__":
    main()
