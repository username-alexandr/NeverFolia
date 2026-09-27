#!/usr/bin/env python3
"""Read-only classification of completed R397 CI saves, not a new generation run."""
from pathlib import Path,PurePosixPath
import collections,hashlib,importlib.util,json,zipfile
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'evidence';OUT=ROOT/'review398';WORK=ROOT/'.work/r398-review'

def need(ok,message):
    if not ok:raise ValueError(message)

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def extract(archive,dest):
    dest.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        need(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),'Invalid saved archive')
        for info in z.infolist():
            p=PurePosixPath(info.filename)
            need(not p.is_absolute() and '..' not in p.parts and '\\' not in info.filename,'Unsafe archive member')
            need((info.external_attr>>16)&0o170000 != 0o120000,'Symlink member')
            if info.is_dir():continue
            target=dest.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))

def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir(parents=True,exist_ok=False)
    report=json.loads((E/'r397-controls.json').read_text())
    need(report.get('diagnostic_complete') is True,'Control matrix did not finish')
    need(report['inputs']['baseline_core']=='411f628603ae531216c173fde1dbd8c702effb170889f72e5f2c0f1af81b6a32','Wrong baseline')
    need(report['inputs']['overworld']=='a5fb99cd0b15efc2ec78a1f155c763112f3e3d2669c1519aae69e468de7902be','Wrong pack')
    observer=load('r398_observer',ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
    paired=load('r398_paired',ROOT/'scripts/probe-never-overworld-paired-r12.py');nbt=observer.load_nbt(ROOT)
    volumes={};inputs={}
    for name in ('baseline','baseline_repeat','baseline_reverse','candidate_off','candidate','restart','reverse'):
        archive=E/(name+'-saved-regions.zip');inputs[archive.name]=hashlib.sha256(archive.read_bytes()).hexdigest()
        folder=WORK/name;extract(archive,folder)
        phase=report['phases'][name]
        need(phase.get('pass') is True and phase.get('exit_code')==0 and phase.get('fresh_report_verified') is True,'Unverified phase')
        coords=[(r['chunk_x'],r['chunk_z']) for r in phase['observed']['chunks']]
        volumes[name]=paired.saved_volume(observer,nbt,folder/'world/dimensions/minecraft/overworld/region',coords,{'normal_stop':True,'exit_code':0})
    pairs={'baseline_repeat':('baseline','baseline_repeat'),'baseline_reverse':('baseline','baseline_reverse'),'candidate_disabled':('baseline','candidate_off'),'forward_effect':('baseline','candidate'),'reverse_effect':('baseline_reverse','reverse'),'candidate_reverse':('candidate','reverse'),'candidate_restart':('candidate','restart')}
    result={'read_only':True,'production_accepted':False,'source_report_sha256':hashlib.sha256((E/'r397-controls.json').read_bytes()).hexdigest(),'saved_archives_sha256':inputs,'comparisons':{}}
    air={'minecraft:air','minecraft:cave_air','minecraft:void_air'}
    for label,(left,right) in pairs.items():
        before=volumes[left];after=volumes[right];transitions=collections.Counter();chunks=collections.Counter();bad=collections.Counter();examples=[];bad_examples=[]
        hashes=report['phases'][left]['saved']['full_state_hashes'];other=report['phases'][right]['saved']['full_state_hashes']
        selected=[p for p in before.roots if hashes[f'{p[0]},{p[1]}']!=other[f'{p[0]},{p[1]}']]
        for cx,cz in sorted(selected):
            for sy in range(-32,32):
                a=before.section((cx,sy,cz));b=after.section((cx,sy,cz));need(len(a)==len(b)==4096,'Truncated section')
                for i,(old,new) in enumerate(zip(a,b)):
                    if old==new:continue
                    transition=old['Name']+' => '+new['Name'];transitions[transition]+=1;chunks[f'{cx},{cz}']+=1
                    entry={'position':[cx*16+(i&15),sy*16+(i>>8),cz*16+((i>>4)&15)],'before':old,'after':new}
                    if len(examples)<8:examples.append(entry)
                    accepted=old['Name'] in air and new['Name']=='minecraft:water' and new.get('Properties',{}).get('level','0')=='0' and -511<=entry['position'][1]<=128
                    if not accepted:
                        bad[transition]+=1
                        if len(bad_examples)<8:bad_examples.append(entry)
        result['comparisons'][label]={'changed_chunks':len(chunks),'changed_cells':sum(transitions.values()),'transitions':dict(transitions),'by_chunk':dict(chunks),'non_air_to_source_water_changes':sum(bad.values()),'non_air_to_source_water_transitions':dict(bad),'first_examples':examples,'first_non_air_to_water_examples':bad_examples}
    (OUT/'four-way-voxel-review.json').write_text(json.dumps(result,indent=2)+'\n')
    compact={label:{k:v for k,v in row.items() if k not in ('first_examples','first_non_air_to_water_examples','by_chunk')} for label,row in result['comparisons'].items()}
    print('R398_FOUR_WAY '+json.dumps(compact,separators=(',',':')))
    print('SOURCE_REPORT_SHA256',result['source_report_sha256'])

if __name__=='__main__':main()
