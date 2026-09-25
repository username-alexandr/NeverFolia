#!/usr/bin/env python3
"""Report deterministic NeverOverworld DESERT-R1 sandstorm windows.

Use /time query gametime in-game, then pass that value here. This helper mirrors
NeverOverworldSandstormR1 exactly and does not modify a world or server.
"""
from __future__ import annotations

import argparse
import json
import math

MASK = (1 << 64) - 1
DEFAULT_SEED = -2996952393010080672
CYCLE_TICKS = 12_000
STORM_CHANCE_PERCENT = 35
STORM_DURATION = 2_400
SALT = 0x53414E4453544F52
CYCLE_SALT = 0x9E3779B97F4A7C15
START_SALT = 0xC2B2AE3D27D4EB4F
DIRECTION_SALT = 0xD6E8FEB86659FD93


def s64(value: int) -> int:
    value &= MASK
    return value - (1 << 64) if value & (1 << 63) else value


def urshift(value: int, bits: int) -> int:
    return (value & MASK) >> bits


def mul64(left: int, right: int) -> int:
    return s64((left & MASK) * (right & MASK))


def mix(value: int) -> int:
    value = s64(value ^ urshift(value, 30))
    value = mul64(value, 0xBF58476D1CE4E5B9)
    value = s64(value ^ urshift(value, 27))
    value = mul64(value, 0x94D049BB133111EB)
    return s64(value ^ urshift(value, 31))


def cycle_state(seed: int, cycle: int) -> dict:
    cycle_term = mul64(cycle, CYCLE_SALT)
    h = mix(s64(seed ^ SALT ^ (cycle_term & MASK)))
    enabled = h % 100 < STORM_CHANCE_PERCENT
    start = 800 + mix(s64(h ^ START_SALT)) % 2_800
    direction_hash = mix(s64(h ^ DIRECTION_SALT))
    direction_index = direction_hash % 4_096
    angle = direction_index * (math.tau / 4_096.0)
    wind_x = math.cos(angle)
    wind_z = math.sin(angle)
    return {
        "cycle": cycle,
        "enabled": enabled,
        "start_tick_in_cycle": start,
        "end_tick_in_cycle": start + STORM_DURATION,
        "wind_x": wind_x,
        "wind_z": wind_z,
        "direction_index": direction_index,
    }


def cardinal(wind_x: float, wind_z: float) -> str:
    angle = math.atan2(wind_z, wind_x)
    octant = int(round(8 * angle / math.tau)) % 8
    # Minecraft: +X east, +Z south, -X west, -Z north.
    return ("east", "south-east", "south", "south-west",
            "west", "north-west", "north", "north-east")[octant]


def find_window(seed: int, game_time: int, max_cycles: int = 10_000) -> dict:
    current_cycle = game_time // CYCLE_TICKS
    phase = game_time % CYCLE_TICKS
    current = cycle_state(seed, current_cycle)
    active_now = (
        current["enabled"]
        and current["start_tick_in_cycle"] <= phase < current["end_tick_in_cycle"]
    )
    if active_now:
        start_game_time = current_cycle * CYCLE_TICKS + current["start_tick_in_cycle"]
        end_game_time = current_cycle * CYCLE_TICKS + current["end_tick_in_cycle"]
        result = dict(current)
        result.update({
            "active_now": True,
            "start_game_time": start_game_time,
            "end_game_time": end_game_time,
            "ticks_until_start": 0,
            "ticks_until_end": end_game_time - game_time,
        })
        return result

    for cycle in range(current_cycle, current_cycle + max_cycles + 1):
        state = cycle_state(seed, cycle)
        if not state["enabled"]:
            continue
        start_game_time = cycle * CYCLE_TICKS + state["start_tick_in_cycle"]
        end_game_time = cycle * CYCLE_TICKS + state["end_tick_in_cycle"]
        if end_game_time <= game_time:
            continue
        if start_game_time <= game_time < end_game_time:
            ticks_until_start = 0
            active_now = True
        else:
            ticks_until_start = start_game_time - game_time
            active_now = False
        result = dict(state)
        result.update({
            "active_now": active_now,
            "start_game_time": start_game_time,
            "end_game_time": end_game_time,
            "ticks_until_start": max(0, ticks_until_start),
            "ticks_until_end": end_game_time - game_time,
        })
        return result
    raise RuntimeError(f"no enabled storm cycle found in next {max_cycles} cycles")


def seconds(ticks: int) -> float:
    return ticks / 20.0


def self_test() -> None:
    state = cycle_state(DEFAULT_SEED, 4)
    assert state["enabled"] is True
    assert state["start_tick_in_cycle"] == 1248
    assert state["direction_index"] == 3078
    assert abs(state["wind_x"] - 0.009203754782059715) < 1.0e-12
    assert abs(state["wind_z"] - (-0.9999576445519639)) < 1.0e-12
    window = find_window(DEFAULT_SEED, 0)
    assert window["cycle"] == 4
    assert window["start_game_time"] == 49_248
    assert window["end_game_time"] == 51_648
    active = find_window(DEFAULT_SEED, 50_000)
    assert active["active_now"] is True
    print("PASS NeverOverworld sandstorm-window self-test")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-time", type=int, help="Value from /time query gametime")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.game_time is None:
        parser.error("--game-time is required unless --self-test is used")

    result = find_window(args.seed, args.game_time)
    result["seed"] = args.seed
    result["game_time"] = args.game_time
    result["wind_cardinal"] = cardinal(result["wind_x"], result["wind_z"])
    result["seconds_until_start"] = seconds(result["ticks_until_start"])
    result["minutes_until_start"] = result["seconds_until_start"] / 60.0
    result["seconds_until_end"] = seconds(result["ticks_until_end"])

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"Seed: {args.seed}")
    print(f"Game time: {args.game_time}")
    print(f"Storm active now: {'yes' if result['active_now'] else 'no'}")
    print(f"Storm cycle: {result['cycle']}")
    print(f"Window: {result['start_game_time']} .. {result['end_game_time']} game ticks")
    if result["active_now"]:
        print(f"Ends in: {result['ticks_until_end']} ticks ({result['seconds_until_end']:.1f} s)")
    else:
        print(
            f"Starts in: {result['ticks_until_start']} ticks "
            f"({result['minutes_until_start']:.2f} min)"
        )
    print(
        f"Wind: x={result['wind_x']:.6f}, z={result['wind_z']:.6f} "
        f"-> {result['wind_cardinal']}"
    )


if __name__ == "__main__":
    main()
