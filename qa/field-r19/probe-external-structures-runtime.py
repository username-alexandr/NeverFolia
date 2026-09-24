#!/usr/bin/env python3
"""Bounded runtime QA for imported R19 Overworld structures.

This probe is intentionally diagnostic by default. R19 generation may reject a
vanilla /locate placement candidate when its actual NeverOverworld terrain is
not a dry island. The probe therefore samples several deterministic locate
origins, generates the candidate envelopes, inspects persisted StructureStart
NBT after a normal stop, and then (for discovered surface structures) reloads
the exact piece coverage for a Y128 water-footprint audit.

Use --strict only after the bounded sample has been calibrated for CI.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import time

SEED=-2815737126961128793
SURFACE_IDS=(
    "nova_structures:tavern_oak",
    "explorify:tavern",
    "structory_towers:wizard_tower",
    "repurposed_structures:witch_hut_oak",
    "repurposed_structures:monument_jungle",
    "explorify:ruins",
    "nova_structures:stray_outlook",
    "nova_structures:witch_villa",
    "nova_structures:lone_citadel",
    "nova_structures:toxic_lair",
)
SOURCE_IDS=(
    "structory_towers:ocean_pillar",
    "nova_structures:catacomb",
    "nova_structures:conduit_ruin",
    "nova_structures:trident_trial_monument",
)
ORIGINS=(
    (0,0),(12000,0),(-12000,0),(0,12000),(0,-12000),(12000,12000),
)
AIR={"minecraft:air","minecraft:cave_air","minecraft:void_air"}

def require(ok,message):
    if not ok: raise ValueError("[External Runtime QA] "+message)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,"missing module: "+str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def box_values(raw):
    if isinstance(raw,dict): raw=raw.get("$int_array")
    if isinstance(raw,list) and len(raw)==6 and all(type(v) is int for v in raw):
        return tuple(raw)
    return None

def start_records(roots,target):
    out=[];seen=set()
    for (cx,cz),root in roots.items():
        starts=root.get("structures",{}).get("starts",{})
        if not isinstance(starts,dict): continue
        for value in starts.values():
            if not isinstance(value,dict) or value.get("id")!=target: continue
            boxes=[]
            for child in value.get("Children",[]):
                if not isinstance(child,dict): continue
                box=box_values(child.get("BB"))
                if box is not None: boxes.append(box)
            marker=(target,tuple(boxes))
            if marker in seen: continue
            seen.add(marker)
            out.append({"id":target,"owner_chunk":[cx,cz],"boxes":[list(b) for b in boxes]})
    return out

def candidate_chunks(cx,cz,radius=1):
    return [(x,z) for z in range(cz-radius,cz+radius+1)
                  for x in range(cx-radius,cx+radius+1)]

def piece_coverage(boxes,margin=1):
    chunks=set()
    for raw in boxes:
        box=tuple(raw)
        require(len(box)==6,"bad piece box")
        minx,_,minz,maxx,_,maxz=box
        for cz in range((minz//16)-margin,(maxz//16)+margin+1):
            for cx in range((minx//16)-margin,(maxx//16)+margin+1):
                chunks.add((cx,cz))
    return sorted(chunks)

def water_at_y128(volume,boxes):
    water=0;columns=0;examples=[]
    visited=set()
    for raw in boxes:
        minx,_,minz,maxx,_,maxz=map(int,raw)
        for x in range(minx,maxx+1):
            for z in range(minz,maxz+1):
                if (x,z) in visited: continue
                visited.add((x,z));columns+=1
                state=volume.at(x,128,z)
                if state is not None and state.get("Name")=="minecraft:water":
                    water+=1
                    if len(examples)<24: examples.append([x,128,z])
    return {"columns":columns,"water_columns":water,"examples":examples,"pass":water==0}

def locate_optional(server,target,x,z,timeout=10):
    command=f'execute in minecraft:overworld positioned {x} 200 {z} run locate structure {target}'
    print(f"[External Runtime QA] locate start target={target} origin={x},{z}",flush=True)
    start=len(server.text());server.send(command)
    deadline=time.monotonic()+timeout
    positive=re.compile(re.escape(target)+r'.*?\[\s*(-?\d+)\s*,\s*(~|-?\d+)\s*,\s*(-?\d+)\s*\]')
    not_found=re.compile(r'Could not find a structure of type .*?'+re.escape(target)+r'.*? nearby')
    while time.monotonic()<deadline:
        segment=server.text()[start:]
        match=positive.search(segment)
        if match:
            found=(int(match.group(1)),int(match.group(3)))
            print(f"[External Runtime QA] locate found target={target} xz={found[0]},{found[1]}",flush=True)
            return found
        if not_found.search(segment):
            print(f"[External Runtime QA] locate none target={target} origin={x},{z}",flush=True)
            return None
        require('FoliaWatchdogThread' not in segment,
                f'R19 fast locate exceeded Folia watchdog budget: {target}')
        fatal=re.search(r'Unknown or incomplete command|Incorrect argument|Unknown command',segment)
        require(fatal is None,f'locate command failed: {command}\n{segment[-2000:]}')
        require(server.p.poll() is None,'server exited during external locate')
        time.sleep(.25)
    raise TimeoutError(f'{command}: no locate acknowledgement')

def plan_candidates(server,target):
    seen=set();rows=[]
    for ox,oz in ORIGINS:
        found=locate_optional(server,target,ox,oz)
        if found is None:continue
        x,z=found
        cx,cz=x//16,z//16
        key=(cx,cz)
        if key in seen: continue
        seen.add(key)
        rows.append({"origin":[ox,oz],"located_xz":[x,z],"chunk":[cx,cz]})
    return rows

def make_work(root,overworld,nether):
    work=root/".work"/"external-structures-runtime-qa"
    work.mkdir(parents=True,exist_ok=False)
    packs=work/"world"/"datapacks";packs.mkdir(parents=True)
    shutil.copyfile(overworld,packs/"NeverOverworld.zip")
    shutil.copyfile(nether,packs/"NeverNether.zip")
    (work/"eula.txt").write_text("eula=true\n",encoding="utf-8")
    (work/"server.properties").write_text(
        f"level-name=world\nlevel-seed={SEED}\n"
        "initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n"
        "online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25598\n"
        "view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\n"
        "pause-when-empty-seconds=-1\n",encoding="utf-8")
    return work

def main_run(args):
    root=Path(__file__).resolve().parents[2]
    observer=load("external_runtime_observer",root/"scripts/probe-never-overworld-trees-villages-r1.py")
    paired=load("external_runtime_paired",root/"scripts/probe-never-overworld-paired-r12.py")
    nbt=observer.load_nbt(root);Server=paired.make_server(observer)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    work=make_work(root,args.overworld.resolve(),args.nether.resolve())
    region=work/"world"/"dimensions"/"minecraft"/"overworld"/"region"

    report={"schema":1,"profile":"NeverOverworld-External-Structures-Runtime-QA1",
            "seed":SEED,"strict":args.strict,"targets":{},"pass":False}
    server=Server(args.jar.resolve(),work,out/"external-structures-runtime-discovery.log")
    normal=False
    try:
        server.wait(r"Done \(",timeout=300);server.disable_random_ticks()
        # Runtime generation is required for the behavior NeverFolia changes:
        # surface-land structures moved onto dry islands. Ocean/underground
        # structures deliberately retain source placement and are verified by
        # the separate complete pack-graph QA instead of invoking vanilla
        # /locate, whose synchronous StructureCheck path is outside this change.
        for index,target in enumerate(SURFACE_IDS,1):
            print(f"[External Runtime QA] target {index}/{len(SURFACE_IDS)} begin {target}",flush=True)
            candidates=plan_candidates(server,target)
            require(candidates,"locate produced no candidate within bounded QA origins: "+target)
            print(f"[External Runtime QA] target {index}/{len(SURFACE_IDS)} candidates={len(candidates)} {target}",flush=True)
            selected=set()
            for row in candidates:
                selected.update(candidate_chunks(*row["chunk"],radius=1))
            require(len(selected)<=324,"discovery sample too large for "+target)
            print(f"[External Runtime QA] target {index}/{len(SURFACE_IDS)} loading_chunks={len(selected)} {target}",flush=True)
            server.load_dimension(sorted(selected),"minecraft:overworld",serial_generation=False)
            print(f"[External Runtime QA] target {index}/{len(SURFACE_IDS)} generated {target}",flush=True)
            report["targets"][target]={
                "class":"surface_land",
                "candidates":candidates,"discovery_chunks":[list(p) for p in sorted(selected)],
            }
        code=server.stop();require(code==0,"discovery server stop failed");normal=True
    finally:
        if not normal: server.close()

    # First persisted-start census.
    coverage_requests={}
    for target,item in report["targets"].items():
        chunks=[tuple(p) for p in item["discovery_chunks"]]
        roots={p:nbt.read_chunk_nbt(region,*p) for p in chunks}
        starts=start_records(roots,target)
        item["persisted_starts"]=starts
        item["found"]=bool(starts)
        if starts and target in SURFACE_IDS:
            boxes=starts[0]["boxes"]
            coverage=piece_coverage(boxes,margin=1)
            require(len(coverage)<=324,"piece coverage too large for "+target)
            coverage_requests[target]=coverage
            item["coverage_chunks"]=[list(p) for p in coverage]

    # Load actual surface piece coverage in one restart so Y128 audits use saved FULL chunks.
    if coverage_requests:
        server=Server(args.jar.resolve(),work,out/"external-structures-runtime-coverage.log")
        normal=False
        try:
            server.wait(r"Done \(",timeout=300);server.disable_random_ticks()
            for target,chunks in coverage_requests.items():
                server.load_dimension(chunks,"minecraft:overworld",serial_generation=False)
            code=server.stop();require(code==0,"coverage server stop failed");normal=True
        finally:
            if not normal: server.close()

        for target,chunks in coverage_requests.items():
            roots={p:nbt.read_chunk_nbt(region,*p) for p in chunks}
            volume=observer.Volume(roots)
            start=report["targets"][target]["persisted_starts"][0]
            report["targets"][target]["y128_piece_footprint"]=water_at_y128(volume,start["boxes"])

    surface_found=all(report["targets"][x]["found"] for x in SURFACE_IDS)
    surface_dry=all(
        report["targets"][x].get("y128_piece_footprint",{}).get("pass") is True
        for x in SURFACE_IDS if report["targets"][x]["found"]
    )
    report["source_placement_static_qa"]={
        "ids":list(SOURCE_IDS),
        "policy":"unchanged source placement is validated by validate-external-structures-pack.py",
        "runtime_locate_skipped":True,
    }
    report["checks"]={
        "surface_representatives_found":surface_found,
        "found_surface_footprints_dry_at_y128":surface_dry,
        "source_placement_delegated_to_complete_static_graph_qa":True,
    }
    report["pass"]=surface_found and surface_dry
    target=out/"external-structures-runtime-qa.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("[External Runtime QA] "+json.dumps({
        "pass":report["pass"],"checks":report["checks"],
        "found":{k:v["found"] for k,v in report["targets"].items()},
    },ensure_ascii=False,sort_keys=True),flush=True)
    if args.strict: require(report["pass"],"runtime dungeon QA rejected; see "+str(target))

def self_test():
    roots={
        (1,2):{"structures":{"starts":{"x":{"id":"explorify:tavern","Children":[
            {"BB":{"$int_array":[16,129,32,31,140,47]}},
            {"BB":{"$int_array":[32,129,32,40,140,47]}},
        ]}}}},
        (2,2):{"structures":{"starts":{"x":{"id":"explorify:tavern","Children":[
            {"BB":{"$int_array":[16,129,32,31,140,47]}},
            {"BB":{"$int_array":[32,129,32,40,140,47]}},
        ]}}}},
    }
    rows=start_records(roots,"explorify:tavern")
    require(len(rows)==1,"SELF-TEST duplicate starts not deduplicated")
    cov=piece_coverage(rows[0]["boxes"],margin=1)
    require((1,2) in cov and (2,2) in cov,"SELF-TEST piece coverage missing owner chunks")
    require(len(candidate_chunks(0,0))==9,"SELF-TEST discovery envelope must be 3x3")
    require(len(SURFACE_IDS)==10 and len(SOURCE_IDS)==4,"SELF-TEST representative set drifted")
    require(locate_optional.__defaults__==(10,),"SELF-TEST locate timeout must stay bounded to 10s")
    print("[NeverFolia][External Runtime QA] SELF-TEST OK")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jar",type=Path)
    p.add_argument("--overworld",type=Path)
    p.add_argument("--nether",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--strict",action="store_true")
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:self_test();return
    for name in ("jar","overworld","nether","output"):
        if getattr(a,name.replace("-","_")) is None:p.error("--"+name+" is required")
    main_run(a)

if __name__=="__main__":main()
