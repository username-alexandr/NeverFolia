#!/usr/bin/env python3
"""Independent Python BFS over actual pre-write Java witnesses. Read-only.
It proves reachability within the captured volume, NOT global closure or the
consistency of every live neighbour with an earlier generation stage.
"""
from collections import deque
from pathlib import Path
import gzip,hashlib,json,struct,unittest
UNKNOWN,SOLID,PROTECTED,AIR,WATER,LAVA=range(6)

def need(ok,message):
    if not ok:raise ValueError(message)

def neighbours(i,w,d,h):
    area=w*d;x=i%w;z=i//w%d
    if x:yield i-1
    if x+1<w:yield i+1
    if z:yield i-w
    if z+1<d:yield i+w
    if i>=area:yield i-area
    if i+area<area*h:yield i+area

def reachable(w,d,h,cells,sky,extra):
    count=w*d*h;area=w*d
    need(w>0 and d>0 and h>0 and len(cells)==count and len(sky)==area,'Invalid witness shape')
    need(all(0<=n<=5 for n in set(cells)) and set(sky)<={0,1},'Unknown witness codes')
    blocked=bytearray(count)
    for i in extra:
        need(0<=i<count,'Lava barrier outside volume');blocked[i]=1
    start=0
    while True:
        i=cells.find(bytes([LAVA]),start)
        if i<0:break
        for n in neighbours(i,w,d,h):blocked[n]=1
        start=i+1
    seen=bytearray(count);q=deque();top=(h-1)*area
    for p,value in enumerate(sky):
        i=top+p
        if value and cells[i] in (AIR,WATER) and not blocked[i]:seen[i]=1;q.append(i)
    visited=len(q)
    while q:
        i=q.popleft()
        for n in neighbours(i,w,d,h):
            if not seen[n] and not blocked[n] and cells[n] in (AIR,WATER):seen[n]=1;q.append(n);visited+=1
    return seen,visited

def bits(raw):
    for j,value in enumerate(raw):
        for k in range(8):
            if value&(1<<k):yield j*8+k

def decode(path):
    with gzip.open(path,'rb') as stream:raw=stream.read(2_000_001)
    need(len(raw)<=2_000_000,'Oversized witness')
    need(raw[:8]==b'NF40W001' and len(raw)>=32,'Wrong witness header')
    w,d,h,low,cx,cz=struct.unpack_from('>6i',raw,8)
    need((w,d,h,low)==(48,48,640,-511),'Wrong world envelope')
    offset=32;count=w*d*h;area=w*d
    need(len(raw)>=offset+count+area+8,'Truncated witness')
    cells=raw[offset:offset+count];offset+=count;sky=raw[offset:offset+area];offset+=area
    arrays=[]
    for maximum in ((count+7)//8,(640*256+7)//8):
        need(len(raw)>=offset+4,'Missing bitset size');size=struct.unpack_from('>i',raw,offset)[0];offset+=4
        need(0<=size<=maximum and len(raw)>=offset+size,'Invalid bitset size')
        arrays.append(set(bits(raw[offset:offset+size])));offset+=size
    need(offset==len(raw),'Trailing witness data')
    need(all(i<640*256 for i in arrays[1]),'Owner write outside bounds')
    return w,d,h,low,cx,cz,cells,sky,arrays[0],arrays[1],hashlib.sha256(raw).hexdigest()

def verify(report_path):
    report=json.loads(Path(report_path).read_text())
    need(report.get('revision')=='R40-combined-bounded-ocean-v1','Wrong revision')
    filename=report.get('witness_file','')
    need(filename==Path(filename).name and filename.endswith('.witness.gz'),'Invalid witness filename')
    w,d,h,low,cx,cz,cells,sky,extra,writes,digest=decode(Path(report_path).parent/filename)
    need((cx,cz)==(report['chunk_x'],report['chunk_z']),'Wrong witness coordinates')
    seen,visited=reachable(w,d,h,cells,sky,extra);expected=set();unproven=0;protected=0
    for y in range(h):
        for z in range(16):
            for x in range(16):
                i=y*w*d+(z+16)*w+x+16;local=(y<<8)|(z<<4)|x
                if cells[i]==PROTECTED:protected+=1
                if cells[i]==AIR:
                    if seen[i]:expected.add(local)
                    else:unproven+=1
    need(writes==expected,'Writes do not exactly match positively connected owner AIR')
    need(len(writes)==report['added_air_to_water'] and visited==report['visited_witness_cells'],'Witness/report count mismatch')
    need(unproven==report['unproven_owner_air'],'Unproven air count mismatch')
    need(report['native_aquatic_cells']==report['preserved_aquatic_cells'] and report['snapshot_write_conflicts']==0,'Unsafe runtime transition')
    need(report['global_closure_proven'] is False,'False global-closure claim')
    return {'chunk':[cx,cz],'added':len(writes),'unproven_air':unproven,'protected_witness_cells':protected,
            'visited':visited,'witness_sha256':digest,'witness_file':filename,'pass':True},writes

class Tests(unittest.TestCase):
    def test_open_column(self):
        self.assertEqual(sum(reachable(1,1,3,bytes([AIR]*3),bytes([1]),set())[0]),3)
    def test_roof_without_seed(self):
        self.assertEqual(sum(reachable(1,1,3,bytes([AIR,AIR,SOLID]),bytes([1]),set())[0]),0)
    def test_protected(self):
        seen,_=reachable(1,1,3,bytes([AIR,PROTECTED,WATER]),bytes([1]),set());self.assertEqual(list(seen),[0,0,1])
    def test_unknown_is_barrier(self):
        seen,_=reachable(1,1,3,bytes([AIR,UNKNOWN,WATER]),bytes([1]),set());self.assertEqual(list(seen),[0,0,1])
    def test_lava_neighbour(self):
        self.assertEqual(sum(reachable(1,1,3,bytes([LAVA,AIR,WATER]),bytes([1]),set())[0]),1)
    def test_external_lava(self):
        self.assertEqual(sum(reachable(1,1,3,bytes([AIR]*3),bytes([1]),{2})[0]),0)
    def test_no_row_wrap(self):
        seen,_=reachable(2,2,1,bytes([SOLID,AIR,AIR,SOLID]),bytes([0,1,0,0]),set());self.assertEqual(list(seen),[0,1,0,0])
    def test_side_path_under_roof(self):
        seen,_=reachable(2,1,2,bytes([AIR,AIR,WATER,SOLID]),bytes([1,0]),set());self.assertEqual(list(seen),[1,1,1,0])
    def test_water_air_connectivity_same(self):
        self.assertEqual(reachable(2,1,2,bytes([AIR,AIR,WATER,SOLID]),bytes([1,0]),set())[0],reachable(2,1,2,bytes([WATER,AIR,WATER,SOLID]),bytes([1,0]),set())[0])
    def test_bitset_little_endian(self):self.assertEqual(set(bits(bytes([129,2]))),{0,7,9})
    def test_bad_codes(self):
        with self.assertRaises(ValueError):reachable(1,1,1,bytes([99]),bytes([1]),set())
    def test_invalid_extra(self):
        with self.assertRaises(ValueError):reachable(1,1,1,bytes([AIR]),bytes([1]),{1})
if __name__=='__main__':unittest.main(verbosity=2)
