#!/usr/bin/env python3
"""Regression for manually reported over-flooded caves on FIELD-R22.

The reported RC1 world filled deep cave volume merely because a large
chunk-seam component was horizontally near an ocean column. FIELD-R22 must
instead require a continuous floodable path to a real/prospective Y=128 ocean
seed. These points are taken from the manual screenshots for the exact seed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
from pathlib import Path

SEED = -4193070274438815849
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
WATER = "minecraft:water"

# Block positions shown by F3/manual inspection in the flooded cave cluster.
# They were visibly inside the erroneous deep-water volume in RC1.
BUG_POINTS = (
    (-2284, 9, -1443),
    (-2297, 46, -1438),
    (-2275, -9, -1445),
    (-2272, -13, -1442),
)
NEIGHBOR_RADIUS_XZ = 2
NEIGHBOR_RADIUS_Y = 2
MAX_LOCAL_WATER = 32


def require(ok, message):
    if not ok:
        raise ValueError("[FIELD-R22 strict-ocean seed] " + message)


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
    selected=set()
    for x, _, z in BUG_POINTS:
        cx,cz=x//16,z//16
        for dx in range(-2,3):
            for dz in range(-2,3):
                selected.add((cx+dx,cz+dz))
    require(1 <= len(selected) <= 96, "unexpected target envelope")
    return sorted(selected)


def block_name(state):
    return None if state is None else state.get("Name")


def local_water(volume, x, y, z):
    water=[]
    unknown=[]
    for dy in range(-NEIGHBOR_RADIUS_Y,NEIGHBOR_RADIUS_Y+1):
        for dz in range(-NEIGHBOR_RADIUS_XZ,NEIGHBOR_RADIUS_XZ+1):
            for dx in range(-NEIGHBOR_RADIUS_XZ,NEIGHBOR_RADIUS_XZ+1):
                pos=(x+dx,y+dy,z+dz)
                state=volume.at(*pos)
                if state is None:
                    unknown.append(pos)
                elif state.get("Name")==WATER:
                    water.append(pos)
    require(not unknown, "point neighbourhood escaped loaded envelope")
    return water


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar",type=Path,required=True)
    p.add_argument("--overworld",type=Path,required=True)
    p.add_argument("--nether",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load("strict_ocean_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("strict_ocean_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r22-strict-ocean-seed"
    require(not work.exists(), "strict-ocean workdir already exists")
    packs=work/"world/datapacks"
    packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n",encoding="utf-8")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25598\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",
        encoding="utf-8",
    )

    chunks=target_chunks()
    log=out/"field-r22-strict-ocean-seed-server.log"
    server=Server(a.jar.resolve(),work,log,java_args=["-Dneverfolia.debugFloodSeams=true"])
    normal=False
    try:
        server.wait(r"Done \(",timeout=300)
        server.disable_random_ticks()
        # Generate in a bounded batch exactly as a normal multi-chunk visit,
        # then persist before inspecting the final FULL chunks.
        server.load_dimension(chunks,"minecraft:overworld",dwell=4,serial_generation=False)
        code=server.stop()
        require(code==0,"target seed server stop failed")
        normal=True
    finally:
        if not normal:
            server.close()

    text=log.read_text(encoding="utf-8",errors="replace")
    proximity_lines=[
        line.strip() for line in text.splitlines()
        if "[NeverFolia][R22ProximityFlood]" in line
    ]
    require(not proximity_lines,"unsafe proximity flood runtime path executed")

    region=work/"world/dimensions/minecraft/overworld/region"
    roots={p:nbt.read_chunk_nbt(region,*p) for p in chunks}
    volume=observer.Volume(roots)

    points=[]
    all_pass=True
    for x,y,z in BUG_POINTS:
        state=block_name(volume.at(x,y,z))
        water=local_water(volume,x,y,z)
        point_pass=state != WATER and len(water) <= MAX_LOCAL_WATER
        all_pass &= point_pass
        points.append({
            "position":[x,y,z],
            "chunk":[x//16,z//16],
            "state":state,
            "local_cube":[
                2*NEIGHBOR_RADIUS_XZ+1,
                2*NEIGHBOR_RADIUS_Y+1,
                2*NEIGHBOR_RADIUS_XZ+1,
            ],
            "local_water_blocks":len(water),
            "max_local_water":MAX_LOCAL_WATER,
            "water_examples":[list(p) for p in water[:24]],
            "pass":point_pass,
        })

    report={
        "schema":1,
        "profile":"FIELD-R22-STRICT-OCEAN-SEED-1",
        "source_sha":a.source_sha,
        "seed":SEED,
        "jar_sha256":sha(a.jar),
        "overworld_sha256":sha(a.overworld),
        "nether_sha256":sha(a.nether),
        "chunks":[list(p) for p in chunks],
        "proximity_flood_runtime_markers":len(proximity_lines),
        "points":points,
        "pass":all_pass and not proximity_lines,
        "notes":[
            "Points are the manual RC1 over-flooded cave locations reported on seed -4193070274438815849.",
            "A point itself must not be source water after strict-ocean generation.",
            "The bounded 5x5x5 neighbourhood gate rejects the former bulk cave flooding while tolerating a small local aquifer.",
            "R22ProximityFlood is forbidden: horizontal proximity is not ocean connectivity.",
        ],
    }
    target=out/"field-r22-strict-ocean-seed.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R22 strict-ocean seed] "+json.dumps({
        "profile":report["profile"],
        "source_sha":report["source_sha"],
        "seed":SEED,
        "states":[p["state"] for p in points],
        "local_water":[p["local_water_blocks"] for p in points],
        "proximity_markers":len(proximity_lines),
        "pass":report["pass"],
    },ensure_ascii=False,sort_keys=True),flush=True)
    require(report["pass"],"manual cave-water regression reproduced; see field-r22-strict-ocean-seed.json")


if __name__=="__main__":
    main()
