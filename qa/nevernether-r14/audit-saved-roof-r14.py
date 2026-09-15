#!/usr/bin/env python3
"""Read-only R14 stopped-region audit: real block states and canonical metadata.

Checks every selected section's saved identity, metadata digest and current-block
hash against the actual Anvil palette. Does not simulate players or fluid ticks.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,struct
from collections import Counter
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def mod(n,p):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
H=mod('r14_saved_nbt',ROOT/'scripts/hash-never-nether-chunks.py')
C=mod('r14_saved_observations',Path(__file__).with_name('compare-roof-r14.py'))
KEY='neverfolia:substrate_r11';SIZE=4096
POS=np.arange(SIZE,dtype=np.uint64)
SINGLE_HASH={}

def text_utf(value):
    # Canonical block names, properties and this profile use ASCII only, where
    # Java modified UTF-8 and ordinary UTF-8 are byte-identical.
    raw=value.encode('ascii')
    if len(raw)>65535:raise ValueError('oversized canonical string')
    return struct.pack('>H',len(raw))+raw

def canonical_digest(m):
    parts=[struct.pack('>i',m[k]) for k in ('Schema','ChunkX','ChunkZ','SectionY','Bits')]
    parts.extend((struct.pack('>q',m['Seed']),text_utf(m['Profile']),struct.pack('>i',len(m['Palette']))))
    parts.extend(text_utf(v) for v in m['Palette'])
    for key in ('Original','External'):
        a=m[key]['$long_array'];parts.append(struct.pack('>i',len(a)));parts.append(struct.pack('>'+str(len(a))+'q',*a))
    for key in ('ProposalIndices','ProposalStates'):
        a=m[key]['$int_array'];parts.append(struct.pack('>i',len(a)));parts.append(struct.pack('>'+str(len(a))+'i',*a))
    raw=bytes.fromhex(m['CurrentHash']['$byte_array'])
    if len(raw)!=32:raise ValueError('Invalid current hash')
    parts.append(raw);return hashlib.sha256(b''.join(parts)).hexdigest()

def name(p):
    ident=p['Name'];props=p.get('Properties',{})
    return ident if not props else ident+'['+','.join(k+'='+props[k] for k in sorted(props))+']'

def indices(container):
    palette=container['palette']
    if not 1<=len(palette)<=4096:raise ValueError('Bad block palette')
    if len(palette)==1:return np.zeros(SIZE,dtype=np.int64)
    bits=max(4,(len(palette)-1).bit_length());per=64//bits
    values=container['data']['$long_array']
    if len(values)!=(SIZE+per-1)//per:raise ValueError('Wrong packed length')
    data=np.asarray(values,dtype=np.int64).view(np.uint64)
    idx=((data[POS//per]>>((POS%per)*bits))&((1<<bits)-1)).astype(np.int64)
    if int(idx.max())>=len(palette):raise ValueError('Packed index outside palette')
    return idx

def section_data(container):
    names=[name(x) for x in container['palette']];idx=indices(container)
    if len(names)==1:
        n=names[0]
        if n not in SINGLE_HASH:
            b=n.encode();SINGLE_HASH[n]=hashlib.sha256((struct.pack('>i',len(b))+b)*SIZE).hexdigest()
        h=SINGLE_HASH[n]
    else:
        encoded=np.array([struct.pack('>i',len(s.encode()))+s.encode() for s in names],dtype=object)
        h=hashlib.sha256(b''.join(encoded[idx].tolist())).hexdigest()
    return names,idx,h

def provenance(m,names,current_indices):
    palette=m['Palette']
    if not 1<=len(palette)<=4096 or len(set(palette))!=len(palette):raise ValueError('Invalid substrate palette')
    bits=m['Bits'];expected=(len(palette)-1).bit_length()
    if type(bits) is not int or bits!=expected:raise ValueError('Invalid original palette width')
    values=m['Original']['$long_array'];per=SIZE if bits==0 else 64//bits
    if len(values)!=(0 if bits==0 else (SIZE+per-1)//per):raise ValueError('Invalid original packed length')
    original=np.zeros(SIZE,dtype=np.int64)
    if bits:
        raw=np.asarray(values,dtype=np.int64).view(np.uint64)
        original=((raw[POS//per]>>((POS%per)*bits))&((1<<bits)-1)).astype(np.int64)
        used=np.minimum(per,SIZE-np.arange(len(raw),dtype=np.uint64)*per)*bits
        if np.any(raw>>used) or int(original.max())>=len(palette):raise ValueError('Invalid original indices/padding')
    flags=m['External']['$long_array']
    if len(flags)>64:raise ValueError('Oversized external bitmap')
    raw=np.zeros(64,dtype=np.uint64)
    raw[:len(flags)]=np.asarray(flags,dtype=np.int64).view(np.uint64)
    external=((raw[POS//64]>>(POS%64))&1).astype(bool)
    pi=np.asarray(m['ProposalIndices']['$int_array'],dtype=np.int64);ps=np.asarray(m['ProposalStates']['$int_array'],dtype=np.int64)
    if len(pi)!=len(ps) or len(pi)>SIZE:raise ValueError('Invalid proposal arrays')
    if len(pi) and (pi[0]<0 or pi[-1]>=SIZE or np.any(np.diff(pi)<=0) or int(ps.min())<0 or int(ps.max())>=len(palette) or np.any(external[pi])):raise ValueError('Invalid proposal provenance')
    current=np.asarray(names,dtype=object)[current_indices]
    baseline=np.asarray(palette,dtype=object)[original]
    if len(pi):
        own=np.asarray(palette,dtype=object)[ps]
        if np.any(current[pi]!=own):raise ValueError('Own proposal not equal to saved block')
        baseline[pi]=own
    if np.any(current[~external]!=baseline[~external]):raise ValueError('Unrecorded saved block change')


def audit(world,plan_path):
    evidence=json.loads((world/'run-evidence.json').read_text())
    if evidence.get('stage')!='completed' or evidence.get('process_exit_code')!=0 or evidence.get('forced_stop') is not False:raise ValueError('World was not stopped normally')
    plan=json.loads(plan_path.read_text());seed=plan['seed'];coords=list(map(tuple,plan['chunks']))
    if len(coords)!=len(set(coords)) or not 1<=len(coords)<=2048 or seed!=evidence['seed']:raise ValueError('Invalid selected plan')
    coverage=hashlib.sha256(''.join(f'{x},{z}\n' for x,z in sorted(coords)).encode()).hexdigest()
    root=world/'world/dimensions/minecraft/the_nether/region';counts=Counter();starts={};blocks=Counter();failures=[]
    for cx,cz in coords:
        nbt=H.read_chunk_nbt(root,cx,cz)
        if (nbt.get('xPos'),nbt.get('zPos'))!=(cx,cz) or nbt.get('Status')!='minecraft:full':raise ValueError('Not a saved FULL selected chunk')
        sections={}
        for section in nbt['sections']:
            sy=section['Y']
            if 'block_states' not in section:continue
            if sy in sections:raise ValueError('Duplicate saved section')
            if not -8<=sy<=32:raise ValueError('Block storage outside R14 envelope')
            sections[sy]=section
        if set(sections)!=set(range(-8,33)):raise ValueError('Missing R14 saved block sections')
        for sy,section in sections.items():
            m=section.get(KEY)
            if not isinstance(m,dict) or m.get('Schema')!=1 or m.get('Profile')!=C.PROFILE or m.get('Seed')!=seed or (m.get('ChunkX'),m.get('SectionY'),m.get('ChunkZ'))!=(cx,sy,cz):raise ValueError('Wrong persisted R14 identity')
            if canonical_digest(m)!=m['Digest']['$byte_array']:raise ValueError('Invalid canonical metadata digest')
            palette,idx,current=section_data(section['block_states'])
            if current!=m['CurrentHash']['$byte_array']:raise ValueError('Persisted blocks do not match substrate current hash')
            provenance(m,palette,idx)
            counts['validated_section_digests']+=1
            ns,ncounts=np.unique(idx,return_counts=True)
            for n,k in zip(ns,ncounts):blocks[palette[int(n)]]+=int(k)
            if sy==32:
                roof=[palette[int(i)] for i in idx[:256]]
                if any(s!='minecraft:bedrock' for s in roof):failures.append({'chunk':[cx,cz],'reason':'roof_not_bedrock'})
                above={palette[int(i)] for i in np.unique(idx[256:])}
                if not above<={'minecraft:air','minecraft:cave_air','minecraft:void_air'}:failures.append({'chunk':[cx,cz],'reason':'padding_non_air','states':sorted(above)})
                counts['roof_cells_checked']+=256;counts['padding_cells_checked']+=3840
        counts['saved_full_chunks_checked']+=1
        for sid,st in nbt.get('structures',{}).get('starts',{}).items():
            if st.get('id')==sid and sid!='INVALID':starts[f'{sid}@{cx},{cz}']={'id':sid,'chunk':[cx,cz],'parts':len(st.get('Children',[]))}
    return dict(schema=1,audit='NN-R14-real-saved-sections',seed=seed,coverage_sha256=coverage,profile=C.PROFILE,counts=dict(counts),failures=failures,roof_storage_pass=not failures,
        canonical_metadata_and_current_block_hashes_pass=True,section_provenance_invariants_pass=True,all_block_states_included=True,blocks=dict(blocks),starts=starts,release_ready=False,
        scope='All selected saved FULL palettes, per-section metadata identities/digests/current hashes, exact roof and empty padding; no fluid simulation or player packet test.')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('world','plan','output'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args()
    if a.output.resolve().is_relative_to(a.world.resolve()):p.error('Write report outside input world')
    r=audit(a.world,a.plan);a.output.write_text(json.dumps(r,indent=2)+'\n');print(r['counts'],r['roof_storage_pass'])
    return 0 if r['roof_storage_pass'] else 2
if __name__=='__main__':raise SystemExit(main())
