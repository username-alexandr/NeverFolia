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
SURFACE_GROUPS={
    "dungeons_and_taverns":(
        "nova_structures:witch_villa",
        "nova_structures:stray_outlook",
        "nova_structures:wild_ruin",
        "nova_structures:firewatch_tower_forest",
        "nova_structures:tavern_oak",
    ),
    "explorify":(
        "explorify:tavern",
        "explorify:ruins",
        "explorify:farmstead",
        "explorify:campsite",
    ),
    "structory_towers":(
        # wizard_tower is intentionally not used as a runtime representative:
        # its source biome tag contains only optional Terralith biomes, so it
        # legitimately has no vanilla NeverOverworld candidate. Prefer source
        # variants with explicit vanilla biome coverage.
        "structory_towers:taiga_outpost",
        "structory_towers:lighthouse",
        "structory_towers:warped_greatsword",
        "structory_towers:small_firetower",
        "structory_towers:farmer_outpost",
        "structory_towers:foraging_outpost",
        "structory_towers:quarter_outpost",
        "structory_towers:nomad_outpost",
        "structory_towers:engineer_tower",
        "structory_towers:overgrown_mangrove",
        "structory_towers:ancient_temple",
        "structory_towers:great_toadstool",
    ),
    "better_witch_huts":(
        "repurposed_structures:witch_hut_oak",
        "repurposed_structures:witch_hut_birch",
        "repurposed_structures:witch_hut_taiga",
        "repurposed_structures:witch_hut_dark_forest",
        "repurposed_structures:witch_hut_mangrove",
        "repurposed_structures:witch_hut_giant_tree_taiga",
    ),
    "better_monuments":(
        "repurposed_structures:monument_desert",
        "repurposed_structures:monument_jungle",
        "repurposed_structures:monument_icy",
    ),
}
SURFACE_IDS=tuple(dict.fromkeys(
    target for group in SURFACE_GROUPS.values() for target in group
))
SOURCE_IDS=(
    "structory_towers:ocean_pillar",
    "nova_structures:catacomb",
    "nova_structures:conduit_ruin",
    "nova_structures:trident_trial_monument",
    "nova_structures:lone_citadel",
    "nova_structures:toxic_lair",
)
ORIGINS=(
    (0,0),
    (12000,0),(-12000,0),(0,12000),(0,-12000),
    (12000,12000),(-12000,12000),(12000,-12000),(-12000,-12000),
    (24000,0),(-24000,0),(0,24000),(0,-24000),
)
AIR={"minecraft:air","minecraft:cave_air","minecraft:void_air"}
MAX_GROUP_TARGET_CANDIDATES=2
BIOME_HINT_ORIGINS=((0,0),(24000,0),(-24000,0),(0,24000),(0,-24000))
TARGET_BIOME_HINTS={
    "repurposed_structures:monument_desert":("minecraft:desert",),
    "repurposed_structures:monument_jungle":("minecraft:jungle","minecraft:sparse_jungle"),
    "repurposed_structures:monument_icy":("minecraft:snowy_plains","minecraft:grove"),
}

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

def locate_biome_optional(server,target,x,z,timeout=15):
    command=f'execute in minecraft:overworld positioned {x} 200 {z} run locate biome {target}'
    print(f"[External Runtime QA] biome locate start target={target} origin={x},{z}",flush=True)
    start=len(server.text());server.send(command)
    deadline=time.monotonic()+timeout
    positive=re.compile(re.escape(target)+r'.*?\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]')
    not_found=re.compile(r'Could not find a biome of type .*?'+re.escape(target)+r'.*? nearby')
    while time.monotonic()<deadline:
        segment=server.text()[start:]
        match=positive.search(segment)
        if match:
            found=(int(match.group(1)),int(match.group(3)))
            print(f"[External Runtime QA] biome locate found target={target} xz={found[0]},{found[1]}",flush=True)
            return found
        if not_found.search(segment):
            print(f"[External Runtime QA] biome locate none target={target} origin={x},{z}",flush=True)
            return None
        fatal=re.search(r'Unknown or incomplete command|Incorrect argument|Unknown command',segment)
        require(fatal is None,f'biome locate command failed: {command}\n{segment[-2000:]}')
        require(server.p.poll() is None,'server exited during biome locate')
        time.sleep(.25)
    raise TimeoutError(f'{command}: no biome locate acknowledgement')

def hinted_origins(server,target):
    hints=TARGET_BIOME_HINTS.get(target)
    if not hints:
        return ORIGINS
    located=[]
    seen=set()
    for biome in hints:
        for ox,oz in BIOME_HINT_ORIGINS:
            found=locate_biome_optional(server,biome,ox,oz)
            if found is None: continue
            if found not in seen:
                seen.add(found);located.append(found)
            break
    # Keep the broad deterministic origins as fallback. Biome-local positions
    # are tried first so rare monument variants are not rejected simply because
    # the QA origins sit in unrelated climates.
    for origin in ORIGINS:
        if origin not in seen:
            seen.add(origin);located.append(origin)
    return tuple(located)

def plan_candidates(server,target,origins=None):
    # Runtime QA needs one real persisted start, not an exhaustive locate
    # census. Stop on the first distinct bounded candidate so one rare structure
    # cannot turn this gate into a long-running world scan.
    origins=ORIGINS if origins is None else origins
    for ox,oz in origins:
        found=locate_optional(server,target,ox,oz)
        if found is None:continue
        x,z=found
        return [{"origin":[ox,oz],"located_xz":[x,z],"chunk":[x//16,z//16]}]
    return []

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
        for group_index,(group,targets) in enumerate(SURFACE_GROUPS.items(),1):
            attempts=[]
            chosen=[]
            for target in targets:
                print(
                    f"[External Runtime QA] group {group_index}/{len(SURFACE_GROUPS)} "
                    f"{group} try {target}",
                    flush=True
                )
                origins=hinted_origins(server,target)
                candidates=plan_candidates(server,target,origins)
                attempts.append({
                    "target":target,
                    "candidate_count":len(candidates),
                    "probe_origin_count":len(origins),
                    "biome_hints":list(TARGET_BIOME_HINTS.get(target,())),
                })
                if candidates:
                    chosen.append((target,candidates))
                    if len(chosen)>=MAX_GROUP_TARGET_CANDIDATES:
                        break
            require(chosen,
                    "no bounded natural candidate for source group: "+group)

            for target_index,(target,candidates) in enumerate(chosen,1):
                print(
                    f"[External Runtime QA] group {group_index}/{len(SURFACE_GROUPS)} "
                    f"{group} selected {target_index}/{len(chosen)}={target} "
                    f"candidates={len(candidates)}",
                    flush=True
                )
                selected=set()
                for row in candidates:
                    selected.update(candidate_chunks(*row["chunk"],radius=1))
                require(len(selected)<=324,"discovery sample too large for "+target)
                print(
                    f"[External Runtime QA] group {group} loading_chunks={len(selected)} "
                    f"target={target}",
                    flush=True
                )
                server.load_dimension(sorted(selected),"minecraft:overworld",serial_generation=False)
                print(f"[External Runtime QA] group {group} generated {target}",flush=True)
                report["targets"][target]={
                    "class":"surface_land",
                    "source_group":group,
                    "attempts":attempts,
                    "candidates":candidates,
                    "discovery_chunks":[list(p) for p in sorted(selected)],
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

    groups_found={
        group:any(
            item.get("source_group")==group and item.get("found")
            for item in report["targets"].values()
        )
        for group in SURFACE_GROUPS
    }
    surface_found=all(groups_found.values())
    surface_dry=all(
        item.get("y128_piece_footprint",{}).get("pass") is True
        for item in report["targets"].values() if item.get("found")
    )
    report["source_placement_static_qa"]={
        "ids":list(SOURCE_IDS),
        "policy":"unchanged source placement is validated by validate-external-structures-pack.py",
        "runtime_locate_skipped":True,
    }
    report["checks"]={
        "surface_source_groups_found":groups_found,
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
    require(len(ORIGINS)==13,"SELF-TEST bounded locate origin set drifted")
    require(len(SURFACE_GROUPS)==5 and len(SOURCE_IDS)==6,"SELF-TEST source group set drifted")
    require(MAX_GROUP_TARGET_CANDIDATES==2,"SELF-TEST per-group runtime sample width drifted")
    require(set(TARGET_BIOME_HINTS)=={
        "repurposed_structures:monument_desert",
        "repurposed_structures:monument_jungle",
        "repurposed_structures:monument_icy",
    },"SELF-TEST Better Monuments biome hints drifted")
    require(len(BIOME_HINT_ORIGINS)==5,"SELF-TEST biome hint origin set drifted")
    require(all(SURFACE_GROUPS.values()),"SELF-TEST each source group needs candidates")
    require(len(set(SURFACE_IDS))==len(SURFACE_IDS),"SELF-TEST duplicate runtime candidates")
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
