#!/usr/bin/env python3
"""Same real-server regression, plus an unmodified-binary order control."""
from pathlib import Path
import ast, json, sys
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'qa/field-r395/run_runtime.py'
text=source.read_text()

def once(old,new):
    global text
    if text.count(old)!=1:raise ValueError('Runtime source drift: '+old[:80])
    text=text.replace(old,new,1)

anchor="    get=lambda key:report['phases'].get(key,{}).get('saved',{}).get('water_hashes')"
once(anchor,"    report['phases']['baseline-reverse']=phase('baseline-reverse',setup('baseline-reverse',plugin),ROOT/'baseline/server.jar',False,True)\n"+anchor)
once("    first=get('candidate')","    first=get('candidate')\n    report['baseline_reverse_equal']=get('baseline') is not None and get('baseline')==get('baseline-reverse')\n    report['baseline_reverse_changed_chunks']=sorted(k for k,v in (get('baseline') or {}).items() if (get('baseline-reverse') or {}).get(k)!=v)")
once("    save(OUT/'runtime.json',report)","    report['bounded_regression_pass']=report['bounded_regression_pass'] and report['baseline_reverse_equal']\n    report['combined_r396_policy']=True\n    save(OUT/'runtime.json',report)")
ast.parse(text)
(ROOT/'artifacts/generated-runtime.py').write_text(text)
sys.path.insert(0,str(source.parent))
exec(compile(text,str(source),'exec'),{'__name__':'__main__','__file__':str(source)})
