#!/usr/bin/env python3
"""R39.25: make Y=128 the native Overworld sea level and harden D&T technical enchantments."""
from __future__ import annotations
import argparse,hashlib,io,json,zipfile
from pathlib import Path,PurePosixPath

NOISE="data/minecraft/worldgen/noise_settings/overworld.json"
GAME="data/nova_structures/tags/enchantment/all_dnt_enchants.json"
TECH="data/nova_structures/tags/enchantment/non_survival_enchants.json"
RAVAGER="nova_structures:jockey/spawn_ravager_jockey"
DEAD_MODIFIERS={f"data/nova_structures/item_modifier/dnt_tech_enchant_fix_{i}.json" for i in range(1,6)}
PUBLIC_PREFIX="data/minecraft/tags/enchantment/"

def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()
def ids(doc):
    out=[]
    for value in doc.get("values",[]):
        rid=value if isinstance(value,str) else value.get("id") if isinstance(value,dict) else None
        if isinstance(rid,str):out.append(rid)
    return out
def read_zip(raw:bytes)->dict[str,bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if not n.endswith("/")]
        need(z.testzip() is None and len(names)==len(set(names)),"invalid/duplicate base pack")
        need(all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and "\\" not in n for n in names),"unsafe ZIP path")
        return {n:z.read(n) for n in names}
def write_zip(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,payload in sorted(files.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,payload,compresslevel=9)
    return out.getvalue()
def dump(doc):
    return (json.dumps(doc,indent=2,ensure_ascii=False)+"\n").encode()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    base=a.base.read_bytes();files=read_zip(base)
    report={"pass":False}
    try:
        need(NOISE in files and GAME in files and TECH in files,"required R3924 resources missing")

        noise=json.loads(files[NOISE])
        need(noise.get("sea_level")==63,"unexpected source sea_level: "+repr(noise.get("sea_level")))
        noise["sea_level"]=128
        files[NOISE]=dump(noise)

        game=set(ids(json.loads(files[GAME])))
        tech_doc=json.loads(files[TECH]);tech_values=list(tech_doc.get("values",[]))
        tech=set(ids(tech_doc))
        need(len(game)==17,"expected 17 gameplay D&T enchantments")
        if RAVAGER not in tech:
            tech_values.append(RAVAGER);tech.add(RAVAGER)
        need(len(tech)==16,"expected exactly 16 technical enchantments after ravager classification: "+repr(sorted(tech)))
        need(not game&tech,"gameplay/technical overlap")
        tech_doc["replace"]=False
        tech_doc["values"]=tech_values
        files[TECH]=dump(tech_doc)

        hardened={}
        for rid in sorted(tech):
            ns,name=rid.split(":",1)
            path=f"data/{ns}/enchantment/{name}.json"
            need(path in files,"technical enchantment definition missing: "+path)
            doc=json.loads(files[path])
            old_level=doc.get("max_level")
            doc["max_level"]=1
            doc["description"]={"text":""}
            files[path]=dump(doc)
            hardened[rid]={"old_max_level":old_level,"new_max_level":1}

        for dead in DEAD_MODIFIERS:
            files.pop(dead,None)

        public={}
        for name,payload in list(files.items()):
            if not(name.startswith(PUBLIC_PREFIX) and name.endswith(".json")):continue
            doc=json.loads(payload);values=doc.get("values")
            if not isinstance(values,list):continue
            cleaned=[]
            for value in values:
                rid=value if isinstance(value,str) else value.get("id") if isinstance(value,dict) else None
                if rid in tech:continue
                cleaned.append(value)
            if cleaned!=values:
                doc["values"]=cleaned;files[name]=dump(doc)
            public[name]=set(ids(doc))
        leaks={n:sorted(v&tech) for n,v in public.items() if v&tech}
        need(not leaks,"technical enchantments remain in public acquisition tags: "+repr(leaks))

        # Every internal controller item must use level I only. Level V is what
        # made the unclassified ravager controller surface as "Bug Enchant V".
        bad_levels=[]
        for name,payload in files.items():
            if not name.endswith((".json",".mcfunction")):continue
            try:text=payload.decode("utf-8")
            except UnicodeDecodeError:continue
            for rid in tech:
                needle='"'+rid+'"'
                start=0
                while True:
                    pos=text.find(needle,start)
                    if pos<0:break
                    tail=text[pos+len(needle):pos+len(needle)+32]
                    import re
                    m=re.match(r"\s*:\s*([0-9]+)",tail)
                    if m and int(m.group(1))>1:bad_levels.append((name,rid,int(m.group(1))))
                    start=pos+len(needle)
        need(not bad_levels,"technical enchantment level > I survived: "+repr(bad_levels[:20]))

        # No real enchant definition may still render the source fallback label.
        bug_defs=[]
        for rid in tech:
            ns,name=rid.split(":",1)
            path=f"data/{ns}/enchantment/{name}.json"
            if b"Bug Enchant" in files[path]:bug_defs.append(path)
        need(not bug_defs,"Bug Enchant fallback survived: "+repr(bug_defs))

        raw=write_zip(files)
        need(read_zip(raw)==files and raw==write_zip(files),"non-deterministic output")
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_bytes(raw)
        report={
          "pass":True,
          "base_sha256":sha(base),
          "pre_fingerprint_output_sha256":sha(raw),
          "sea_level_before":63,
          "sea_level_after":128,
          "native_water_top_y":127,
          "gameplay_enchantments":sorted(game),
          "gameplay_count":len(game),
          "technical_enchantments":sorted(tech),
          "technical_count":len(tech),
          "ravager_classified":RAVAGER in tech,
          "technical_hardening":hardened,
          "public_technical_leaks":leaks,
          "dead_item_modifiers_removed":sorted(DEAD_MODIFIERS),
          "technical_level_gt_one":bad_levels,
        }
    except Exception as exc:
        report={"pass":False,"error":repr(exc)}
        raise
    finally:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
        print("R3925_PACK "+json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":main()
