#!/usr/bin/env python3
"""FIELD-R36 regression for user-reported chunk-square water artifacts.

The seed and dry samples come from manual F3 screenshots. The probe combines
point controls with the established FIELD-R20 chunk-boundary WATER/AIR metric,
so a fix cannot simply move the rectangular wall away from one coordinate.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

SEED=-4651369264513492755

# Player block positions from screenshots where the camera is visibly in dry
# cave air while looking at an adjacent WATER wall.
DRY_SAMPLES=(
    (14,52,11),
    (8,52,14),
    (-53,23,50),
)

# Chunk centers covering all screenshot defects: cave WATER walls, the old
# synthetic-support rectangles, and the surface/ocean transition around them.
TARGET_CHUNKS=(
    (0,0),
    (-4,3),
    (0,-1),
    (3,0),
    (2,3),
    (12,4),
)

MAX_BOUNDARY_WATER_AIR_FACES=192
MIN_SURFACE_WATER_COLUMNS=1


def require(ok,message):
    if not ok:
        raise ValueError("[FIELD-R36 water-square seed] "+message)


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,"missing module: "+str(path))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def sample_chunks():
    chunks=set()
    for cx,cz in TARGET_CHUNKS:
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    require(len(chunks)<=80,"target envelope unexpectedly large")
    return sorted(chunks)


def state_name(state):
    return state.get("Name") if isinstance(state,dict) else None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar",type=Path,required=True)
    p.add_argument("--overworld",type=Path,required=True)
    p.add_argument("--nether",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load("field_r36_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("field_r36_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    field20=load("field_r36_field20",root/"qa/field-r20/probe-user-seed.py")
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r36-water-square-seed"
    if work.exists():shutil.rmtree(work)
    packs=work/"world/datapacks";packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n",encoding="utf-8")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25595\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",encoding="utf-8"
    )

    chunks=sample_chunks()
    log=out/"field-r36-water-square-seed-server.log"
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

    seam=field20.seam_audit(volume,chunks)
    surface=field20.surface_water_columns(volume,chunks)

    text=log.read_text(encoding="utf-8",errors="replace")
    scheduler_errors=[
        line.strip() for line in text.splitlines()
        if "Missing chunkholder when required" in line
        or "[ChunkTaskScheduler] Chunk system error" in line
    ][:100]

    checks={
        "screenshot_player_samples_remain_dry":len(failed_dry)==0,
        "no_large_chunk_boundary_water_wall":
            seam["max_boundary_water_air_faces"]<=MAX_BOUNDARY_WATER_AIR_FACES,
        "surface_ocean_still_present":len(surface)>=MIN_SURFACE_WATER_COLUMNS,
        "no_chunk_scheduler_failure":len(scheduler_errors)==0,
    }
    report={
        "schema":1,
        "profile":"FIELD-R36-WATER-SQUARE-SEED-1",
        "source_sha":a.source_sha,
        "seed":SEED,
        "jar_sha256":sha(a.jar),
        "overworld_sha256":sha(a.overworld),
        "nether_sha256":sha(a.nether),
        "target_chunks":[list(p) for p in TARGET_CHUNKS],
        "generated_chunks":[list(p) for p in chunks],
        "dry_samples":dry_rows,
        "failed_dry_samples":failed_dry,
        "surface_water_columns":len(surface),
        "seam_audit":seam,
        "scheduler_errors":scheduler_errors,
        "checks":checks,
        "pass":all(checks.values()),
    }
    target=out/"field-r36-water-square-seed.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R36 water-square seed] "+json.dumps({
        "seed":SEED,
        "pass":report["pass"],
        "dry_samples":dry_rows,
        "max_boundary_water_air_faces":seam["max_boundary_water_air_faces"],
        "total_boundary_water_air_faces":seam["total_boundary_water_air_faces"],
        "surface_water_columns":len(surface),
        "scheduler_errors":len(scheduler_errors),
    },ensure_ascii=False,sort_keys=True),flush=True)
    require(report["pass"],"chunk-square water regression failed; see "+str(target))


if __name__=="__main__":
    main()
