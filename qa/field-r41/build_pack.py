#!/usr/bin/env python3
"""Use complete biome cart models and verify every existing profession variant."""
import importlib.util,sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
subprocess.run([sys.executable,str(ROOT/'qa/field-r41/inspect_remaining.py')],check=True)
p=ROOT/'qa/field-r41/repair_pack.py';s=importlib.util.spec_from_file_location('r41_repair',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
original=m.load
def load(path,name):
    if name=='r41carts':path=ROOT/'qa/field-r41/carts.py'
    return original(path,name)
m.load=load
m.main()
