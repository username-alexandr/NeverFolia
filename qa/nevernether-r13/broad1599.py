#!/usr/bin/env python3
"""Explicit original-R7 footprint coverage, not a relaxation of stage coherence.

Only the pinned 1,599-coordinate set and seed are accepted. No chunk status,
owning-thread, frozen-simulation, runtime hash or snapshot content checks change.
Builds a diagnostic plugin, never modifies the Minecraft runtime or an old world.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
PLAN_SHA='cb4f123132048322c8601eaf097ca68679128882a9269f43fe9740dff285d2e6'
PROBE_SHA='1d8af899ba9089ead80b91bdb49edc1d4c5cbd2549c080c494b4efb0cc464bea'
COUNT=1599

def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise RuntimeError(path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

RUNNER=module('broad_runner',ROOT/'qa/nevernether-r8/run-stage-probe.py')

def plan_hash(chunks:list) -> str:
    return hashlib.sha256(''.join(f'{x},{z}\n' for x,z in sorted(chunks)).encode()).hexdigest()

def validate(value:dict,seed:int) -> dict:
    if not isinstance(value,dict) or type(value.get('seed')) is not int or seed!=7270913 or value['seed']!=seed:
        raise ValueError('Original R7 footprint seed is exactly 7270913')
    chunks=value.get('chunks')
    if not isinstance(chunks,list) or len(chunks)!=COUNT:raise ValueError('Expected all 1599 original R7 coordinates')
    for pair in chunks:
        if not isinstance(pair,list) or len(pair)!=2 or any(type(n) is not int for n in pair):raise ValueError('Invalid integer pair')
    if len(set(map(tuple,chunks)))!=COUNT or plan_hash(chunks)!=PLAN_SHA:raise ValueError('Original footprint coordinate identity mismatch')
    if value.get('stop_after_carvers') or value.get('verify_saved_only'):raise ValueError('This full-coverage runner is not a restart adapter')
    return value

def original_plan()->dict:
    value=json.loads((ROOT/'qa/nevernether-r13/original-r7-coverage.json').read_text())
    if value.get('schema')!=1 or value.get('coordinate_sha256')!=PLAN_SHA:raise ValueError('Invalid coverage manifest')
    chunks=[]
    for row in value['rows']:
        if len(row)!=3 or any(type(n) is not int for n in row) or not row[1]<=row[2] or row[2]-row[1]>1599:raise ValueError('Invalid bounded coverage row')
        chunks.extend([[row[0],z] for z in range(row[1],row[2]+1)])
        if len(chunks)>COUNT:raise ValueError('Oversized coverage manifest')
    return validate({'seed':value['seed'],'coverage':'original-r7-1599','chunks':chunks},7270913)

def checked_plan(path:Path,seed:int,reverse:bool)->dict:
    value=validate(json.loads(path.read_text()),seed)
    if reverse:value['chunks']=list(reversed(value['chunks']))
    return value

def probe_source()->str:
    text=(ROOT/'qa/nevernether-r11/NeverNetherLifecycleProbeR11.java').read_text()
    if hashlib.sha256(text.encode()).hexdigest()!=PROBE_SHA:raise ValueError('Changed diagnostic capture source')
    changes=[
        ('raw.size()>512','raw.size()!=1599'),
        ('Expected 1..512 explicitly selected chunks','Expected exactly 1599 pinned R7 chunks'),
        ('Math.abs((long)z))<64','Math.abs((long)z))<6'),
        ('        Files.createDirectories(output);',
         '        var ordered=new ArrayList<int[]>(chunks);ordered.sort(Comparator.<int[]>comparingInt(c->c[0]).thenComparingInt(c->c[1]));\n'
         '        var canonical=new StringBuilder();for(var c:ordered)canonical.append(c[0]).append(",").append(c[1]).append("\\n");\n'
         '        var planHash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)));\n'
         '        if(level.getSeed()!=7270913L || !planHash.equals("'+PLAN_SHA+'"))throw new IllegalArgumentException("Unrecognized R7 footprint plan");\n'
         '        report.addProperty("exact_r7_coverage_sha256",planHash);\n'
         '        Files.createDirectories(output);')]
    for old,new in changes:
        if text.count(old)!=1:raise ValueError('Changed capture anchor: '+old)
        text=text.replace(old,new)
    return text

def build(java_home:Path,runtime:Path,destination:Path)->None:
    entries,_=RUNNER.runtime_inventory(runtime)
    import os
    destination.mkdir(parents=True,exist_ok=False)
    source=destination/'NeverNetherLifecycleProbeR11.java';source.write_text(probe_source())
    classes=destination/'classes';classes.mkdir()
    subprocess.run([str(java_home/'bin/javac'),'-cp',os.pathsep.join(entries),'-d',str(classes),str(source)],check=True)
    (classes/'plugin.yml').write_bytes((ROOT/'qa/nevernether-r11/plugin.yml').read_bytes())
    subprocess.run([str(java_home/'bin/jar'),'--create','--file',str(destination/'broad1599-qa.jar'),'-C',str(classes),'.'],check=True)
    (destination/'build.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'template_sha256':PROBE_SHA,'coverage_sha256':PLAN_SHA,'jar_sha256':RUNNER.sha(destination/'broad1599-qa.jar')},indent=2))

def compare(left:Path,right:Path,relation:str='reverse')->dict:
    for root in (left,right):
        report=json.loads((root/'plugins/NN-STAGE-R8-QA/report.json').read_text())
        validate(report['plan'],report['seed'])
        if report.get('exact_r7_coverage_sha256')!=PLAN_SHA:raise ValueError('Broad probe coverage stamp missing')
    comparator=module('broad_comparator',ROOT/'scripts/compare-never-nether-stages-r8.py')
    result=comparator.compare(left,right,relation,max_chunks=COUNT)
    result['exact_r7_coverage_sha256']=PLAN_SHA
    result['scope']='Original R7 1599-coordinate set, frozen three-stage block snapshots. Not dynamic fluids, structure traversal or release acceptance.'
    return result

def main()->int:
    if len(sys.argv)>1 and sys.argv[1]=='run':
        sys.argv=[sys.argv[0],*sys.argv[2:]]
        return RUNNER.main(plan_validator=checked_plan)
    if len(sys.argv)>1 and sys.argv[1]=='plan':
        print(json.dumps(original_plan(), separators=(',', ':')))
        return 0
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    b=subs.add_parser('build-plugin');b.add_argument('--java-home',type=Path,required=True);b.add_argument('--runtime-dir',type=Path,required=True);b.add_argument('--new-directory',type=Path,required=True)
    c=subs.add_parser('compare');c.add_argument('--left',type=Path,required=True);c.add_argument('--right',type=Path,required=True);c.add_argument('--relation',choices=('same','reverse'),default='reverse');c.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.command=='build-plugin':build(a.java_home,a.runtime_dir,a.new_directory);return 0
        result=compare(a.left,a.right,a.relation);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
        print({k:v['different_blocks'] for k,v in result['cross_order'].items()});return 0 if result['generation_stage_equal'] else 2
    except (OSError,ValueError,KeyError,TypeError) as error:p.exit(2,f'Invalid broad probe: {error}\n')

if __name__=='__main__':raise SystemExit(main())
