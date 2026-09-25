#!/usr/bin/env python3
"""FIELD-R23 regression for user-reported over-flooded caves."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil

SEED=-4193070274438815849
AIR={"minecraft:air","minecraft:cave_air","minecraft:void_air"}

# Camera positions from the user screenshots, floored to block coordinates.
DRY_CAVE_SAMPLES=(
    (-2284,9,-1443),
    (-2297,46,-1438),
    (-2275,-9,-1445),
    (-2272,-13,-1442),
)
# Underwater monument/ocean control: this must remain flooded.
OCEAN_WET_SAMPLES=(
    (-2251,111,-1336),
)

def require(ok,message):
    if not ok:raise ValueError("[FIELD-R23 cave flood] "+message)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,"missing module: "+str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def state_name(state):
    return None if state is None else state.get("Name")

def chunks_to_load():
    chunks=set()
    for x,_,z in DRY_CAVE_SAMPLES+OCEAN_WET_SAMPLES:
        cx=x//16;cz=z//16
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    return sorted(chunks)

def cave_profile(volume):
    rows=[]
    for x,_,z in DRY_CAVE_SAMPLES:
        cx=x//16;cz=z//16
        air=water=lava=known=0
        for bx in range(cx*16,cx*16+16):
            for bz in range(cz*16,cz*16+16):
                for y in range(-32,65):
                    name=state_name(volume.at(bx,y,bz))
                    if name is None:continue
                    known+=1
                    if name in AIR:air+=1
                    elif name=="minecraft:water":water+=1
                    elif name=="minecraft:lava":lava+=1
        rows.append({
            "chunk":[cx,cz],"known":known,"air":air,"water":water,"lava":lava,
            "air_share_of_air_water": air/(air+water) if air+water else None,
        })
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar",type=Path,required=True)
    p.add_argument("--overworld",type=Path,required=True)
    p.add_argument("--nether",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load("field_r23_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("field_r23_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r23-user-seed"
    if work.exists():shutil.rmtree(work)
    packs=work/"world/datapacks";packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n",encoding="utf-8")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25596\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",encoding="utf-8"
    )

    chunks=chunks_to_load()
    log=out/"field-r23-user-seed-server.log"
    server=Server(a.jar.resolve(),work,log,java_args=["-Dneverfolia.debugFloodSeams=true"])
    normal=False
    try:
        server.wait(r"Done \(",timeout=300)
        server.disable_random_ticks()
        server.load_dimension(chunks,"minecraft:overworld",dwell=6,serial_generation=False)
        code=server.stop()
        require(code==0,"target seed server stop failed")
        normal=True
    finally:
        if not normal:server.close()

    region=work/"world/dimensions/minecraft/overworld/region"
    roots={pos:nbt.read_chunk_nbt(region,*pos) for pos in chunks}
    volume=observer.Volume(roots)

    dry=[]
    for x,y,z in DRY_CAVE_SAMPLES:
        name=state_name(volume.at(x,y,z))
        dry.append({"pos":[x,y,z],"state":name,"pass":name in AIR})
    wet=[]
    for x,y,z in OCEAN_WET_SAMPLES:
        name=state_name(volume.at(x,y,z))
        wet.append({"pos":[x,y,z],"state":name,"pass":name=="minecraft:water"})

    profile=cave_profile(volume)
    report={
        "schema":1,"profile":"FIELD-R23-USER-SEED-CAVE-1",
        "source_sha":a.source_sha,"seed":SEED,
        "dry_cave_samples":dry,"ocean_wet_samples":wet,
        "chunk_profiles":profile,
        "pass":all(row["pass"] for row in dry+wet),
        "notes":[
            "Dry samples are floored camera coordinates from the user screenshots.",
            "Isolated/deep caves must remain dry unless an authoritative ocean-water path reaches them.",
            "The underwater monument control must remain ocean-flooded.",
        ],
    }
    target=out/"field-r23-user-seed-cave.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R23 cave seed] "+json.dumps({
        "seed":SEED,"pass":report["pass"],
        "dry":[(r["pos"],r["state"],r["pass"]) for r in dry],
        "wet":[(r["pos"],r["state"],r["pass"]) for r in wet],
    },ensure_ascii=False),flush=True)
    require(report["pass"],"user-reported cave flooding regression failed; see field-r23-user-seed-cave.json")

if __name__=="__main__":main()
