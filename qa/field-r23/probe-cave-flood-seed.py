#!/usr/bin/env python3
"""FIELD-R23 regression for user-reported sealed-cave overflooding."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

SEED=-4193070274438815849
# Block positions read from the user's F3 screenshots. These are internal cave
# samples that were WATER in RC1 but must remain dry without a proven ocean path.
DRY_SAMPLES=(
    (-2284,9,-1443),
    (-2297,46,-1438),
    (-2275,-9,-1445),
    (-2272,-13,-1442),
)
AIR={"minecraft:air","minecraft:cave_air","minecraft:void_air"}

def require(ok,message):
    if not ok: raise ValueError("[FIELD-R23 cave seed] "+message)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,"missing module: "+str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def sample_chunks():
    centers={(x//16,z//16) for x,_,z in DRY_SAMPLES}
    chunks=set()
    for cx,cz in centers:
        for dx in range(-1,2):
            for dz in range(-1,2):
                chunks.add((cx+dx,cz+dz))
    return sorted(chunks)

def state_name(state):
    if state is None:return None
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
    observer=load("field_r23_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("field_r23_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r23-cave-seed"
    if work.exists():shutil.rmtree(work)
    packs=work/"world/datapacks";packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25596\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",encoding="utf-8")

    chunks=sample_chunks()
    log=out/"field-r23-cave-seed-server.log"
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

    rows=[]
    failed=[]
    for x,y,z in DRY_SAMPLES:
        state=state_name(volume.at(x,y,z))
        row={"pos":[x,y,z],"state":state,"dry":state!="minecraft:water"}
        rows.append(row)
        if not row["dry"]:failed.append(row)

    text=log.read_text(encoding="utf-8",errors="replace")
    proximity_lines=[line.strip() for line in text.splitlines() if "[NeverFolia][R22ProximityFlood]" in line]
    report={
        "schema":1,
        "profile":"FIELD-R23-CAVE-SEED-1",
        "source_sha":a.source_sha,
        "seed":SEED,
        "jar_sha256":sha(a.jar),
        "overworld_sha256":sha(a.overworld),
        "nether_sha256":sha(a.nether),
        "chunks":[list(x) for x in chunks],
        "dry_samples":rows,
        "failed_samples":failed,
        "proximity_flood_runtime_markers":proximity_lines[:100],
        "checks":{
            "user_reported_cave_samples_not_water":len(failed)==0,
            "proximity_flood_path_absent":len(proximity_lines)==0,
        },
    }
    report["pass"]=all(report["checks"].values())
    target=out/"field-r23-cave-seed.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R23 cave seed] "+json.dumps({
        "seed":SEED,"pass":report["pass"],"dry_samples":rows,
        "proximity_markers":len(proximity_lines)
    },ensure_ascii=False,sort_keys=True),flush=True)
    require(report["pass"],"sealed-cave overflood regression failed; see "+str(target))

if __name__=="__main__":main()
