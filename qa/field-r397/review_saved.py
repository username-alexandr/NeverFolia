#!/usr/bin/env python3
"""Read-only replay of the first R397 archive with coordinate-validated comparison."""
from pathlib import Path
import ast, hashlib
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'qa/field-r395/review_differences.py'
raw=source.read_bytes()
if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!='a159e6d6ba8e51fb085694587acdfa5bb7844c58':
    raise ValueError('Wrong retained comparison parser')
text=raw.decode()
def once(old,new):
    global text
    if text.count(old)!=1:raise ValueError('Review drift: '+old[:100])
    text=text.replace(old,new,1)
once("E=ROOT/'evidence'","E=ROOT/'artifacts'")
once("'8b387b040b9b3b2a1412d364dbc9eaa0bbb763f69b249c7c213b19812da8a4d5'","'42a0153d207c042f309ee9091355f1c830326fdd5450387a2c26ea4ee11c2639'")
once("for name in ('baseline','candidate','restart','reverse'):","for name in ('baseline','candidate','restart','reverse','baseline-reverse'):")
once("'source_run':36324714489","'source_run':36332731284")
once("            row={'position':[x,y,z]", "            if (x//16,z//16)!=(cx,cz):raise ValueError('Computed position is outside owner chunk')\n            row={'position':[x,y,z]")
once("'baseline_forward':old[i],", "'baseline_forward':old[i],'baseline_reverse':phases['baseline-reverse'][1].section((cx,sy,cz))[i],")
ast.parse(text)
exec(compile(text,str(source),'exec'),{'__name__':'__main__','__file__':str(source)})
