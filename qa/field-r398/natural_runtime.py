#!/usr/bin/env python3
"""Extend, never relax, the existing absolute saved-water acceptance test."""
from pathlib import Path
import ast,hashlib,sys
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'qa/field-r395/run_runtime.py';raw=source.read_bytes()
if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!='00fb8fcffea1f30252ee2a223ae4c96aee1e2fe5':raise ValueError('Pinned runtime changed')
text=raw.decode()
def once(old,new):
 global text
 if text.count(old)!=1:raise ValueError('Runtime anchor changed: '+old[:80])
 text=text.replace(old,new,1)
anchor="    get=lambda key:report['phases'].get(key,{}).get('saved',{}).get('water_hashes')"
once(anchor,"    report['phases']['baseline-reverse']=phase('baseline-reverse',setup('baseline-reverse',plugin),ROOT/'baseline/server.jar',False,True)\n    report['phases']['baseline-repeat']=phase('baseline-repeat',setup('baseline-repeat',plugin),ROOT/'baseline/server.jar',False,False)\n"+anchor)
once("    first=get('candidate')","    first=get('candidate')\n    report['baseline_reverse_equal']=get('baseline') is not None and get('baseline')==get('baseline-reverse')\n    report['baseline_repeat_equal']=get('baseline') is not None and get('baseline')==get('baseline-repeat')\n    report['baseline_reverse_changed_chunks']=sorted(k for k,v in (get('baseline') or {}).items() if (get('baseline-reverse') or {}).get(k)!=v)\n    report['baseline_repeat_changed_chunks']=sorted(k for k,v in (get('baseline') or {}).items() if (get('baseline-repeat') or {}).get(k)!=v)")
once("    save(OUT/'runtime.json',report)","    report['bounded_regression_pass']=report['bounded_regression_pass'] and report['baseline_reverse_equal'] and report['baseline_repeat_equal']\n    report['r398_full_guards_installed']=True\n    report['combined_r396_policy']=True\n    save(OUT/'runtime.json',report)")
ast.parse(text);(ROOT/'artifacts/r398-generated-runtime.py').write_text(text)
sys.path.insert(0,str(source.parent))
exec(compile(text,str(source),'exec'),{'__name__':'__main__','__file__':str(source)})
