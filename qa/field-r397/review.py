#!/usr/bin/env python3
"""Compare immutable input snapshots; do not exclude seams or modify worlds."""
from pathlib import Path
from collections import Counter
import gzip, json, struct
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts'

def read(path):
    raw=gzip.decompress(path.read_bytes());at=0
    def integer():
        nonlocal at
        if at+4>len(raw):raise ValueError('Truncated witness integer')
        v=struct.unpack_from('>i',raw,at)[0];at+=4;return v
    magic,cx,cz,w,d,h,low=[integer() for _ in range(7)]
    if magic!=0x52333937 or (w,d,h,low)!=(48,48,640,-511):raise ValueError('Invalid witness header')
    def data(maximum,exact=None):
        nonlocal at
        n=integer()
        if not 0<=n<=maximum or (exact is not None and n!=exact) or at+n>len(raw):raise ValueError('Invalid witness length')
        v=raw[at:at+n];at+=n;return v
    cells=data(w*d*h,w*d*h);sky=data(w*d,w*d);lava=data((len(cells)+7)//8);connected=data((len(cells)+7)//8)
    if at!=len(raw) or any(v>5 for v in cells) or any(v>1 for v in sky):raise ValueError('Invalid witness payload')
    if path.name!=f'{cx}_{cz}.bin.gz':raise ValueError('Wrong witness filename/coordinates')
    return {'cx':cx,'cz':cz,'cells':cells,'sky':sky,'lava':lava,'connected':connected}

def bit(raw,k):return k//8<len(raw) and bool(raw[k//8]&(1<<(k%8)))
def position(a,i):return [a['cx']*16-16+i%48,-511+i//2304,a['cz']*16-16+(i//48)%48]
def canonical(c):return 3 if c==4 else c

def main():
    left={p.name:p for p in (OUT/'proof-candidate/witness').glob('*.bin.gz')}
    right={p.name:p for p in (OUT/'proof-reverse/witness').glob('*.bin.gz')}
    if not left or left.keys()!=right.keys():raise ValueError('Missing candidate/reverse witnesses')
    rows=[]
    for name in sorted(left):
        a,b=read(left[name]),read(right[name]);pairs=Counter();examples=[];reach=[];raw_changes=0;reach_count=0
        if (a['cx'],a['cz'])!=(b['cx'],b['cz']):raise ValueError('Mismatched owner coordinates')
        for i,(old,new) in enumerate(zip(a['cells'],b['cells'])):
            if old!=new:raw_changes+=1
            if canonical(old)!=canonical(new):
                pairs[f'{old}->{new}']+=1
                if len(examples)<48:examples.append({'position':position(a,i),'candidate':old,'reverse':new})
            x=i%48;z=(i//48)%48
            if 16<=x<32 and 16<=z<32 and bit(a['connected'],i)!=bit(b['connected'],i):
                reach_count+=1
                if len(reach)<32:reach.append({'position':position(a,i),'candidate_cell':old,'reverse_cell':new,'candidate_connected':bit(a['connected'],i),'reverse_connected':bit(b['connected'],i)})
        sky=[{'x':a['cx']*16-16+i%48,'z':a['cz']*16-16+i//48,'candidate':old,'reverse':new} for i,(old,new) in enumerate(zip(a['sky'],b['sky'])) if old!=new]
        rows.append({'chunk':[a['cx'],a['cz']],'raw_changes':raw_changes,'passability_changes':dict(pairs),'examples':examples,'owner_reachability_count':reach_count,'owner_reachability_examples':reach,'sky_changes':sky[:48],'sky_change_count':len(sky),'lava_equal':a['lava']==b['lava']})
    output={'source':'R397 before-write witness arrays from actual JVMs','classification_codes':{'unknown':0,'solid':1,'protected':2,'air':3,'water':4,'lava':5},'rows':rows,'production_accepted':False}
    (OUT/'witness-review.json').write_text(json.dumps(output,indent=2)+'\n')
    print('R397_WITNESS_REVIEW',json.dumps(output),flush=True)
if __name__=='__main__':main()
