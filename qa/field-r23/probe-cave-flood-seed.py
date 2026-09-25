#!/usr/bin/env python3
"""R23 regression: sealed caves must stay dry unless truly ocean-connected."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil

SEED = -4193070274438815849

# Manual QA screenshots from 2026-09-25. These positions were visibly inside
# flooded underground cave volumes on RC1, despite not being direct ocean
# openings. R23 must leave them non-water on a newly generated world.
DRY_POINTS = (
    (-2284, 9, -1443),
    (-2296, 46, -1438),
    (-2275, -8, -1445),
    (-2272, -13, -1442),
)

# Positive control from the same manual session: this point is in the actual
# submerged/ocean volume near the monument and must remain water.
OCEAN_POINTS = (
    (-2251, 111, -1335),
)

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R23 cave flood] " + message)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, "missing module: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state_name(state) -> str | None:
    return state.get("Name") if isinstance(state, dict) else None


def chunk_of(x: int, z: int) -> tuple[int, int]:
    return x // 16, z // 16


def expanded_chunks() -> list[tuple[int, int]]:
    out=set()
    for x,_,z in DRY_POINTS + OCEAN_POINTS:
        cx,cz=chunk_of(x,z)
        for dx in range(-1,2):
            for dz in range(-1,2):
                out.add((cx+dx,cz+dz))
    return sorted(out)


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar",type=Path,required=True)
    p.add_argument("--overworld",type=Path,required=True)
    p.add_argument("--nether",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()

    root=Path(__file__).resolve().parents[2]
    observer=load("r23_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("r23_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    nbt=observer.load_nbt(root)
    Server=paired.make_server(observer)

    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    work=root/".work/field-r23-cave-flood"
    require(not work.exists(),"work directory already exists")
    packs=work/"world/datapacks"
    packs.mkdir(parents=True)
    shutil.copyfile(a.overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(a.nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n",encoding="utf-8")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25596\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",
        encoding="utf-8",
    )

    chunks=expanded_chunks()
    log=out/"field-r23-cave-flood-server.log"
    server=Server(a.jar.resolve(),work,log,java_args=["-Dneverfolia.debugFloodSeams=true"])
    normal=False
    try:
        server.wait(r"Done \\(",timeout=300)
        server.disable_random_ticks()
        server.load_dimension(chunks,"minecraft:overworld",dwell=7,serial_generation=False)
        code=server.stop()
        require(code==0,"server stop failed")
        normal=True
    finally:
        if not normal:
            server.close()

    region=work/"world/dimensions/minecraft/overworld/region"
    roots={p:nbt.read_chunk_nbt(region,*p) for p in chunks}
    volume=observer.Volume(roots)

    dry=[]
    for x,y,z in DRY_POINTS:
        name=state_name(volume.at(x,y,z))
        dry.append({"pos":[x,y,z],"state":name,"pass":name!="minecraft:water"})

    ocean=[]
    for x,y,z in OCEAN_POINTS:
        name=state_name(volume.at(x,y,z))
        ocean.append({"pos":[x,y,z],"state":name,"pass":name=="minecraft:water"})

    report={
        "schema":1,
        "profile":"FIELD-R23-SEALED-CAVE-1",
        "source_sha":a.source_sha,
        "seed":SEED,
        "dry_points":dry,
        "ocean_points":ocean,
        "pass":all(x["pass"] for x in dry+ocean),
        "notes":[
            "Dry points come from manual RC1 screenshots where sealed caves were incorrectly flooded.",
            "Positive ocean control prevents fixing the bug by globally suppressing flood water.",
            "This regression is for newly generated chunks only.",
        ],
    }
    target=out/"field-r23-cave-flood.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[FIELD-R23 cave flood] "+json.dumps(report,ensure_ascii=False,sort_keys=True),flush=True)
    require(report["pass"],"sealed-cave regression failed; see "+str(target))


if __name__=="__main__":
    main()
