#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, hashlib, io, json, re, urllib.request, zipfile
from pathlib import Path

TARGET_FORMAT = 107
SPEC = Path(__file__).resolve().parents[1] / "worldgen-spec/never-overworld-external-structures-r19.json"

SOURCES = {
    "witch": {
        "url": "https://cdn.modrinth.com/data/ePaZVJM4/versions/CTab3l6x/Repurposed_Structures-Better_Witch_Huts_v5.zip",
        "sha256": "ca4ae83e5a777392d50154f4ef57d8cbd7a12cc190ed69fd2dd2a51437fd64ef",
    },
    "towers": {
        "url": "https://cdn.modrinth.com/data/j3FONRYr/versions/uxUF2h4B/Structory_Towers_v1.0.17.zip",
        "sha256": "90af7fddea07973fef035b0c99213cc6b4c2baafeeb9c7f8a230b6e256687aa0",
    },
    "explorify": {
        "url": "https://cdn.modrinth.com/data/HSfsxuTo/versions/BKKKBD2V/Explorify%20v1.6.5.dp.zip",
        "sha256": "09dea87923b8dc021a6694f7c6487725b1a666e255e122bce55fdd2dc3377d4f",
    },
    "dat": {
        "url": "https://cdn.modrinth.com/data/tpehi7ww/versions/CS77UwHE/Dungeons%20and%20Taverns%20v5.3.2.zip",
        "sha256": "4096cd6372e0f244efa0e85c4d884bd85afe665a84a050280acd483b3222b4f9",
    },
    "monuments": {
        "url": "https://cdn.modrinth.com/data/WQ8xE11Z/versions/EU6PZcdv/Repurposed_Structures-Better_Monuments_v7.zip",
        "sha256": "c76cd5ab549974b051a352a633abd2f78a916acc40392bc53ba0581c3116a8c9",
    },
}

AUTO_EXCLUDED_CATEGORIES = {"advancement", "advancements", "function", "functions", "recipe", "recipes", "villager_trade", "villager_trades", "predicate", "predicates"}
SURFACE_PROJECTIONS = {"WORLD_SURFACE_WG", "WORLD_SURFACE", "MOTION_BLOCKING_NO_LEAVES"}

def fail(msg: str) -> None:
    raise SystemExit("[NeverFolia][External Structures R19] " + msg)

def policy_radii() -> dict[str,int]:
    data=json.loads(SPEC.read_text(encoding="utf-8"))
    radii=data.get("island_radii",{})
    if data.get("profile")!="NeverOverworld-External-Structures-R19":
        fail("wrong external-structure spec profile")
    if not isinstance(radii,dict) or len(radii)!=134:
        fail(f"expected 134 policy island radii, got {len(radii) if isinstance(radii,dict) else 'invalid'}")
    if any(not isinstance(k,str) or not isinstance(v,int) or v<1 for k,v in radii.items()):
        fail("invalid policy island radius table")
    return radii

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def read_json(data: bytes, where: str) -> dict:
    try:
        return json.loads(data)
    except Exception as ex:
        fail(f"invalid JSON {where}: {ex}")

def format_num(value):
    if isinstance(value, int): return value
    if isinstance(value, list) and value: return int(value[0])
    return None

def flatten_zip(payload: bytes) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        for n in z.namelist():
            if n.startswith("data/") and not n.endswith("/"):
                out[n] = z.read(n)
        meta = {}
        if "pack.mcmeta" in z.namelist():
            meta = read_json(z.read("pack.mcmeta"), "pack.mcmeta")
        for ent in meta.get("overlays", {}).get("entries", []):
            mn = format_num(ent.get("min_format"))
            mx = format_num(ent.get("max_format"))
            if mn is None or mx is None:
                fs = ent.get("formats")
                if isinstance(fs, list) and len(fs) >= 2:
                    mn, mx = format_num(fs[0]), format_num(fs[-1])
            if mn is None or mx is None or not (mn <= TARGET_FORMAT <= mx):
                continue
            prefix = ent["directory"].rstrip("/") + "/"
            for n in z.namelist():
                if n.startswith(prefix + "data/") and not n.endswith("/"):
                    out[n[len(prefix):]] = z.read(n)
    return out

def resource_id(path: str, family: str) -> str | None:
    m = re.match(r"data/([^/]+)/" + re.escape(family) + r"/(.+)\.json$", path)
    return f"{m.group(1)}:{m.group(2)}" if m else None

def biome_tags(files: dict[str, bytes]) -> dict[str, list[str]]:
    result = {}
    for n,b in files.items():
        rid = resource_id(n, "tags/worldgen/biome")
        if not rid: continue
        d = read_json(b, n)
        vals=[]
        for v in d.get("values", []):
            if isinstance(v, str): vals.append(v)
            elif isinstance(v, dict) and isinstance(v.get("id"), str): vals.append(v["id"])
        result[rid]=vals
    return result

def dimension_of(struct_id: str, d: dict, tags: dict[str, list[str]]) -> str:
    raw = json.dumps(d.get("biomes", "")).lower()
    lowid = struct_id.lower()
    nether_keys = ("is_nether","nether_fortress","bastion_remnant","nether_","crimson","warped_forest","soul_sand","basalt_delta")
    end_keys = ("is_end","end_city","outer_end","end_highlands","end_midlands","end_barrens")
    if any(k in raw for k in nether_keys) or any(k in lowid for k in ("nether/","nether_","_nether","piglin")):
        return "nether"
    if any(k in raw for k in end_keys) or any(k in lowid for k in ("end/","end_","_end")):
        return "end"

    seen=set()
    def walk(v: str) -> set[str]:
        low=v.lower()
        if any(k in low for k in nether_keys): return {"nether"}
        if any(k in low for k in end_keys): return {"end"}
        if v.startswith("#"):
            tid=v[1:]
            if tid in seen: return set()
            seen.add(tid)
            out=set()
            for x in tags.get(tid, []): out |= walk(x)
            return out
        if v.startswith("minecraft:"): return {"overworld"}
        return set()
    b=d.get("biomes")
    values=[b] if isinstance(b,str) else (b if isinstance(b,list) else [])
    dims=set()
    for v in values:
        if isinstance(v,str): dims |= walk(v)
    if "overworld" in dims: return "overworld"
    if "nether" in dims: return "nether"
    if "end" in dims: return "end"
    return "overworld"

def biome_refs(d: dict) -> list[str]:
    raw=d.get("biomes")
    if isinstance(raw,str): return [raw]
    if isinstance(raw,list): return [v for v in raw if isinstance(v,str)]
    return []

def explicit_ocean_biomes(d: dict, tags: dict[str, list[str]]) -> bool:
    """True only when the structure's biome contract is explicitly oceanic."""
    seen=set()
    def walk(v: str) -> tuple[bool,bool]:
        low=v.lower()
        # Vanilla/source tag names are useful even if the referenced tag is not
        # copied into the external pack (for example minecraft:ocean_monument).
        if "ocean" in low or "deep_ocean" in low:
            return True,False
        if v.startswith("#"):
            tid=v[1:]
            if tid in seen: return False,False
            seen.add(tid)
            ocean=False;land=False
            for x in tags.get(tid, []):
                o,l=walk(x);ocean|=o;land|=l
            return ocean,land
        if v.startswith("minecraft:"):
            return False,True
        return False,False

    refs=biome_refs(d)
    if not refs: return False
    ocean=False;land=False
    for ref in refs:
        o,l=walk(ref);ocean|=o;land|=l
    return ocean and not land

def absolute_start_height(d: dict) -> int | None:
    raw=d.get("start_height")
    if not isinstance(raw,dict): return None
    value=raw.get("absolute")
    return value if isinstance(value,int) else None

def is_land_surface(d: dict, tags: dict[str, list[str]]) -> bool:
    # Preserve source generation intent. A structure is island-adapted only
    # when the source itself schedules it in surface_structures and its biome
    # contract is not explicitly oceanic. OCEAN_FLOOR_WG alone is not an ocean
    # classifier because several genuine land structures use that projection.
    #
    # In particular, D&T lone_citadel/toxic_lair use underground_decoration.
    # Their fixed source Y is intentional underground placement and must remain
    # untouched per the R19 contract.
    return d.get("step") == "surface_structures" and not explicit_ocean_biomes(d,tags)

def adapt_land_surface(d: dict) -> dict:
    """Anchor admitted source-surface structures to NeverOverworld terrain."""
    out=copy.deepcopy(d)
    source_height=absolute_start_height(out)
    out["project_start_to_heightmap"]="WORLD_SURFACE_WG"
    if source_height == 63 or "start_height" not in out:
        # D&T witch_villa is a source surface structure anchored to vanilla
        # sea level Y63. WORLD_SURFACE_WG + zero offset preserves its surface
        # intent in the Y128 NeverOverworld.
        out["start_height"]={"absolute":0}
    return out

def island_radius(d: dict) -> int:
    size = d.get("size")
    if isinstance(size, int):
        return max(24, min(96, 16 + size * 8))
    return 32

def sanitize_processor(proc):
    if not isinstance(proc, dict): return None
    t=proc.get("processor_type")
    if not isinstance(t, str): return proc
    if t.startswith("minecraft:"):
        return proc
    if t == "repurposed_structures:structure_surface_processor":
        delegate=proc.get("delegate")
        return sanitize_processor(delegate)
    if t == "repurposed_structures:pillar_processor":
        # Vanilla Folia has no registry entry for RS's downward pillar
        # processor. Do not silently leave its template marker blocks behind:
        # translate the marker -> support-material part into a vanilla rule
        # processor. The dynamic downward extension itself remains intentionally
        # omitted; R19's exact dry-island piece admission is the terrain-safety
        # replacement for that mod-only behavior.
        rules=[]
        for pair in proc.get("pillar_trigger_and_replacements", []):
            if not isinstance(pair,dict): continue
            trigger=pair.get("trigger")
            replacement=pair.get("replacement")
            if not isinstance(trigger,dict) or not isinstance(replacement,dict):
                continue
            block=trigger.get("Name")
            if not isinstance(block,str) or not block.startswith("minecraft:"):
                continue
            rules.append({
                "input_predicate":{
                    "predicate_type":"minecraft:block_match",
                    "block":block,
                },
                "location_predicate":{"predicate_type":"minecraft:always_true"},
                "output_state":replacement,
            })
        if rules:
            return {"processor_type":"minecraft:rule","rules":rules}
        return None
    return None

def sanitize_processor_list(data: dict) -> dict:
    out=[]
    for p in data.get("processors", []):
        q=sanitize_processor(p)
        if q is not None: out.append(q)
    return {"processors": out}

def sanitize_pool(data: dict, drop_legacy_features: bool=False) -> dict:
    data=copy.deepcopy(data)
    data.pop("name", None)
    elements=[]
    for entry in data.get("elements", []):
        el=entry.get("element")
        if not isinstance(el, dict):
            elements.append(entry); continue
        if el.get("element_type") == "yungsapi:max_count_single_element":
            el["element_type"]="minecraft:single_pool_element"
            el.pop("max_count",None)
            el.pop("name",None)
        if drop_legacy_features and el.get("element_type") == "minecraft:feature_pool_element":
            feature=el.get("feature","")
            if isinstance(feature,str) and feature.startswith("betteroceanmonuments:"):
                continue
        elements.append(entry)
    data["elements"]=elements
    return data

RS_BIOMES = {
    "repurposed_structures:witch_hut_birch": ["minecraft:birch_forest","minecraft:old_growth_birch_forest"],
    "repurposed_structures:witch_hut_dark_forest": ["minecraft:dark_forest"],
    "repurposed_structures:witch_hut_giant_tree_taiga": ["minecraft:old_growth_pine_taiga","minecraft:old_growth_spruce_taiga"],
    "repurposed_structures:witch_hut_mangrove": ["minecraft:mangrove_swamp"],
    "repurposed_structures:witch_hut_oak": ["minecraft:forest","minecraft:flower_forest"],
    "repurposed_structures:witch_hut_taiga": ["minecraft:taiga","minecraft:snowy_taiga"],
    "repurposed_structures:monument_desert": ["minecraft:desert"],
    "repurposed_structures:monument_icy": ["minecraft:snowy_plains","minecraft:ice_spikes","minecraft:snowy_slopes","minecraft:frozen_peaks","minecraft:jagged_peaks","minecraft:grove"],
    "repurposed_structures:monument_jungle": ["minecraft:jungle","minecraft:sparse_jungle","minecraft:bamboo_jungle"],
}

def sanitize_repurposed_structure(data: dict, radius: int, structure_id: str) -> dict:
    d=copy.deepcopy(data)
    d["type"]="minecraft:jigsaw"
    for key in ("burying_type","valid_biome_radius_check"):
        d.pop(key,None)
    d.setdefault("max_distance_from_center", max(80, radius))
    d.setdefault("use_expansion_hack", False)
    if structure_id in RS_BIOMES:
        d["biomes"]=RS_BIOMES[structure_id]
    return d

def merge_rs_pool_additions(files: dict[str, bytes]) -> None:
    for n,b in list(files.items()):
        m=re.match(r"data/([^/]+)/rs_pool_additions/(.+)\.json$", n)
        if not m: continue
        d=read_json(b,n)
        target=d.get("target_pool")
        if not isinstance(target,str) or ":" not in target: continue
        ns,path=target.split(":",1)
        dest=f"data/{ns}/worldgen/template_pool/{path}.json"
        base=read_json(files.get(dest,b'{"fallback":"minecraft:empty","elements":[]}'),dest)
        base.setdefault("fallback",d.get("fallback","minecraft:empty"))
        base.setdefault("elements",[])
        base["elements"].extend(d.get("elements",[]))
        files[dest]=(json.dumps(base,indent=2,ensure_ascii=False)+"\n").encode()

def should_copy_dependency(path: str) -> bool:
    if not path.startswith("data/"): return False
    parts=path.split("/")
    if len(parts) < 3: return False
    ns,category=parts[1],parts[2]
    if ns=="minecraft": return False
    if category in AUTO_EXCLUDED_CATEGORIES: return False
    if category=="rs_pool_additions": return False
    if "/tags/worldgen/structure/" in path: return False
    return True

def strip_dat_run_function_effects(value):
    """Remove D&T scripted enchantment effects from the structure-only import.

    The supplied D&T pack contains a broader gameplay layer (quests, bosses,
    tick/load helpers and newer command syntax). NeverFolia imports structures,
    not that global runtime. Keep the enchantment registry IDs so NBT/loot can
    still resolve them, but remove run_function effects rather than importing
    incompatible mcfunctions that spam the console or fail datapack reload.
    """
    if isinstance(value, list):
        out=[]
        for child in value:
            sanitized=strip_dat_run_function_effects(child)
            if sanitized is not None:
                out.append(sanitized)
        return out
    if not isinstance(value, dict):
        return value
    if value.get("type") in ("minecraft:run_function", "run_function"):
        return None

    out={}
    for key,child in value.items():
        sanitized=strip_dat_run_function_effects(child)
        if sanitized is None:
            if key == "effect":
                # An enchantment condition without an effect is invalid; drop
                # the complete wrapper from its parent list.
                return None
            continue
        out[key]=sanitized

    # all_of with no remaining effects is itself a no-op and should disappear.
    if out.get("type") in ("minecraft:all_of", "all_of") and out.get("effects") == []:
        return None
    return out

def sanitize_dat_enchantment(data: dict) -> dict:
    out=strip_dat_run_function_effects(copy.deepcopy(data))
    if not isinstance(out,dict):
        fail("D&T enchantment sanitizer removed JSON root")
    effects=out.get("effects")
    if isinstance(effects,dict):
        out["effects"]={
            key:value for key,value in effects.items()
            if value not in (None, [], {})
        }
        if not out["effects"]:
            out.pop("effects",None)
    return out

def dat_minecraft_compat(path: str) -> bool:
    # Dungeons & Taverns defines NEW dependency resources under minecraft:
    # namespace. They are not structure/structure_set/tag overrides and cannot
    # spawn anything by themselves. Copying the complete dependency families is
    # required because even excluded Nether/End template pools are registry
    # entries and must resolve their processors/fallback pools while datapacks
    # freeze. Generation remains Overworld-only because their structure sets are
    # filtered separately.
    for prefix in (
        "data/minecraft/worldgen/configured_feature/",
        "data/minecraft/worldgen/placed_feature/",
        "data/minecraft/worldgen/processor_list/",
        "data/minecraft/worldgen/template_pool/",
        "data/minecraft/structure/",
        "data/minecraft/loot_table/",
    ):
        if path.startswith(prefix):
            return True
    return False

def filter_pack(key: str, files: dict[str, bytes]):
    files=dict(files)
    if key=="witch":
        merge_rs_pool_additions(files)
    tags=biome_tags(files)
    allowed=set(); land=set(); radii={}
    for n,b in files.items():
        sid=resource_id(n,"worldgen/structure")
        if not sid: continue
        d=read_json(b,n)
        if dimension_of(sid,d,tags)!="overworld": continue
        allowed.add(sid)
        if is_land_surface(d,tags):
            land.add(sid); radii[sid]=island_radius(d)

    out={}
    for n,b in files.items():
        if key=="dat" and dat_minecraft_compat(n):
            out[n]=b
            continue
        if key=="dat" and "/enchantment/" in n and n.endswith(".json"):
            d=sanitize_dat_enchantment(read_json(b,n))
            out[n]=(json.dumps(d,indent=2,ensure_ascii=False)+"\n").encode()
            continue
        if not should_copy_dependency(n): continue
        if key in {"witch","monuments"} and "/tags/worldgen/biome/" in n:
            # Converted RS structures carry direct vanilla biome lists and must
            # not depend on the missing base Repurposed Structures tag pack.
            continue
        if key=="monuments" and (
            "/worldgen/configured_feature/" in n or "/worldgen/placed_feature/" in n
        ):
            # These seven decorative random_patch features target an older
            # feature registry. Their pool elements are removed below; monument
            # geometry, pools, templates and loot remain intact.
            continue
        sid=resource_id(n,"worldgen/structure")
        if sid:
            if sid not in allowed: continue
            d=read_json(b,n)
            if key in {"witch","monuments"}:
                d=sanitize_repurposed_structure(d,radii.get(sid,32),sid)
            if sid in land:
                d=adapt_land_surface(d)
            out[n]=(json.dumps(d,indent=2,ensure_ascii=False)+"\n").encode()
            continue
        setid=resource_id(n,"worldgen/structure_set")
        if setid:
            d=read_json(b,n)
            entries=[e for e in d.get("structures",[]) if e.get("structure") in allowed]
            if not entries: continue
            d=copy.deepcopy(d); d["structures"]=entries
            out[n]=(json.dumps(d,indent=2,ensure_ascii=False)+"\n").encode()
            continue
        if "/worldgen/processor_list/" in n and n.endswith(".json") and key in {"witch","monuments"}:
            d=sanitize_processor_list(read_json(b,n))
            out[n]=(json.dumps(d,indent=2,ensure_ascii=False)+"\n").encode()
            continue
        if "/worldgen/template_pool/" in n and n.endswith(".json") and key in {"witch","monuments"}:
            d=sanitize_pool(read_json(b,n),drop_legacy_features=(key=="monuments"))
            out[n]=(json.dumps(d,indent=2,ensure_ascii=False)+"\n").encode()
            continue
        out[n]=b

    # Final compatibility guards for the vanilla-only Folia runtime.
    if key in {"witch","monuments"}:
        for n in out:
            if "/tags/worldgen/biome/" in n and n.startswith("data/repurposed_structures/"):
                fail("base Repurposed Structures biome-tag dependency survived: "+n)
    if key=="monuments":
        if any("/worldgen/configured_feature/" in n or "/worldgen/placed_feature/" in n for n in out if n.startswith("data/betteroceanmonuments/")):
            fail("legacy Better Monuments random_patch feature survived")
    if key=="dat":
        required=(
            "data/minecraft/worldgen/placed_feature/donjon_base.json",
            "data/minecraft/worldgen/processor_list/ruined_town_degradation.json",
            "data/minecraft/worldgen/processor_list/nether_fortress_generic_degradation.json",
            "data/minecraft/worldgen/template_pool/illager_mansion/illager_mansion_entry.json",
            "data/minecraft/worldgen/template_pool/jungle_village/town_center.json",
            "data/minecraft/worldgen/template_pool/swamp_village/town_center.json",
            "data/minecraft/worldgen/template_pool/nether_fortress/nether_fortress_core.json",
            "data/minecraft/structure/illager_mansion/illager_mansion_anchor.nbt",
            "data/minecraft/loot_table/chests/village/village_jungle_house.json",
        )
        for n in required:
            if n not in out: fail("Dungeons & Taverns Overworld dependency missing: "+n)


    if key=="witch":
        out["data/neverfolia/worldgen/structure_set/external_better_witch_huts.json"]=(json.dumps({
            "placement":{"type":"minecraft:random_spread","spacing":32,"separation":8,"salt":14357620,"spread_type":"linear"},
            "structures":[{"structure":s,"weight":1} for s in sorted(allowed)]
        },indent=2)+"\n").encode()
    if key=="monuments":
        out["data/neverfolia/worldgen/structure_set/external_better_monuments.json"]=(json.dumps({
            "placement":{"type":"minecraft:random_spread","spacing":32,"separation":5,"salt":10387313,"spread_type":"triangular"},
            "structures":[{"structure":s,"weight":1} for s in sorted(allowed)]
        },indent=2)+"\n").encode()
    references=set()
    for n,b in out.items():
        if not resource_id(n,"worldgen/structure_set"):
            continue
        d=read_json(b,n)
        for entry in d.get("structures",[]):
            if isinstance(entry,dict) and isinstance(entry.get("structure"),str):
                references.add(entry["structure"])
    source_unused=sorted(allowed-references)
    return out, allowed, land, radii, source_unused

def fetch_source(key: str, cache: Path) -> bytes:
    cfg=SOURCES[key]
    cache.mkdir(parents=True,exist_ok=True)
    dest=cache/(key+".zip")
    if dest.is_file():
        data=dest.read_bytes()
    else:
        req=urllib.request.Request(cfg["url"],headers={"User-Agent":"NeverFolia-R19/1"})
        with urllib.request.urlopen(req,timeout=120) as r: data=r.read()
        dest.write_bytes(data)
    if sha(data)!=cfg["sha256"]:
        fail(f"{key} SHA256 mismatch: got {sha(data)}, expected {cfg['sha256']}")
    return data

def build(base: Path, output: Path, payloads: dict[str,bytes]):
    with zipfile.ZipFile(base) as z:
        merged={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
    all_land={}
    all_source_unused=set()
    summary={}
    for key,payload in payloads.items():
        files=flatten_zip(payload)
        filtered,allowed,land,radii,source_unused=filter_pack(key,files)
        collisions=[n for n in filtered if n in merged and merged[n]!=filtered[n]]
        if collisions:
            fail(f"{key} collisions with NeverOverworld: {collisions[:8]}")
        merged.update(filtered)
        all_land.update(radii)
        all_source_unused.update(source_unused)
        summary[key]={
            "overworld_structures":len(allowed),
            "natural_spawnable":len(allowed)-len(source_unused),
            "source_unused":source_unused,
            "island_adapted":len(land),
            "files":len(filtered),
            "sha256":sha(payload),
        }

    expected_radii=policy_radii()
    detected=set(all_land)
    expected=set(expected_radii)
    if detected!=expected:
        fail(
            "land classification/spec drift: missing="
            +repr(sorted(expected-detected)[:20])
            +" unexpected="+repr(sorted(detected-expected)[:20])
        )
    # The checked-in spec is authoritative for footprint radii. The builder
    # discovers *which* source structures are land; the policy table controls
    # their tuned island envelope. This keeps pack metadata, runtime admission
    # and fast-locate prediction on the same exact radius values.
    all_land=dict(expected_radii)

    manifest={
        "schema":1,
        "profile":"NeverOverworld-External-Structures-R19",
        "target_pack_format":TARGET_FORMAT,
        "sources":summary,
        "island_admission":{
            "min_surface_y":129,
            "structure_count":len(all_land),
            "spawnable_structure_count":len(set(all_land)-all_source_unused),
            "radii":dict(sorted(all_land.items())),
        },
        "source_unused_structures":sorted(all_source_unused),
        "untouched_policy":"Overworld ocean/underground structures keep source placement; Nether/End structures are excluded.",
        "skipped_supplied_packs":["Amplified_Nether_v1.2.15 (no structures)","Hearths v1.0.5 (Nether-only structures)"],
        "minecraft_namespace_overrides_imported":False,
    }
    merged["neveroverworld-external-structures-r19.json"]=(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n").encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n in sorted(merged): z.writestr(n,merged[n])
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--cache",type=Path,default=Path(".work/external-structures-r19"))
    p.add_argument("--source",action="append",default=[],help="key=/path/to/exact.zip; overrides network fetch")
    a=p.parse_args()
    supplied={}
    for item in a.source:
        key,path=item.split("=",1)
        data=Path(path).read_bytes()
        exp=SOURCES[key]["sha256"]
        if sha(data)!=exp: fail(f"{key} supplied SHA mismatch")
        supplied[key]=data
    payloads={}
    for key in SOURCES:
        payloads[key]=supplied.get(key) or fetch_source(key,a.cache)
    manifest=build(a.input,a.output,payloads)
    print(json.dumps(manifest,indent=2,ensure_ascii=False))

if __name__=="__main__": main()
