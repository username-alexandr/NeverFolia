#!/usr/bin/env python3
"""R14 fixed-envelope FULL diagnostic, bounded explicit plans, NEW worlds only."""
import importlib.util
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('r14_runner',ROOT/'qa/nevernether-r8/run-stage-probe.py')
R=importlib.util.module_from_spec(s);s.loader.exec_module(R)
# Leave native/off-heap and OS headroom in the measured 4 GiB QA environment.
# The same explicit flags are recorded and enforced in both orders and restarts.
JVM_FLAGS=['-Xms512M','-Xmx2304M','-XX:ActiveProcessorCount=4',
           '-Dpaper.disablePluginRemapping=true','-Dneverfolia.qa.stageProbe=true']
R.SUPERVISOR.JVM_FLAGS=list(JVM_FLAGS)
def checked_plan(path,seed,reverse):
    v=json.loads(path.read_text());c=v.get('chunks')
    if type(v.get('seed')) is not int or v['seed']!=seed or not isinstance(c,list) or not 1<=len(c)<=2048:raise ValueError('Invalid R14 seed/plan')
    for p in c:
        if not isinstance(p,list) or len(p)!=2 or any(type(n) is not int for n in p) or not 6<=max(abs(n) for n in p)<=100000:raise ValueError('Invalid R14 integer coordinates')
    if len(c)!=len(set(map(tuple,c))):raise ValueError('Duplicate R14 coordinates')
    if v.get('readback'):raise ValueError('Use the explicit saved-world readback routine')
    if reverse:v['chunks']=list(reversed(c))
    return v
if __name__=='__main__':raise SystemExit(R.main(plan_validator=checked_plan))
