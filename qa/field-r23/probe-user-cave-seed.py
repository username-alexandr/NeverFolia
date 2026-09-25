#!/usr/bin/env python3
"""FIELD-R23 regression for the user-reported fully flooded cave seed."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil

SEED = -4193070274438815849
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
CAMERA_POINTS = (
    (-2284, 9, -1443),
    (-2297, 46, -1438),
    (-2275, -9, -1445),
    (-2272, -13, -1442),
)

def require(ok, message):
    if not ok:
        raise ValueError("[FIELD-R23 cave seed] " + message)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "missing module: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def sha(path):
    import hashlib
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def target_chunks():
    centers = {(x // 16, z // 16) for x, _, z in CAMERA_POINTS}
    chunks = set()
    for cx, cz in centers:
        for dx in range(-1, 2):
            for dz in range(-1, 2):
                chunks.add((cx + dx, cz + dz))
    return sorted(chunks)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar", type=Path, required=True)
    p.add_argument("--overworld", type=Path, required=True)
    p.add_argument("--nether", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--source-sha", required=True)
    a = p.parse_args()

    root = Path(__file__).resolve().parents[2]
    observer = load("field_r23_observer", root / "scripts/probe-never-overworld-trees-villages-r1.py")
    paired = load("field_r23_paired", root / "scripts/probe-never-overworld-paired-r12.py")
    nbt = observer.load_nbt(root)
    Server = paired.make_server(observer)

    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = root / ".work/field-r23-user-cave-seed"
    require(not work.exists(), "existing FIELD-R23 work directory")
    packs = work / "world/datapacks"
    packs.mkdir(parents=True)
    shutil.copyfile(a.overworld, packs / "NeverOverworld.zip")
    shutil.copyfile(a.nether, packs / "NeverNether.zip")
    (work / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    (work / "server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25596\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",
        encoding="utf-8",
    )

    chunks = target_chunks()
    log = out / "field-r23-user-cave-seed-server.log"
    server = Server(a.jar.resolve(), work, log, java_args=["-Dneverfolia.debugFloodSeams=true"])
    normal = False
    try:
        server.wait(r"Done \(", timeout=300)
        server.disable_random_ticks()
        server.load_dimension(chunks, "minecraft:overworld", dwell=8, serial_generation=False)
        code = server.stop()
        require(code == 0, "target seed server stop failed")
        normal = True
    finally:
        if not normal:
            server.close()

    log_text = log.read_text(encoding="utf-8", errors="replace")
    require("[NeverFolia][R22ProximityFlood]" not in log_text,
            "obsolete R22 proximity flood executed")

    region = work / "world/dimensions/minecraft/overworld/region"
    roots = {pos: nbt.read_chunk_nbt(region, *pos) for pos in chunks}
    volume = observer.Volume(roots)

    points = []
    water_points = []
    non_air_points = []
    for x, y, z in CAMERA_POINTS:
        state = volume.at(x, y, z)
        require(state is not None, f"camera point missing from persisted sample: {x},{y},{z}")
        name = state.get("Name")
        row = {"pos": [x, y, z], "state": name}
        points.append(row)
        if name == "minecraft:water":
            water_points.append(row)
        if name not in AIR:
            non_air_points.append(row)

    # These exact coordinates are the camera locations from the user's F3
    # screenshots. They are open cave volume in the same deterministic seed,
    # so R23 must keep them dry instead of turning the cavern into source water.
    require(not water_points, "reported deep cave camera points are still WATER: " + repr(water_points))
    require(not non_air_points, "reported cave camera points are not AIR after strict flood: " + repr(non_air_points))

    report = {
        "schema": 1,
        "profile": "FIELD-R23-USER-CAVE-SEED-1",
        "source_sha": a.source_sha,
        "seed": SEED,
        "jar_sha256": sha(a.jar),
        "overworld_sha256": sha(a.overworld),
        "nether_sha256": sha(a.nether),
        "chunks": [list(p) for p in chunks],
        "camera_points": points,
        "camera_water_points": water_points,
        "camera_non_air_points": non_air_points,
        "obsolete_proximity_log_seen": False,
        "pass": True,
        "notes": [
            "Camera coordinates are taken from the user's F3 screenshots for seed -4193070274438815849.",
            "R23 requires physical ocean connectivity; near-ocean geometry alone may not flood a cave.",
            "The four reported deep-cave camera cells must persist as AIR.",
        ],
    }
    target = out / "field-r23-user-cave-seed.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("[FIELD-R23 cave seed] " + json.dumps({
        "seed": SEED,
        "camera_points": points,
        "pass": True,
    }, ensure_ascii=False, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
