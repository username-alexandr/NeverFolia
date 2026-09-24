#!/usr/bin/env python3
"""Audit the pinned Better Monuments v7 source and NeverFolia R19 conversion."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, zipfile
from pathlib import Path

EXPECTED_SHA256="c76cd5ab549974b051a352a633abd2f78a916acc40392bc53ba0581c3116a8c9"
EXPECTED_STRUCTURES={
    "repurposed_structures:monument_desert",
    "repurposed_structures:monument_icy",
    "repurposed_structures:monument_jungle",
}
EXPECTED_BIOMES={
    "repurposed_structures:monument_desert":{"minecraft:desert"},
    "repurposed_structures:monument_icy":{
        "minecraft:snowy_plains","minecraft:ice_spikes","minecraft:snowy_slopes",
        "minecraft:frozen_peaks","minecraft:jagged_peaks","minecraft:grove",
    },
    "repurposed_structures:monument_jungle":{
        "minecraft:jungle","minecraft:sparse_jungle","minecraft:bamboo_jungle",
    },
}

def require(ok:bool,msg:str)->None:
    if not ok: raise ValueError("[Monuments R19 QA] "+msg)

def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def read_json(z:zipfile.ZipFile,name:str)->dict:
    require(name in z.namelist(),"missing JSON: "+name)
    value=json.loads(z.read(name).decode("utf-8"))
    require(isinstance(value,dict),"JSON root must be object: "+name)
    return value

def rid_from_path(path:str,family:str)->str|None:
    prefix="data/"
    if not path.startswith(prefix) or not path.endswith(".json"): return None
    rest=path[len(prefix):]
    parts=rest.split("/",2)
    if len(parts)!=3 or parts[1]!=family:return None
    return parts[0]+":"+parts[2][:-5]

def collect_pool_locations(payload:dict)->set[str]:
    out=set()
    for row in payload.get("elements",[]):
        if not isinstance(row,dict):continue
        el=row.get("element")
        if not isinstance(el,dict):continue
        location=el.get("location")
        if isinstance(location,str):out.add(location)
    return out

def location_to_nbt(location:str)->str:
    ns,path=location.split(":",1)
    return f"data/{ns}/structure/{path}.nbt"

def audit(source:Path,builder:Path,output:Path|None)->dict:
    raw=source.read_bytes()
    require(sha(raw)==EXPECTED_SHA256,"source ZIP SHA mismatch: "+sha(raw))
    spec=importlib.util.spec_from_file_location("r19_builder",builder)
    require(spec is not None and spec.loader is not None,"cannot import R19 builder")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

    files=module.flatten_zip(raw)
    converted,allowed,land,radii,unused=module.filter_pack("monuments",files)
    require(set(allowed)==EXPECTED_STRUCTURES,
            "source Overworld monument set drifted: "+repr(sorted(allowed)))
    require(set(land)==EXPECTED_STRUCTURES,"all three monument variants must be source-land")
    require(not unused,"converted monuments unexpectedly source-unused: "+repr(unused))

    report={
        "schema":1,
        "profile":"NeverOverworld-R19-Better-Monuments-QA1",
        "source_sha256":sha(raw),
        "structures":{},
        "source_templates":0,
        "converted_templates":0,
        "converted_processor_types":[],
        "dropped_legacy_features":0,
        "pass":False,
    }

    source_templates={n:b for n,b in files.items()
                      if n.startswith("data/betteroceanmonuments/structure/") and n.endswith(".nbt")}
    converted_templates={n:b for n,b in converted.items()
                         if n.startswith("data/betteroceanmonuments/structure/") and n.endswith(".nbt")}
    require(source_templates,"source contains no Better Monuments NBT templates")
    require(set(source_templates)==set(converted_templates),
            "converted pack lost/added Better Monuments NBT templates")
    for name,data in source_templates.items():
        require(converted_templates[name]==data,"converted monument NBT changed bytes: "+name)
    report["source_templates"]=len(source_templates)
    report["converted_templates"]=len(converted_templates)

    processor_types=set()
    for name,data in converted.items():
        if "/worldgen/processor_list/" not in name or not name.endswith(".json"):continue
        payload=json.loads(data.decode("utf-8"))
        for proc in payload.get("processors",[]):
            if isinstance(proc,dict) and isinstance(proc.get("processor_type"),str):
                processor_types.add(proc["processor_type"])
    require(all(t.startswith("minecraft:") for t in processor_types),
            "non-vanilla processor survived: "+repr(sorted(processor_types)))
    report["converted_processor_types"]=sorted(processor_types)

    legacy_features=[n for n in files if n.startswith("data/betteroceanmonuments/worldgen/")
                     and ("/configured_feature/" in n or "/placed_feature/" in n)]
    converted_legacy=[n for n in converted if n.startswith("data/betteroceanmonuments/worldgen/")
                      and ("/configured_feature/" in n or "/placed_feature/" in n)]
    require(not converted_legacy,"legacy Better Monuments feature registry survived conversion")
    report["dropped_legacy_features"]=len(legacy_features)

    # Every surviving converted pool location must resolve to a copied NBT template.
    unresolved=[]
    for name,data in converted.items():
        if "/worldgen/template_pool/" not in name or not name.endswith(".json"):continue
        payload=json.loads(data.decode("utf-8"))
        for location in collect_pool_locations(payload):
            if ":" not in location:continue
            if location.startswith("minecraft:"):continue
            nbt=location_to_nbt(location)
            if nbt not in converted:
                unresolved.append({"pool":name,"location":location,"expected_nbt":nbt})
    require(not unresolved,"converted pool references missing NBT: "+repr(unresolved[:20]))

    for sid in sorted(EXPECTED_STRUCTURES):
        ns,path=sid.split(":",1)
        name=f"data/{ns}/worldgen/structure/{path}.json"
        payload=json.loads(converted[name].decode("utf-8"))
        require(payload.get("type")=="minecraft:jigsaw",sid+" not converted to vanilla jigsaw")
        biomes=payload.get("biomes")
        require(isinstance(biomes,list),sid+" must use direct vanilla biome list")
        require(set(biomes)==EXPECTED_BIOMES[sid],sid+" biome conversion drifted")
        require(payload.get("project_start_to_heightmap")=="WORLD_SURFACE_WG",
                sid+" must be projected to island surface")
        require(payload.get("step")=="surface_structures",sid+" source surface step drifted")
        report["structures"][sid]={
            "biomes":sorted(biomes),
            "type":payload.get("type"),
            "step":payload.get("step"),
            "projection":payload.get("project_start_to_heightmap"),
            "radius":radii.get(sid),
        }

    report["pass"]=True
    if output:
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return report

def main()->None:
    root=Path(__file__).resolve().parents[2]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--builder",type=Path,default=root/"scripts/build-never-overworld-external-structures-r19.py")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    audit(a.source.resolve(),a.builder.resolve(),a.output.resolve() if a.output else None)

if __name__=="__main__":main()
