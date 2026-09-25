#!/usr/bin/env python3
"""Static QA for the merged R19 external Overworld structure graph."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

MANIFEST="neveroverworld-external-structures-r19.json"
PROFILE="NeverOverworld-External-Structures-R19"
QA_PROFILE="NeverOverworld-External-Structures-QA1"
EXTERNAL_NAMESPACES={"nova_structures","explorify","structory_towers","repurposed_structures"}
SURFACE_PROJECTIONS={"WORLD_SURFACE_WG","WORLD_SURFACE","MOTION_BLOCKING_NO_LEAVES"}
DNT_SAFE_RUNTIME_FUNCTIONS={
    "nova_structures:jockey/spawn_bogged_horseman",
    "nova_structures:jockey/spawn_camel_husk_jockey",
    "nova_structures:jockey/spawn_chicken_jockey",
    "nova_structures:jockey/spawn_hoglin_jockey",
    "nova_structures:jockey/spawn_ravager_jockey",
    "nova_structures:jockey/spawn_skeleton_horseman",
    "nova_structures:jockey/spawn_stray_horseman",
    "nova_structures:jockey/spawn_zautilus_jockey",
    "nova_structures:jockey/spawn_zombie_horseman",
    "nova_structures:spawn_cave_spider_minion",
    "nova_structures:spawn_guardian_minion",
    "nova_structures:spawn_spider_minion",
}
REPRESENTATIVES={
    "surface_land":[
        "nova_structures:tavern_oak",
        "explorify:tavern",
        "structory_towers:wizard_tower",
        "repurposed_structures:witch_hut_oak",
        "repurposed_structures:monument_jungle",
        "explorify:ruins",
        "nova_structures:stray_outlook",
        "nova_structures:witch_villa",
    ],
    "source_placement":[
        "structory_towers:ocean_pillar",
        "nova_structures:catacomb",
        "nova_structures:conduit_ruin",
        "nova_structures:trident_trial_monument",
        "nova_structures:lone_citadel",
        "nova_structures:toxic_lair",
    ],
}

def fail(message:str)->None:
    raise ValueError("[NeverFolia][External Structures QA] "+message)

def resource_id(path:str,family:str)->str|None:
    m=re.fullmatch(r"data/([^/]+)/"+re.escape(family)+r"/(.+)\.json",path)
    return f"{m.group(1)}:{m.group(2)}" if m else None

def read_json(archive:zipfile.ZipFile,name:str)->dict:
    try:value=json.loads(archive.read(name).decode("utf-8"))
    except Exception as exc:fail(f"invalid JSON {name}: {exc}")
    if not isinstance(value,dict):fail("JSON root must be an object: "+name)
    return value

def collect_run_function_refs(value)->set[str]:
    refs=set()
    def walk(node):
        if isinstance(node,dict):
            t=node.get("type")
            fn=node.get("function")
            if t in ("minecraft:run_function","run_function") and isinstance(fn,str):
                refs.add(fn)
            for child in node.values(): walk(child)
        elif isinstance(node,list):
            for child in node: walk(child)
    walk(value)
    return refs

def function_path_candidates(resource_id:str)->tuple[str,str]:
    if ":" in resource_id:
        namespace,path=resource_id.split(":",1)
    else:
        namespace,path="minecraft",resource_id
    return (
        f"data/{namespace}/function/{path}.mcfunction",
        f"data/{namespace}/functions/{path}.mcfunction",
    )

def expected_unused(spec_path:Path)->set[str]:
    data=json.loads(spec_path.read_text(encoding="utf-8"))
    raw=data.get("source_unused_structures",{})
    if not isinstance(raw,dict):fail("spec source_unused_structures must be an object")
    result=set(raw)
    if len(result)!=4:fail(f"expected four pinned D&T source-unused structures, got {len(result)}")
    return result

def audit(pack:Path,spec_path:Path)->dict:
    expected=expected_unused(spec_path)
    spec=json.loads(spec_path.read_text(encoding="utf-8"))
    expected_radii=spec.get("island_radii",{})
    if not isinstance(expected_radii,dict) or len(expected_radii)!=134:
        fail("spec island radius table must contain 134 IDs")
    with zipfile.ZipFile(pack) as archive:
        bad=archive.testzip()
        if bad is not None:fail("corrupt ZIP entry: "+bad)
        names=set(archive.namelist())
        if MANIFEST not in names:fail("R19 external structures manifest missing")
        manifest=read_json(archive,MANIFEST)
        if manifest.get("profile")!=PROFILE:fail("wrong R19 manifest profile")
        if manifest.get("minecraft_namespace_overrides_imported") is not False:
            fail("external merge must not import minecraft structure overrides")

        admission=manifest.get("island_admission",{})
        radii=admission.get("radii",{})
        if admission.get("min_surface_y")!=129:fail("island surface floor must remain Y129")
        if not isinstance(radii,dict) or len(radii)!=134:fail("R19 island radius table must contain 134 IDs")
        if radii!=expected_radii:fail("manifest/runtime island radius table drifted from checked-in spec")
        if admission.get("structure_count")!=len(radii):fail("manifest island structure_count mismatch")
        island=set(radii)

        run_function_refs=set()
        for name in names:
            if not name.endswith(".json"): continue
            try:
                payload=json.loads(archive.read(name).decode("utf-8"))
            except Exception as exc:
                fail(f"invalid JSON {name}: {exc}")
            run_function_refs |= collect_run_function_refs(payload)
        external_run_functions={
            rid for rid in run_function_refs if not rid.startswith("minecraft:")
        }
        unexpected_run_functions=sorted(external_run_functions-DNT_SAFE_RUNTIME_FUNCTIONS)
        missing_run_functions=sorted(DNT_SAFE_RUNTIME_FUNCTIONS-external_run_functions)
        if unexpected_run_functions:
            fail("unexpected D&T run_function effects survived: "+repr(unexpected_run_functions[:40]))
        if missing_run_functions:
            fail("safe D&T mob controller effects missing: "+repr(missing_run_functions[:40]))
        unresolved_functions=[]
        for rid in sorted(external_run_functions):
            if not any(candidate in names for candidate in function_path_candidates(rid)):
                unresolved_functions.append(rid)
        if unresolved_functions:
            fail("safe D&T runtime function closure broken: "+repr(unresolved_functions[:40]))

        imported_external_functions=sorted(
            name for name in names
            if ("/function/" in name or "/functions/" in name)
            and name.startswith("data/nova_structures/")
            and name.endswith(".mcfunction")
        )
        imported_function_ids=set()
        for name in imported_external_functions:
            m=re.fullmatch(r"data/([^/]+)/(?:function|functions)/(.+)\\.mcfunction",name)
            if m: imported_function_ids.add(f"{m.group(1)}:{m.group(2)}")
        if imported_function_ids!=DNT_SAFE_RUNTIME_FUNCTIONS:
            fail(
                "D&T runtime import differs from safe allowlist: missing="
                +repr(sorted(DNT_SAFE_RUNTIME_FUNCTIONS-imported_function_ids)[:40])
                +" unexpected="+repr(sorted(imported_function_ids-DNT_SAFE_RUNTIME_FUNCTIONS)[:40])
            )

        structures={}
        sets={}
        for name in names:
            sid=resource_id(name,"worldgen/structure")
            if sid is not None:
                structures[sid]=read_json(archive,name);continue
            setid=resource_id(name,"worldgen/structure_set")
            if setid is not None:sets[setid]=read_json(archive,name)

        external={sid for sid in structures if sid.split(":",1)[0] in EXTERNAL_NAMESPACES}
        missing_island=sorted(island-external)
        if missing_island:fail("island table references missing structure JSON: "+repr(missing_island[:20]))

        refs=defaultdict(list)
        missing_refs=[]
        for setid,payload in sets.items():
            entries=payload.get("structures",[])
            if not isinstance(entries,list):fail("structure_set entries must be a list: "+setid)
            for entry in entries:
                if not isinstance(entry,dict) or not isinstance(entry.get("structure"),str):continue
                sid=entry["structure"];refs[sid].append(setid)
                ns=sid.split(":",1)[0] if ":" in sid else "minecraft"
                if ns in EXTERNAL_NAMESPACES and sid not in structures:
                    missing_refs.append({"set":setid,"structure":sid})
        if missing_refs:fail("structure_set references missing external structure JSON: "+repr(missing_refs[:20]))

        bad_surface=[]
        for sid in sorted(island):
            payload=structures[sid]
            if payload.get("step")!="surface_structures" or payload.get("project_start_to_heightmap") not in SURFACE_PROJECTIONS:
                bad_surface.append({"id":sid,"step":payload.get("step"),"projection":payload.get("project_start_to_heightmap")})
        if bad_surface:fail("island classification drifted: "+repr(bad_surface[:20]))
        for sid in ("nova_structures:lone_citadel","nova_structures:toxic_lair"):
            payload=structures.get(sid,{})
            if payload.get("step")!="underground_decoration":
                fail("D&T underground source intent drifted: "+sid)
            if sid in island:
                fail("D&T underground structure was incorrectly island-adapted: "+sid)
        for sid in ("explorify:ruins","nova_structures:stray_outlook","nova_structures:witch_villa"):
            payload=structures.get(sid,{})
            if payload.get("project_start_to_heightmap")!="WORLD_SURFACE_WG":
                fail("land structure still uses drowned-floor projection: "+sid)
        villa=structures.get("nova_structures:witch_villa",{})
        if villa.get("start_height")!={"absolute":0}:
            fail("witch_villa vanilla-sea absolute height survived")

        reps={}
        for group,ids in REPRESENTATIVES.items():
            rows=[]
            for sid in ids:
                if sid not in structures:fail("representative structure missing: "+sid)
                placements=sorted(refs.get(sid,[]))
                if not placements:fail("representative structure has no natural structure_set: "+sid)
                expected_island=group=="surface_land"
                if (sid in island)!=expected_island:fail("representative island classification mismatch: "+sid)
                payload=structures[sid]
                rows.append({
                    "id":sid,"structure_sets":placements,"island_adapted":sid in island,
                    "step":payload.get("step"),"projection":payload.get("project_start_to_heightmap"),
                })
            reps[group]=rows

        unreferenced=sorted(sid for sid in external if not refs.get(sid))
        unreferenced_island=sorted(sid for sid in island if not refs.get(sid))
        if set(unreferenced)!=expected or set(unreferenced_island)!=expected:
            fail("source placement coverage drifted: "+repr(unreferenced))

        manifest_unused=set(manifest.get("source_unused_structures",[]))
        if manifest_unused!=expected:fail("builder manifest source_unused_structures drifted")
        if admission.get("spawnable_structure_count")!=len(island-expected):
            fail("builder manifest spawnable island count drifted")

        return {
            "schema":1,"profile":QA_PROFILE,"source_profile":PROFILE,"pack":pack.name,
            "counts":{
                "all_structure_json":len(structures),
                "external_structure_json":len(external),
                "island_adapted":len(island),
                "spawnable_island":len(island-expected),
                "source_placement":len(external-island),
                "spawnable_external":len(external-expected),
                "structure_sets":len(sets),
                "source_unused":len(expected),
                "run_function_refs":len(run_function_refs),
                "imported_external_functions":len(imported_external_functions),
            },
            "source_unused":sorted(expected),
            "representatives":reps,
            "runtime_probe_plan":{
                "seed":-2815737126961128793,
                "surface_land":REPRESENTATIVES["surface_land"],
                "source_placement":REPRESENTATIVES["source_placement"],
                "surface_assertion":"persisted start on dry island; Y128 water must not intersect sampled piece footprint",
                "untouched_assertion":"source placement class unchanged",
            },
            "pass":True,
        }

def synthetic_pack(path:Path,spec_path:Path)->None:
    unused=expected_unused(spec_path)
    surface=list(REPRESENTATIVES["surface_land"])
    untouched=list(REPRESENTATIVES["source_placement"])
    policy=json.loads(spec_path.read_text(encoding="utf-8")).get("island_radii",{})
    island=sorted(policy)
    radii=dict(policy)
    manifest={
        "profile":PROFILE,"minecraft_namespace_overrides_imported":False,
        "source_unused_structures":sorted(unused),
        "island_admission":{
            "min_surface_y":129,"structure_count":134,
            "spawnable_structure_count":134-len(unused),"radii":radii,
        },
    }
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST,json.dumps(manifest))
        for sid in island:
            ns,name=sid.split(":",1)
            z.writestr(f"data/{ns}/worldgen/structure/{name}.json",json.dumps({
                "step":"surface_structures",
                "start_height":{"absolute":0},
                "project_start_to_heightmap":"WORLD_SURFACE_WG",
            }))
        for sid in untouched:
            ns,name=sid.split(":",1)
            if sid=="nova_structures:catacomb":
                payload={"step":"underground_structures"}
            elif sid=="nova_structures:lone_citadel":
                payload={"step":"underground_decoration","start_height":{"absolute":106}}
            elif sid=="nova_structures:toxic_lair":
                payload={"step":"underground_decoration","start_height":{"absolute":67}}
            else:
                payload={"step":"surface_structures","project_start_to_heightmap":"OCEAN_FLOOR_WG"}
            z.writestr(f"data/{ns}/worldgen/structure/{name}.json",json.dumps(payload))
        spawnable=[sid for sid in island if sid not in unused]+untouched
        z.writestr("data/neverfolia/worldgen/structure_set/qa.json",json.dumps({
            "placement":{"type":"minecraft:random_spread","spacing":32,"separation":8,"salt":1},
            "structures":[{"structure":sid,"weight":1} for sid in spawnable],
        }))

def self_test(spec_path:Path)->None:
    with tempfile.TemporaryDirectory(prefix="nr-external-qa-") as tmp:
        pack=Path(tmp)/"pack.zip";synthetic_pack(pack,spec_path)
        result=audit(pack,spec_path)
        if not result["pass"] or result["counts"]["spawnable_island"]!=130:
            fail("SELF-TEST valid synthetic pack rejected")
    print("[NeverFolia][External Structures QA] SELF-TEST OK")

def main()->None:
    root=Path(__file__).resolve().parents[2]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pack",type=Path)
    p.add_argument("--spec",type=Path,default=root/"worldgen-spec/never-overworld-external-structures-r19.json")
    p.add_argument("--output",type=Path)
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    spec=a.spec.resolve()
    if a.self_test:self_test(spec);return
    if a.pack is None:p.error("--pack is required")
    result=audit(a.pack.resolve(),spec)
    if a.output is not None:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__":main()
