#!/usr/bin/env python3
"""FIELD-R24 regression for user-reported deep-water and berry bugs."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

SEED=-5997491035824281296

# Positions read from the user's F3 screenshots. These are deep/internal cave
# samples where the reported build produced isolated source/flowing water.
DRY_SAMPLES=(
    (87,-9,61),
    (138,-8,-25),
    (205,-30,27),
    (-23109,40,-59094),
)

# Underwater berry screenshot was around this location. R24 also scans every
# loaded sample chunk and rejects sweet berry bushes at/below the Y128 ocean.
BERRY_REFERENCE=(-155,91,196)
OCEAN_Y=128
AIR={"minecraft:air","minecraft:cave_air","minecraft:void_air"}

def require(ok,message):
    if not ok: raise ValueError("[FIELD-R24 water/flora seed] "+message)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,"missing module: "+str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def sample_chunks():
    centers={(x//16,z//16) for x,_,z in DRY_SAMPLES+(BERRY_REFERENCE,)}
    chunks=set()
    for cx,cz in centers:
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    return sorted(chunks)

def state_name(state):
    if state is None:return None
    return state.get("Name")

def deep_water_wall_audit(volume,chunks):
    """Reject large below-ocean WATER columns/planes not reaching Y128.

    This targets the user's x-ray-visible vertical WATER walls. A column is
    suspicious when it contains a long contiguous deep-water run but has no
    WATER path in that same X/Z column to the ocean plane. The metric is local
    and deliberately conservative: ordinary short cave drips do not fail it.
    """
    selected=set(chunks)
    suspicious=[]
    max_run=0
    total_columns=0
    for cx,cz in sorted(selected):
        base_x=cx*16;base_z=cz*16
        for x in range(base_x,base_x+16):
            for z in range(base_z,base_z+16):
                runs=[];start=None
                for y in range(-64,OCEAN_Y):
                    water=state_name(volume.at(x,y,z))=="minecraft:water"
                    if water and start is None:start=y
                    elif not water and start is not None:
                        runs.append((start,y-1));start=None
                if start is not None:runs.append((start,OCEAN_Y-1))
                if not runs:continue
                surface_connected=state_name(volume.at(x,OCEAN_Y,z))=="minecraft:water"
                for lo,hi in runs:
                    length=hi-lo+1
                    max_run=max(max_run,length)
                    if length<16 or surface_connected:continue
                    total_columns+=1
                    if len(suspicious)<200:
                        suspicious.append({"x":x,"z":z,"min_y":lo,"max_y":hi,"length":length})
    return {
        "max_deep_vertical_water_run":max_run,
        "suspicious_deep_water_columns":total_columns,
        "examples":suspicious,
        "pass":total_columns==0,
        "minimum_flagged_run":16,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar",type=Path,required=True)
    p.add_argument("--overworld",type=Path,required=True)
    p.add_argument("--nether",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load("field_r24_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("field_r24_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r24-water-flora-seed"
    if work.exists():shutil.rmtree(work)
    packs=work/"world/datapacks";packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25595\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",encoding="utf-8")

    chunks=sample_chunks()
    log=out/"field-r24-water-flora-server.log"
    server=Server(a.jar.resolve(),work,log,java_args=["-Dneverfolia.debugFloodSeams=true"])
    normal=False
    try:
        server.wait(r"Done \(",timeout=300)
        server.disable_random_ticks()
        server.load_dimension(chunks,"minecraft:overworld",dwell=6,serial_generation=False)
        code=server.stop();require(code==0,"server stop failed")
        normal=True
    finally:
        if not normal:server.close()

    region=work/"world/dimensions/minecraft/overworld/region"
    roots={pos:nbt.read_chunk_nbt(region,*pos) for pos in chunks}
    volume=observer.Volume(roots)

    dry_rows=[]
    failed_dry=[]
    for x,y,z in DRY_SAMPLES:
        state=state_name(volume.at(x,y,z))
        row={"pos":[x,y,z],"state":state,"dry":state!="minecraft:water"}
        dry_rows.append(row)
        if not row["dry"]:failed_dry.append(row)

    berries=[]
    for cx,cz in chunks:
        base_x=cx*16;base_z=cz*16
        for x in range(base_x,base_x+16):
            for z in range(base_z,base_z+16):
                for y in range(-64,OCEAN_Y+1):
                    if state_name(volume.at(x,y,z))=="minecraft:sweet_berry_bush":
                        berries.append([x,y,z])
                        if len(berries)>=200:break
                if len(berries)>=200:break
            if len(berries)>=200:break
        if len(berries)>=200:break

    water_walls=deep_water_wall_audit(volume,chunks)

    text=log.read_text(encoding="utf-8",errors="replace")
    chunk_errors=[
        line.strip() for line in text.splitlines()
        if "Missing chunkholder when required" in line or "[ChunkTaskScheduler] Chunk system error" in line
    ]

    report={
        "schema":1,
        "profile":"FIELD-R24-WATER-FLORA-SEED-1",
        "source_sha":a.source_sha,
        "seed":SEED,
        "jar_sha256":sha(a.jar),
        "overworld_sha256":sha(a.overworld),
        "nether_sha256":sha(a.nether),
        "chunks":[list(x) for x in chunks],
        "dry_samples":dry_rows,
        "failed_dry_samples":failed_dry,
        "sweet_berry_bush_at_or_below_ocean":berries,
        "deep_water_wall_audit":water_walls,
        "chunk_system_errors":chunk_errors[:100],
        "checks":{
            "reported_deep_cave_samples_not_water":len(failed_dry)==0,
            "sweet_berry_bush_only_above_ocean":len(berries)==0,
            "no_isolated_deep_water_walls":water_walls["pass"],
            "no_chunk_system_failure":len(chunk_errors)==0,
        },
    }
    report["pass"]=all(report["checks"].values())
    target=out/"field-r24-water-flora-seed.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R24 water/flora] "+json.dumps({
        "seed":SEED,"pass":report["pass"],"dry_samples":dry_rows,
        "berries_below_ocean":len(berries),
        "deep_water_columns":water_walls["suspicious_deep_water_columns"],
        "max_deep_water_run":water_walls["max_deep_vertical_water_run"],
        "chunk_errors":len(chunk_errors)
    },ensure_ascii=False,sort_keys=True),flush=True)
    require(report["pass"],"user-seed water/flora regression failed; see "+str(target))

if __name__=="__main__":main()
