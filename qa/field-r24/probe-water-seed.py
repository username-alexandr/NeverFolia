#!/usr/bin/env python3
"""FIELD-R24 regression for user-reported cave water and submerged sweet berries."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

SEED=-5997491035824281296

# Player/F3 positions from the R23 fullpack screenshots. These locations are
# inside dry cave/structure volumes and must not be converted to source water.
DRY_SAMPLES=(
    (-2,10,68),
    (86,-10,60),
    (137,-8,-25),
    (205,-31,26),
    (-23110,40,-59094),
)

# Real ocean control from the submerged sweet-berry screenshot.
WATER_SAMPLES=(
    (-156,91,195),
)

BERRY="minecraft:sweet_berry_bush"

def require(ok,message):
    if not ok:
        raise ValueError("[FIELD-R24 water seed] "+message)

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
    centers={(x//16,z//16) for x,_,z in DRY_SAMPLES+WATER_SAMPLES}
    chunks=set()
    for cx,cz in centers:
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    return sorted(chunks)

def state_name(state):
    if state is None:
        return None
    return state.get("Name")

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

    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r24-water-seed"
    if work.exists():
        shutil.rmtree(work)
    packs=work/"world/datapacks"
    packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25595\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",
        encoding="utf-8",
    )

    chunks=sample_chunks()
    log=out/"field-r24-water-seed-server.log"
    server=Server(a.jar.resolve(),work,log,java_args=["-Dneverfolia.debugFloodSeams=true"])
    normal=False
    try:
        server.wait(r"Done \(",timeout=300)
        server.disable_random_ticks()
        server.load_dimension(chunks,"minecraft:overworld",dwell=6,serial_generation=False)
        code=server.stop()
        require(code==0,"server stop failed")
        normal=True
    finally:
        if not normal:
            server.close()

    region=work/"world/dimensions/minecraft/overworld/region"
    roots={pos:nbt.read_chunk_nbt(region,*pos) for pos in chunks}
    volume=observer.Volume(roots)

    dry_rows=[]
    failed_dry=[]
    for x,y,z in DRY_SAMPLES:
        state=state_name(volume.at(x,y,z))
        row={"pos":[x,y,z],"state":state,"dry":state!="minecraft:water"}
        dry_rows.append(row)
        if not row["dry"]:
            failed_dry.append(row)

    water_rows=[]
    failed_water=[]
    for x,y,z in WATER_SAMPLES:
        state=state_name(volume.at(x,y,z))
        row={"pos":[x,y,z],"state":state,"water":state=="minecraft:water"}
        water_rows.append(row)
        if not row["water"]:
            failed_water.append(row)

    # Scan the 3x3 chunk envelope around the underwater screenshot and reject
    # any sweet berry bush at/below the Y128 flood plane.
    berry_center={(x//16,z//16) for x,_,z in WATER_SAMPLES}
    berry_chunks=set()
    for cx,cz in berry_center:
        for dx in range(-1,2):
            for dz in range(-1,2):
                berry_chunks.add((cx+dx,cz+dz))
    submerged_berries=[]
    for cx,cz in sorted(berry_chunks):
        for x in range(cx*16,cx*16+16):
            for z in range(cz*16,cz*16+16):
                for y in range(-64,129):
                    if state_name(volume.at(x,y,z))==BERRY:
                        submerged_berries.append([x,y,z])
                        if len(submerged_berries)>=100:
                            break
                if len(submerged_berries)>=100:
                    break
            if len(submerged_berries)>=100:
                break
        if len(submerged_berries)>=100:
            break

    text=log.read_text(encoding="utf-8",errors="replace")
    proximity=[line.strip() for line in text.splitlines() if "[NeverFolia][R22ProximityFlood]" in line]
    report={
        "schema":1,
        "profile":"FIELD-R24-WATER-SEED-1",
        "source_sha":a.source_sha,
        "seed":SEED,
        "jar_sha256":sha(a.jar),
        "overworld_sha256":sha(a.overworld),
        "nether_sha256":sha(a.nether),
        "chunks":[list(x) for x in chunks],
        "dry_samples":dry_rows,
        "failed_dry_samples":failed_dry,
        "water_samples":water_rows,
        "failed_water_samples":failed_water,
        "submerged_sweet_berries":submerged_berries,
        "proximity_flood_runtime_markers":proximity[:100],
        "checks":{
            "reported_cave_samples_not_water":len(failed_dry)==0,
            "real_ocean_control_remains_water":len(failed_water)==0,
            "no_sweet_berries_at_or_below_ocean":len(submerged_berries)==0,
            "proximity_flood_path_absent":len(proximity)==0,
        },
    }
    report["pass"]=all(report["checks"].values())
    target=out/"field-r24-water-seed.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R24 water seed] "+json.dumps({
        "seed":SEED,
        "pass":report["pass"],
        "dry_samples":dry_rows,
        "water_samples":water_rows,
        "submerged_sweet_berries":len(submerged_berries),
    },ensure_ascii=False,sort_keys=True),flush=True)
    require(report["pass"],"R24 water/berry regression failed; see "+str(target))

if __name__=="__main__":
    main()
