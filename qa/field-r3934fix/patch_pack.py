#!/usr/bin/env python3
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,struct,zipfile

ROOT=Path(__file__).resolve().parents[2]
R3931=ROOT/'qa/field-r3931/patch_pack.py'
NBT='data/structory_towers/structure/ocean_pillar.nbt'
FP_ROOT='neveroverworld-worldgen-fingerprint.json'
FP_RESOURCE='data/neverfolia/neveroverworld/worldgen_fingerprint.json'
REMOTE_POSITIONS={(10,21,5),(10,21,6),(10,21,7),(10,22,5),(10,22,6),(10,22,7),(10,23,6),(10,23,7)}

def need(v,m):
    if not v: raise ValueError(m)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    need(spec is not None and spec.loader is not None,'cannot load '+str(path))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

r31=load('r3931_patch',R3931)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _u16(data,p):
    return struct.unpack_from('>H',data,p)[0]

def _i32(data,p):
    return struct.unpack_from('>i',data,p)[0]

def _read_string(data,p):
    n=_u16(data,p);p+=2
    return data[p:p+n].decode('utf-8'),p+n

def _skip_payload(data,p,t):
    if t in (1,): return p+1
    if t in (2,): return p+2
    if t in (3,5): return p+4
    if t in (4,6): return p+8
    if t==7:
        n=_i32(data,p);need(n>=0,'negative byte-array');return p+4+n
    if t==8:
        n=_u16(data,p);return p+2+n
    if t==9:
        et=data[p];n=_i32(data,p+1);need(n>=0,'negative list');p+=5
        for _ in range(n): p=_skip_payload(data,p,et)
        return p
    if t==10:
        while True:
            ct=data[p];p+=1
            if ct==0:return p
            _name,p=_read_string(data,p)
            p=_skip_payload(data,p,ct)
    if t==11:
        n=_i32(data,p);need(n>=0,'negative int-array');return p+4+4*n
    if t==12:
        n=_i32(data,p);need(n>=0,'negative long-array');return p+4+8*n
    raise ValueError('unsupported NBT tag '+str(t))

def _parse_block_compound(data,p):
    start=p;state=None;pos=None
    while True:
        ct=data[p];p+=1
        if ct==0:
            return start,p,state,pos
        name,p=_read_string(data,p)
        if name=='state' and ct==3:
            state=_i32(data,p);p+=4
            continue
        if name=='pos' and ct==9:
            et=data[p];n=_i32(data,p+1);p+=5
            need(et==3 and n==3,'unexpected structure block pos list')
            pos=tuple(_i32(data,p+4*i) for i in range(3))
            p+=12
            continue
        p=_skip_payload(data,p,ct)

def remove_remote_structure_blocks(raw:bytes,state_index:int)->bytes:
    data=gzip.decompress(raw)
    p=0
    need(data[p]==10,'structure NBT root is not compound');p+=1
    _root_name,p=_read_string(data,p)

    while True:
        tag_type=data[p];p+=1
        need(tag_type!=0,'blocks list not found')
        name,p=_read_string(data,p)

        if name=='blocks':
            need(tag_type==9,'blocks is not a TAG_List')
            elem_type=data[p]
            count_offset=p+1
            count=_i32(data,count_offset)
            need(elem_type==10 and count>=0,'unexpected blocks list encoding')
            items_start=p+5
            cur=items_start
            kept=[]
            removed=[]
            for _ in range(count):
                start,end,state,pos=_parse_block_compound(data,cur)
                blob=data[start:end]
                if state==state_index and pos in REMOTE_POSITIONS:
                    removed.append(pos)
                else:
                    kept.append(blob)
                cur=end
            need(set(removed)==REMOTE_POSITIONS,'remote ocean_pillar cells did not match exactly: '+repr(sorted(removed)))
            new_count=len(kept)
            rebuilt=(
                data[:count_offset]
                + struct.pack('>i',new_count)
                + b''.join(kept)
                + data[cur:]
            )
            return gzip.compress(rebuilt,compresslevel=9,mtime=0)

        p=_skip_payload(data,p,tag_type)

def patch(raw:bytes)->tuple[bytes,dict]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos=z.infolist()
        files={i.filename:z.read(i.filename) for i in infos if not i.is_dir()}

    for p in (NBT,FP_ROOT,FP_RESOURCE):
        need(p in files,'missing '+p)

    parsed=r31._nbt_parse(files[NBT])
    palette=parsed.get('palette')
    blocks=parsed.get('blocks')
    need(isinstance(palette,list) and isinstance(blocks,list),'malformed ocean_pillar structure NBT')

    void_states={i for i,row in enumerate(palette) if isinstance(row,dict) and row.get('Name')=='minecraft:structure_void'}
    water_states={i for i,row in enumerate(palette) if isinstance(row,dict) and row.get('Name')=='minecraft:water'}
    need(len(void_states)==1,'expected one structure_void palette state')
    need(not water_states,'R39.34 input unexpectedly contains explicit water palette state')
    void_state=next(iter(void_states))

    before_positions={
        tuple(row.get('pos',[]))
        for row in blocks
        if isinstance(row,dict) and row.get('state')==void_state
    }
    need(before_positions==REMOTE_POSITIONS,'unexpected remote ocean_pillar geometry: '+repr(sorted(before_positions)))

    before_count=len(blocks)
    files[NBT]=remove_remote_structure_blocks(files[NBT],void_state)

    after=r31._nbt_parse(files[NBT])
    after_blocks=after.get('blocks')
    need(isinstance(after_blocks,list),'patched ocean_pillar blocks list missing')
    need(len(after_blocks)==before_count-8,'ocean_pillar block count did not shrink by 8')

    lingering=[
        tuple(row.get('pos',[]))
        for row in after_blocks
        if isinstance(row,dict) and tuple(row.get('pos',[])) in REMOTE_POSITIONS
    ]
    need(not lingering,'remote ocean_pillar cells still present: '+repr(lingering))

    # No explicit water is injected. The eight detached template writes simply
    # disappear, so the native ocean column remains untouched.
    after_void=r31._state_geometry(files[NBT],'minecraft:structure_void')
    after_water=r31._state_geometry(files[NBT],'minecraft:water')
    need(after_void['count']==0,'structure_void block references survived')
    need(after_water['count']==0,'explicit water block references should not be injected')

    fp=r31.content_fingerprint(files)
    for p in (FP_ROOT,FP_RESOURCE):
        d=json.loads(files[p])
        d['content_sha256']=fp
        d['entry_count_excluding_fingerprint']=len(files)-2
        files[p]=(json.dumps(d,ensure_ascii=False,indent=2)+'\n').encode()

    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as dst:
        known={i.filename:i for i in infos if not i.is_dir()}
        for name in [i.filename for i in infos if not i.is_dir()]:
            dst.writestr(known[name],files[name])

    result=out.getvalue()
    return result,{
      'ocean_pillar_detached_cells_before':8,
      'ocean_pillar_detached_cells_after':0,
      'ocean_pillar_blocks_before':before_count,
      'ocean_pillar_blocks_after':len(after_blocks),
      'ocean_pillar_explicit_water_after':0,
      'content_fingerprint':fp
    }

def verify(raw:bytes):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files={i.filename:z.read(i.filename) for i in z.infolist() if not i.is_dir()}
    root=r31._nbt_parse(files[NBT])
    blocks=root.get('blocks',[])
    positions={tuple(row.get('pos',[])) for row in blocks if isinstance(row,dict)}
    need(REMOTE_POSITIONS.isdisjoint(positions),'detached ocean_pillar cells survived in blocks list')
    void=r31._state_geometry(files[NBT],'minecraft:structure_void')
    water=r31._state_geometry(files[NBT],'minecraft:water')
    need(void['count']==0,'structure_void block references survived')
    need(water['count']==0,'explicit water should not be part of ocean_pillar template')
    fp0=json.loads(files[FP_ROOT]);fp1=json.loads(files[FP_RESOURCE])
    need(fp0==fp1,'fingerprint docs differ')
    need(fp0.get('content_sha256')==r31.content_fingerprint(files),'fingerprint mismatch')
    return {
      'detached_cells_present':0,
      'structure_void':void,
      'explicit_water':water,
      'fingerprint':fp0.get('content_sha256')
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('src',type=Path)
    ap.add_argument('dst',type=Path)
    a=ap.parse_args()
    raw=a.src.read_bytes()
    out,meta=patch(raw)
    report=verify(out)
    a.dst.parent.mkdir(parents=True,exist_ok=True)
    a.dst.write_bytes(out)
    print('R3934_PACK '+json.dumps({
      'input_sha256':sha(raw),
      'output_sha256':sha(out),
      **meta,
      'audit':report
    }))

if __name__=='__main__':main()
