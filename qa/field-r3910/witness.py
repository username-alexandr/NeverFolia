#!/usr/bin/env python3
"""Independent Python flood oracle for immutable Java witness files. Read-only.
Certifies the recorded finite input, NOT global closure or concurrent acquisition.
"""
from collections import deque
from pathlib import Path
import gzip,struct

MAX_BYTES=2_200_000

def bit(raw,index):return index//8<len(raw) and bool(raw[index//8]&(1<<(index%8)))
def setbit(raw,index):raw[index//8]|=1<<(index%8)

def reachable(width,depth,height,cells,sky,lava_extra):
    area=width*depth;count=area*height
    if width<1 or depth<1 or height<1 or count>2_000_000 or len(cells)!=count or len(sky)!=area:
        raise ValueError('Invalid finite volume')
    if any(code>5 for code in cells) or any(code not in (0,1) for code in sky):raise ValueError('Unknown state code')
    if len(lava_extra)>(count+7)//8:raise ValueError('Oversized lava mask')
    allowed=bytearray(code in (3,4) for code in cells)
    for i,code in enumerate(cells):
        if bit(lava_extra,i):allowed[i]=0
        if code!=5:continue
        x=i%width;z=(i//width)%depth
        if x:allowed[i-1]=0
        if x+1<width:allowed[i+1]=0
        if z:allowed[i-width]=0
        if z+1<depth:allowed[i+width]=0
        if i>=area:allowed[i-area]=0
        if i+area<count:allowed[i+area]=0
    seen=bytearray(count);pending=deque();top=(height-1)*area
    for p,open_sky in enumerate(sky):
        i=top+p
        if open_sky and allowed[i]:seen[i]=1;pending.append(i)
    while pending:
        i=pending.popleft();x=i%width;z=(i//width)%depth
        targets=[]
        if x:targets.append(i-1)
        if x+1<width:targets.append(i+1)
        if z:targets.append(i-width)
        if z+1<depth:targets.append(i+width)
        if i>=area:targets.append(i-area)
        if i+area<count:targets.append(i+area)
        for other in targets:
            if allowed[other] and not seen[other]:seen[other]=1;pending.append(other)
    return seen

def certify(width,depth,height,cells,sky,lava_extra,writes):
    if width!=depth or width%3:raise ValueError('Expected square three-chunk window')
    side=width//3;area=width*depth;owner_count=height*side*side
    if len(writes)>(owner_count+7)//8:raise ValueError('Oversized write mask')
    seen=reachable(width,depth,height,cells,sky,lava_extra)
    expected=bytearray((owner_count+7)//8);coordinates=[]
    for y in range(height):
        for z in range(side):
            for x in range(side):
                local=(y*side+z)*side+x;global_index=y*area+(z+side)*width+x+side
                permitted=cells[global_index]==3 and bool(seen[global_index])
                if permitted:setbit(expected,local);coordinates.append((x,y,z))
                if bit(writes,local)!=permitted:raise ValueError('Invalid/missing write at owner index '+str(local))
    if owner_count%8 and len(writes)==len(expected) and writes[-1]>>(owner_count%8):raise ValueError('Out-of-volume write bits')
    return coordinates,sum(seen)

def read(path):
    with gzip.open(path,'rb') as stream:raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Witness exceeds bounded size')
    position=0
    def integer():
        nonlocal position
        if position+4>len(raw):raise ValueError('Truncated header')
        value=struct.unpack_from('>i',raw,position)[0];position+=4;return value
    def block(limit):
        nonlocal position
        length=integer()
        if length<0 or length>limit or position+length>len(raw):raise ValueError('Invalid witness field')
        value=raw[position:position+length];position+=length;return value
    if integer()!=0x4e4c3130 or integer()!=1:raise ValueError('Unknown witness format')
    cx,cz,width,depth,height,low=[integer() for _ in range(6)]
    if (width,depth,height,low)!=(48,48,640,-511):raise ValueError('Unexpected production witness envelope')
    cells=block(2_000_000);sky=block(2304);lava=block(184320);writes=block(20480)
    if position!=len(raw):raise ValueError('Trailing witness bytes')
    coordinates,visited=certify(width,depth,height,cells,sky,lava,writes)
    return {'chunk':[cx,cz],'writes':[(cx*16+x,low+y,cz*16+z) for x,y,z in coordinates],
            'added':len(coordinates),'visited':visited,'global_closure_proven':False}
