#!/usr/bin/env python3
"""Audit Dungeons & Taverns enchantment runtime closure for NeverFolia R24."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BUILDER=ROOT/"scripts/build-never-overworld-external-structures-r19.py"

def load_builder():
    spec=importlib.util.spec_from_file_location("r24_dat_builder",BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("builder import unavailable")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def collect_run_function(value,out:set[str]):
    if isinstance(value,list):
        for x in value: collect_run_function(x,out)
        return
    if not isinstance(value,dict): return
    if value.get("type") in ("minecraft:run_function","run_function"):
        rid=value.get("function")
        if isinstance(rid,str): out.add(rid)
    for x in value.values(): collect_run_function(x,out)

FUNCTION_CALL_RE=re.compile(
    r"(?:^|\s)(?:function|schedule\s+function)\s+([a-z0-9_.-]+:[a-z0-9_./-]+)"
)

def function_candidates(rid:str):
    ns,path=rid.split(":",1)
    return (
        f"data/{ns}/function/{path}.mcfunction",
        f"data/{ns}/functions/{path}.mcfunction",
    )

def resolve(files,rid):
    for p in function_candidates(rid):
        if p in files:return p
    return None

def main():
    builder=load_builder()
    payload=builder.fetch_source("dat",ROOT/".work/external-structures-r24")
    files=builder.flatten_zip(payload)

    roots=set()
    root_files=[]
    for name,payload in sorted(files.items()):
        if "/enchantment/" not in name or not name.endswith(".json"):
            continue
        data=json.loads(payload)
        before=set()
        collect_run_function(data,before)
        if before:
            root_files.append({"path":name,"run_function_refs":sorted(before)})
            roots |= before

    closure=set()
    missing=set()
    queue=list(sorted(roots))
    functions={}
    while queue:
        rid=queue.pop(0)
        if rid in closure:continue
        closure.add(rid)
        path=resolve(files,rid)
        if path is None:
            missing.add(rid);continue
        text=files[path].decode("utf-8",errors="replace")
        lines=[]
        calls=set()
        for no,raw in enumerate(text.splitlines(),1):
            line=raw.strip()
            if not line or line.startswith("#"):continue
            m=FUNCTION_CALL_RE.search(line)
            if m:calls.add(m.group(1))
            lines.append({"line":no,"command":line})
        functions[rid]={
            "path":path,
            "calls":sorted(calls),
            "lines":lines,
            "has_summon":any(re.search(r"(?:^|\s)summon\s",x["command"]) for x in lines),
            "has_execute":any(x["command"].startswith("execute ") for x in lines),
            "has_data":any(x["command"].startswith("data ") for x in lines),
            "has_item":any(x["command"].startswith("item ") for x in lines),
        }
        for target in sorted(calls):
            if target not in closure:queue.append(target)

    # Also report source load/tick tags so R24 can prove they remain excluded.
    tags={}
    for p in (
        "data/minecraft/tags/function/load.json",
        "data/minecraft/tags/functions/load.json",
        "data/minecraft/tags/function/tick.json",
        "data/minecraft/tags/functions/tick.json",
    ):
        if p in files:
            try:tags[p]=json.loads(files[p])
            except Exception:tags[p]={"raw":files[p].decode("utf-8",errors="replace")}

    report={
        "schema":1,
        "source_sha256":builder.sha(payload),
        "enchantment_files_with_run_function":root_files,
        "root_run_function_refs":sorted(roots),
        "closure_refs":sorted(closure),
        "missing_refs":sorted(missing),
        "functions":functions,
        "source_load_tick_tags":tags,
        "summary":{
            "enchantment_files":len(root_files),
            "root_refs":len(roots),
            "closure_refs":len(closure),
            "resolved_functions":len(functions),
            "missing_refs":len(missing),
            "summon_functions":sorted(k for k,v in functions.items() if v["has_summon"]),
        },
    }
    out=ROOT/"artifacts"
    out.mkdir(exist_ok=True)
    target=out/"r24-dat-runtime-source.json"
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report["summary"],indent=2,ensure_ascii=False))
    print("report:",target)

if __name__=="__main__":
    main()
