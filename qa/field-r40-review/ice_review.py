#!/usr/bin/env python3
"""Read-only review of the failed R40 matrix. Does not rerun, edit or accept worldgen.
Witnesses retain categories, not exact pre-write state names: that limitation is
reported explicitly. This review never whitelists ice to make the kernel pass.
"""
from pathlib import Path,PurePosixPath
import collections,hashlib,importlib.util,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];E=ROOT/'evidence';OUT=ROOT/'ice-review';WORK=ROOT/'.work/r40-ice-review'
sys.path.insert(0,str(ROOT/'qa/field-r40'))
from witness import decode,need,AIR,WATER,SOLID,PROTECTED,LAVA

def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def extract(archive,dest):
    dest.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        need(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),'Invalid saved archive')
        for info in z.infolist():
            p=PurePosixPath(info.filename)
            need(not p.is_absolute() and '..' not in p.parts and '\\' not in info.filename and (info.external_attr>>16)&0o170000 != 0o120000,'Unsafe archive path')
            if info.is_dir():continue
            target=dest.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))

def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    report=json.loads((E/'runtime.json').read_text());provenance=json.loads((E/'provenance.json').read_text())
    need(provenance['commit']=='65f24bf7bbc580b0733c9a7605ea4d69e49358cc' and str(provenance['run_id'])=='36343200218','Wrong source run')
    need(report['build']['candidate_core_sha256']=='32e38e8171b42f035cb82661a608dce04a5b3c7c84027081c033d7d9f80c0dc2','Wrong core')
    observer=load('r40ice_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('r40ice_paired',ROOT/'scripts/probe-never-overworld-paired-r12.py');nbt=observer.load_nbt(ROOT)
    phases={}
    for name in ('baseline_reverse','reverse'):
        p=report['phases'][name];need(p.get('pass') is True and p.get('fresh_verified') is True and p['exit_code']==0,'Unsuccessful phase')
        archive=E/(name+'-saved-regions.zip');dest=WORK/name;extract(archive,dest)
        coords=[(r['chunk_x'],r['chunk_z']) for r in p['observed']['chunks']]
        phases[name]=paired.saved_volume(observer,nbt,dest/'world/dimensions/minecraft/overworld/region',coords,{'normal_stop':True,'exit_code':0})
    proof={}
    for p in (E/'proof-reverse').glob('*.json'):
        r=json.loads(p.read_text());key=(r['chunk_x'],r['chunk_z'])
        if key not in phases['reverse'].roots:continue
        need(key not in proof,'Duplicate proof');proof[key]=decode(p.parent/r['witness_file'])
    need(len(proof)==54,'Incomplete witnesses')
    aquatic={'minecraft:water','minecraft:bubble_column','minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass'}
    air={'minecraft:air','minecraft:cave_air','minecraft:void_air'}
    before,after=phases['baseline_reverse'],phases['reverse'];counts=collections.Counter();categories=collections.Counter();by_chunk=collections.Counter();rows=[];filled=0
    for cx,cz in sorted(before.roots):
        witness=proof[(cx,cz)];cells=witness[6];writes=witness[9]
        for sy in range(-32,32):
            a=before.section((cx,sy,cz));b=after.section((cx,sy,cz));need(len(a)==len(b)==4096,'Incomplete saved section')
            for i,(old,new) in enumerate(zip(a,b)):
                if old==new:continue
                y=sy*16+(i>>8);x=i&15;z=(i>>4)&15;pos=[cx*16+x,y,cz*16+z]
                local=((y+511)<<8)|(z<<4)|x
                if old['Name'] in air and new['Name']=='minecraft:water' and new.get('Properties',{}).get('level')=='0' and -511<=y<=128:
                    need(local in writes,'Unlogged water write');filled+=1;continue
                counts[old['Name']+' -> '+new['Name']]+=1;by_chunk[f'{cx},{cz}']+=1
                code=cells[(y+511)*2304+(z+16)*48+x+16] if -511<=y<=128 else None
                new_code=AIR if new['Name'] in air else WATER if new['Name'] in aquatic else LAVA if new['Name']=='minecraft:lava' else SOLID
                evidence='outside_vertical_witness' if code is None else ('classified_before_write' if code==new_code else 'protected' if code==PROTECTED else 'category_changed_after_capture')
                categories[evidence]+=1
                rows.append({'position':pos,'baseline_reverse':old,'candidate_reverse':new,'candidate_prewrite_category':code,'candidate_final_category':new_code,'was_water_write':local in writes if -511<=y<=128 else False,'evidence':evidence})
    need(filled==7020,'Unexpected retained fill count')
    metadata={}
    for text in by_chunk:
        key=tuple(map(int,text.split(',')));metadata[text]={}
        for phase,volume in phases.items():
            root=volume.roots[key];structures=root.get('structures',{})
            payload=json.dumps(structures,sort_keys=True,separators=(',',':'))
            metadata[text][phase]={'structure_keys':list(structures),'starts':structures.get('starts',{}),'references':structures.get('References',structures.get('references',{})),'structure_sha256':hashlib.sha256(payload.encode()).hexdigest()}
    result={'source_run':36343200218,'source_core':report['build']['candidate_core_sha256'],'runtime_sha256':hashlib.sha256((E/'runtime.json').read_bytes()).hexdigest(),
        'read_only':True,'production_accepted':False,'original_gate_pass':report['bounded_integration_pass'],
        'air_to_water':filled,'unexpected_count':len(rows),'unexpected_by_chunk':dict(by_chunk),'unexpected_transitions':dict(counts),'witness_categories':dict(categories),
        'y_range':[min(r['position'][1] for r in rows),max(r['position'][1] for r in rows)] if rows else None,
        'nonwater_positions_in_write_bitmap':sum(r['was_water_write'] for r in rows),
        'rows':rows,'structure_metadata':metadata,
        'limitations':'Pre-write witness records AIR/SOLID/etc, not exact ice id or air subtype. Matching categories does not rule out indirect scheduling changes or establish equality of the complete pre-LIGHT worlds. Not permission to ignore these differences.'}
    (OUT/'ice-differences.json').write_text(json.dumps(result,indent=2)+'\n')
    summary={k:v for k,v in result.items() if k not in ('rows','structure_metadata')};summary['first_examples']=rows[:5]
    summary['structures']={text:{phase:{'start_ids':list(data['starts']),'reference_ids':list(data['references']),'hash':data['structure_sha256']} for phase,data in item.items()} for text,item in metadata.items()}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R40_ICE_REVIEW '+json.dumps(summary,separators=(',',':')),flush=True)
if __name__=='__main__':main()
