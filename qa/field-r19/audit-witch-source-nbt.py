#!/usr/bin/env python3
"""Audit the pinned Better Witch Huts v5 source ZIP and its merged R19 output.

The compatibility datapack contains vanilla structure-template NBT plus mod
processor identifiers. NeverFolia copies the templates byte-for-byte, rewrites
the structure/pool graph, and strips processors that cannot exist on a vanilla
Folia server. This audit proves that:
- the exact pinned Witch ZIP is the one being consumed;
- every template-pool location resolves to a real NBT template;
- copied NBT templates remain byte-identical after the R19 merge;
- NBT palettes/entities/block entities do not require non-vanilla registries;
- witch/cat spawning is retained by structure spawn_overrides even if templates
  themselves contain no mob entities;
- merged processor lists contain only vanilla processor types.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

EXPECTED_SHA256="ca4ae83e5a777392d50154f4ef57d8cbd7a12cc190ed69fd2dd2a51437fd64ef"
BIOMES=("birch","dark_forest","giant_tree_taiga","mangrove","oak","taiga")
SIZES=("sm","lg","double")
ALLOWED_MOB_IDS={"minecraft:witch","minecraft:cat"}

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[Witch R19 QA] "+message)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class NBTReader:
    def __init__(self, data: bytes):
        self.data=data
        self.pos=0

    def take(self,n:int)->bytes:
        require(self.pos+n<=len(self.data),"truncated NBT")
        out=self.data[self.pos:self.pos+n]
        self.pos+=n
        return out

    def unpack(self,fmt:str):
        return struct.unpack(">"+fmt,self.take(struct.calcsize(">"+fmt)))[0]

    def string(self)->str:
        n=self.unpack("H")
        return self.take(n).decode("utf-8")

    def payload(self,t:int):
        if t==0: return None
        if t==1: return self.unpack("b")
        if t==2: return self.unpack("h")
        if t==3: return self.unpack("i")
        if t==4: return self.unpack("q")
        if t==5: return self.unpack("f")
        if t==6: return self.unpack("d")
        if t==7:
            n=self.unpack("i"); require(n>=0,"negative byte-array length")
            return self.take(n)
        if t==8: return self.string()
        if t==9:
            child=self.unpack("B"); n=self.unpack("i")
            require(n>=0,"negative list length")
            return [self.payload(child) for _ in range(n)]
        if t==10:
            out={}
            while True:
                child=self.unpack("B")
                if child==0: return out
                name=self.string()
                out[name]=self.payload(child)
        if t==11:
            n=self.unpack("i"); require(n>=0,"negative int-array length")
            return [self.unpack("i") for _ in range(n)]
        if t==12:
            n=self.unpack("i"); require(n>=0,"negative long-array length")
            return [self.unpack("q") for _ in range(n)]
        raise ValueError("[Witch R19 QA] unknown NBT tag type "+str(t))

def parse_nbt(data: bytes)->dict:
    if data[:2]==b"\x1f\x8b":
        data=gzip.decompress(data)
    r=NBTReader(data)
    root_type=r.unpack("B")
    require(root_type==10,"structure NBT root must be TAG_Compound")
    _root_name=r.string()
    root=r.payload(root_type)
    require(isinstance(root,dict),"invalid NBT root")
    require(r.pos==len(data),"trailing bytes after NBT root")
    return root

def nested_entity_ids(value)->list[str]:
    out=[]
    if isinstance(value,dict):
        entity_id=value.get("id")
        if isinstance(entity_id,str): out.append(entity_id)
        for v in value.values(): out.extend(nested_entity_ids(v))
    elif isinstance(value,list):
        for v in value: out.extend(nested_entity_ids(v))
    return out

def nbt_summary(data:bytes)->dict:
    root=parse_nbt(data)
    palette=root.get("palette",[])
    blocks=root.get("blocks",[])
    entities=root.get("entities",[])
    require(isinstance(palette,list) and isinstance(blocks,list) and isinstance(entities,list),
            "structure template missing palette/blocks/entities lists")

    palette_names=[]
    for item in palette:
        if isinstance(item,dict) and isinstance(item.get("Name"),str):
            palette_names.append(item["Name"])

    entity_ids=[]
    for item in entities:
        if isinstance(item,dict):
            entity_ids.extend(nested_entity_ids(item.get("nbt",{})))

    block_entity_ids=[]
    for item in blocks:
        if not isinstance(item,dict): continue
        payload=item.get("nbt")
        if isinstance(payload,dict) and isinstance(payload.get("id"),str):
            block_entity_ids.append(payload["id"])

    return {
        "size":root.get("size"),
        "data_version":root.get("DataVersion"),
        "palette_blocks":sorted(set(palette_names)),
        "entity_ids":sorted(entity_ids),
        "block_entity_ids":sorted(block_entity_ids),
        "entity_count":len(entities),
        "block_count":len(blocks),
    }

def read_json(z:zipfile.ZipFile,name:str)->dict:
    require(name in z.namelist(),"missing JSON: "+name)
    value=json.loads(z.read(name).decode("utf-8"))
    require(isinstance(value,dict),"JSON root must be object: "+name)
    return value

def spawn_ids(structure:dict)->set[str]:
    out=set()
    overrides=structure.get("spawn_overrides",{})
    if not isinstance(overrides,dict): return out
    for category in overrides.values():
        if not isinstance(category,dict): continue
        for row in category.get("spawns",[]):
            if isinstance(row,dict) and isinstance(row.get("type"),str):
                out.add(row["type"])
    return out

def processor_types(payload:dict)->set[str]:
    out=set()
    for p in payload.get("processors",[]):
        if isinstance(p,dict) and isinstance(p.get("processor_type"),str):
            out.add(p["processor_type"])
    return out

def audit(source:Path, merged:Path|None)->dict:
    raw=source.read_bytes()
    require(sha256(raw)==EXPECTED_SHA256,
            "Witch source ZIP SHA256 mismatch: "+sha256(raw))

    report={
        "schema":1,
        "profile":"NeverOverworld-R19-Witch-Source-NBT-QA1",
        "source_zip":source.name,
        "source_sha256":sha256(raw),
        "templates":{},
        "source_processor_types":{},
        "merged_processor_types":{},
        "spawn_overrides":{},
        "pool_links":{},
        "mob_reference_summary":{},
        "pass":False,
    }

    with zipfile.ZipFile(source) as src:
        bad=src.testzip()
        require(bad is None,"corrupt Witch ZIP entry: "+str(bad))
        names=set(src.namelist())

        expected_templates={
            f"data/betterwitchhuts/structure/{biome}/witch_hut_{size}.nbt"
            for biome in BIOMES for size in SIZES
        }
        actual_templates={n for n in names if n.startswith("data/betterwitchhuts/structure/") and n.endswith(".nbt")}
        require(actual_templates==expected_templates,
                f"Witch template set drifted: expected {len(expected_templates)}, got {len(actual_templates)}")

        all_nbt_entities=Counter()
        all_block_entities=Counter()
        all_palette_names=set()
        source_template_bytes={}

        for name in sorted(expected_templates):
            data=src.read(name)
            source_template_bytes[name]=data
            info=nbt_summary(data)
            report["templates"][name]=info
            all_nbt_entities.update(info["entity_ids"])
            all_block_entities.update(info["block_entity_ids"])
            all_palette_names.update(info["palette_blocks"])

        require(all(name.startswith("minecraft:") for name in all_palette_names),
                "Witch NBT palette contains non-vanilla block IDs")
        require(all(name.startswith("minecraft:") for name in all_block_entities),
                "Witch NBT contains non-vanilla block-entity IDs")
        require(all(name.startswith("minecraft:") for name in all_nbt_entities),
                "Witch NBT contains non-vanilla entity IDs")

        for biome in BIOMES:
            struct_name=f"data/repurposed_structures/worldgen/structure/witch_hut_{biome}.json"
            structure=read_json(src,struct_name)
            mobs=spawn_ids(structure)
            require(mobs==ALLOWED_MOB_IDS,
                    f"{struct_name} must retain witch+cat spawn overrides, got {sorted(mobs)}")
            report["spawn_overrides"][biome]=sorted(mobs)

            proc_name=f"data/betterwitchhuts/worldgen/processor_list/{biome}.json"
            proc=read_json(src,proc_name)
            report["source_processor_types"][biome]=sorted(processor_types(proc))

            add_name=f"data/betterwitchhuts/rs_pool_additions/witch_huts/{biome}_start_pool.json"
            add=read_json(src,add_name)
            links=[]
            for row in add.get("elements",[]):
                element=row.get("element",{}) if isinstance(row,dict) else {}
                location=element.get("location")
                processors=element.get("processors")
                require(isinstance(location,str) and location.startswith("betterwitchhuts:"),
                        "invalid Witch pool template location: "+repr(location))
                namespace,path=location.split(":",1)
                nbt=f"data/{namespace}/structure/{path}.nbt"
                require(nbt in names,"Witch pool points to missing NBT: "+nbt)
                require(processors==f"betterwitchhuts:{biome}",
                        f"Witch pool processor mismatch for {biome}: {processors}")
                links.append({"location":location,"nbt":nbt,"processors":processors})
            require(len(links)==3,f"Witch {biome} pool must reference sm/lg/double templates")
            report["pool_links"][biome]=links

        report["mob_reference_summary"]={
            "nbt_entity_ids":dict(sorted(all_nbt_entities.items())),
            "nbt_block_entity_ids":dict(sorted(all_block_entities.items())),
            "structure_spawn_override_ids":sorted(ALLOWED_MOB_IDS),
            "note":(
                "Witch/cat population is authoritative in structure spawn_overrides. "
                "Any entities embedded in NBT are audited separately and must be vanilla IDs."
            ),
        }

        if merged is not None:
            with zipfile.ZipFile(merged) as out:
                bad=out.testzip()
                require(bad is None,"corrupt merged NeverOverworld ZIP entry: "+str(bad))
                out_names=set(out.namelist())
                for name,data in source_template_bytes.items():
                    require(name in out_names,"merged pack lost Witch NBT: "+name)
                    require(out.read(name)==data,"merged pack modified Witch NBT bytes: "+name)

                for biome in BIOMES:
                    struct_name=f"data/repurposed_structures/worldgen/structure/witch_hut_{biome}.json"
                    structure=read_json(out,struct_name)
                    mobs=spawn_ids(structure)
                    require(mobs==ALLOWED_MOB_IDS,
                            f"merged {struct_name} lost witch/cat spawn overrides")

                    proc_name=f"data/betterwitchhuts/worldgen/processor_list/{biome}.json"
                    proc=read_json(out,proc_name)
                    types=processor_types(proc)
                    require(all(t.startswith("minecraft:") for t in types),
                            f"merged Witch processor list still requires a mod: {sorted(types)}")
                    report["merged_processor_types"][biome]=sorted(types)

                    pool_name=f"data/repurposed_structures/worldgen/template_pool/witch_huts/{biome}_start_pool.json"
                    pool=read_json(out,pool_name)
                    locations=[]
                    for row in pool.get("elements",[]):
                        element=row.get("element",{}) if isinstance(row,dict) else {}
                        location=element.get("location")
                        if isinstance(location,str) and location.startswith("betterwitchhuts:"):
                            locations.append(location)
                    expected={f"betterwitchhuts:{biome}/witch_hut_{size}" for size in SIZES}
                    require(set(locations)==expected,
                            f"merged Witch pool links drifted for {biome}: {sorted(locations)}")

    report["pass"]=True
    return report

def self_test()->None:
    # Minimal gzip-NBT fixture with one vanilla cat entity.
    def s(v:str)->bytes:
        b=v.encode(); return struct.pack(">H",len(b))+b
    # Root compound -> entities list(compound) -> nbt compound -> id string.
    payload=bytearray()
    payload+=b"\x0a"+s("")
    payload+=b"\x09"+s("entities")+b"\x0a"+struct.pack(">i",1)
    payload+=b"\x0a"+s("nbt")
    payload+=b"\x08"+s("id")+s("minecraft:cat")
    payload+=b"\x00"
    payload+=b"\x00"
    payload+=b"\x09"+s("palette")+b"\x0a"+struct.pack(">i",0)
    payload+=b"\x09"+s("blocks")+b"\x0a"+struct.pack(">i",0)
    payload+=b"\x00"
    parsed=nbt_summary(gzip.compress(bytes(payload)))
    require(parsed["entity_ids"]==["minecraft:cat"],"SELF-TEST entity parse failed")
    print("[Witch R19 QA] SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path)
    p.add_argument("--merged",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test(); return
    if a.source is None:
        p.error("--source is required")
    result=audit(a.source.resolve(),a.merged.resolve() if a.merged else None)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__":
    main()
