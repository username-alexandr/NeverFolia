#!/usr/bin/env python3
"""Read-only paired FIELD-R12 observation after normal server stops.

Runs baseline and candidate in DIFFERENT fresh folders with the same seed/packs.
Never repairs regions, edits locks, fills blocks, places synthetic structures,
or interprets connected wood as individual tree identities.
"""
from __future__ import annotations
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import shutil
import time
import zipfile

BASE_SHA = '32c6df3029fca001fd3602012e446a901f80eb2f'
BASE_JAR_SHA = 'dfdbcffce9d4404bbb610828eb804db622ab410f94b37344293ce94d2349ce11'
SEED = -2996952393010080672
MINE_TARGETS = ('minecraft:mineshaft', 'neverfolia:collapsed_mine')
DIMENSIONS = ('minecraft:overworld', 'minecraft:the_nether')
KEY = 'neverfolia:dry_mines_r12'
KINDS = ('coal', 'iron', 'copper', 'gold', 'redstone', 'lapis', 'diamond', 'emerald')
ORE = {f'minecraft:{prefix}{kind}_ore': kind for kind in KINDS for prefix in ('','deepslate_')}
ORE.update({'minecraft:raw_iron_block':'iron','minecraft:raw_copper_block':'copper'})


def require(ok, message):
    if not ok: raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'missing module: '+str(path))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def box_values(value):
    value = value.get('$int_array') if isinstance(value, dict) else value
    require(isinstance(value, (list,tuple)) and len(value)==6 and all(type(x) is int for x in value)
            and all(value[i]<=value[i+3] for i in range(3))
            and -512<=value[1]<=value[4]<=511
            and value[3]-value[0]<=256 and value[5]-value[2]<=256, 'invalid mine piece')
    return tuple(value)


def intersects(box, point, margin=0):
    x,z = point
    return box[0]-margin <= x*16+15 and box[3]+margin >= x*16 and box[2]-margin <= z*16+15 and box[5]+margin >= z*16


def coverage(boxes, margin=1):
    require(isinstance(boxes, list) and 1<=len(boxes)<=4096, 'missing/unbounded mine pieces')
    result = set()
    for value in boxes:
        b=box_values(value)
        result.update((x,z) for x in range((b[0]-margin)//16,(b[3]+margin)//16+1)
                      for z in range((b[2]-margin)//16,(b[5]+margin)//16+1))
    require(1<=len(result)<=324, 'mine sample exceeds chunk cap')
    return result


def pdc_boxes(root):
    raw = root.get('ChunkBukkitValues', {}).get(KEY)
    if raw is None: return set()
    values = raw.get('$int_array') if isinstance(raw,dict) else raw
    require(isinstance(values,list) and all(type(v) is int for v in values)
            and len(values)>=2 and values[0]==1 and 1<=values[1]<=4096
            and len(values)==2+6*values[1], 'invalid persisted dry mine metadata')
    return {box_values(values[i:i+6]) for i in range(2,len(values),6)}


def saved_volume(observer, nbt, region, chunks, phase):
    require(phase.get('normal_stop') is True and type(phase.get('exit_code')) is int
            and phase['exit_code']==0, 'no NBT reads before a normal stop')
    selected = [tuple(p) for p in chunks]
    require(len(selected)==len(set(selected)) and 1<=len(selected)<=1500, 'invalid saved sample')
    roots={p:nbt.read_chunk_nbt(region,*p) for p in selected}
    for p,doc in roots.items():
        require(type(doc.get('xPos')) is int and type(doc.get('zPos')) is int
                and (doc['xPos'],doc['zPos'])==p and doc.get('Status')=='minecraft:full', 'missing/non-FULL saved chunk '+str(p))
        sections=doc.get('sections')
        require(isinstance(sections,list), 'missing saved section table')
        by_y={s.get('Y'):s for s in sections if isinstance(s,dict)}
        require(len(by_y)==len(sections), 'duplicate saved sections')
        # Do not turn a truncated/missing generated section into assumed air.
        require(all(y in by_y and 'block_states' in by_y[y] for y in range(-32,32)), 'incomplete Overworld block-state sections')
    return observer.Volume(roots)


def mine_evidence(volume, area, require_metadata):
    start=volume.roots[tuple(area['start_chunk'])]
    raw=start.get('structures',{}).get('starts',{}).get(area['target'])
    require(isinstance(raw,dict) and raw.get('id')==area['target'], 'saved mine start missing')
    pieces=[box_values(child.get('BB')) for child in raw.get('Children',[])]
    require(bool(pieces), 'mine has no final saved pieces')
    require(coverage(list(pieces))<=set(volume.roots), 'mine extends beyond verified chunks')
    if require_metadata:
        for p,root in volume.roots.items():
            needed={b for b in pieces if intersects(b,p,1)}
            require(needed<=pdc_boxes(root), f'mine geometry missing from owner chunk {p}')
    cells=set()
    for b in pieces:
        require(b[4]<=127, 'mine reaches ocean surface; separate acceptance required')
        for x in range(b[0],b[3]+1):
            for z in range(b[2],b[5]+1):
                cells.update((x,y,z) for y in range(b[1],b[4]+1))
    require(len(cells)<=1000000, 'unbounded mine interior')
    counts=Counter(); findings=[]
    for pos in sorted(cells):
        state=volume.at(*pos); require(state is not None, 'unknown mine cell')
        name=state['Name']; counts['checked_cells']+=1
        if name in ('minecraft:water','minecraft:lava') or state.get('Properties',{}).get('waterlogged')=='true':
            counts['fluid_cells']+=1
            if len(findings)<30: findings.append({'position':list(pos),'state':state})
        if name in ('minecraft:air','minecraft:cave_air'): counts['air_cells']+=1
        if name.endswith('rail'): counts['rails']+=1
    return {'target':area['target'],'piece_count':len(pieces), 'counts':dict(counts),
            'fluid_examples':findings, 'metadata_checked':require_metadata, 'final_boxes':[list(b) for b in pieces]}


def resources(volume):
    result={}
    for key, section in volume.sections.items():
        if not any(s.get('Name') in ORE for s in section['block_states']['palette']): continue
        cx,sy,cz=key
        for i,state in enumerate(volume.section(key)):
            kind=ORE.get(state['Name'])
            if kind:
                result[(cx*16+(i&15),sy*16+(i>>8),cz*16+((i>>4)&15))]=kind
    return result


def compare_ore(before, after):
    old=Counter(before.values()); new=Counter(after.values())
    additions=[list(p) for p,k in after.items() if before.get(p)!=k]
    total=len(before); ratio=len(after)/total if total else None
    # One sampled comparison, not a new mask calibration. Exact native mask
    # tests remain mandatory. Preserve additions as diagnostics instead of
    # quietly excluding them from the ratio.
    return {'baseline_blocks':total,'candidate_blocks':len(after),'retained_ratio':ratio,
            'baseline_by_kind':dict(old),'candidate_by_kind':dict(new),
            'new_or_retyped_positions':len(additions),'examples':additions[:30],
            'pass':total>=200 and not additions and 0.40<=ratio<=0.60}


def ore_delta(before, after):
    """Every changed resource coordinate, including equal-count rerolls.

    Below -64 is reported separately because the baseline has native deep
    geology and upper vanilla FEATURES ores. Neither band is exempted.
    """
    changed=[]; bands=Counter(); edges=Counter()
    for point in sorted(before.keys() | after.keys()):
        old, new = before.get(point), after.get(point)
        if old == new: continue
        changed.append({'position':list(point),'before':old,'after':new})
        bands['below_minus64' if point[1] < -64 else 'at_or_above_minus64'] += 1
        edges['chunk_face' if (point[0] & 15) in (0,15) or (point[2] & 15) in (0,15) else 'chunk_interior'] += 1
    return {'before_blocks':len(before),'after_blocks':len(after),
            'changed_positions':len(changed),'by_height':dict(bands),
            'by_chunk_location':dict(edges),'changes':changed}


def plan_signature(areas):
    require(isinstance(areas,list) and len(areas)==5, 'expected three forests and two mine areas')
    keys=[(a['kind'],a['target']) for a in areas]
    require(len(set(keys))==5 and sum(k=='forest' for k,t in keys)==3
            and {t for k,t in keys if k=='mine'}==set(MINE_TARGETS), 'invalid paired area selection')
    normalized=[]
    for area in areas:
        chunks=[tuple(p) for p in area['chunks']]
        require(chunks and len(chunks)==len(set(chunks))
                and all(len(p)==2 and all(type(v) is int for v in p) for p in chunks), 'invalid paired chunk coverage')
        normalized.append({'kind':area['kind'],'target':area['target'],
            'located_xz':list(area['located_xz']), 'chunks':sorted(chunks),
            'start_chunk':list(area.get('start_chunk',[])),
            'boxes':sorted(box_values(b) for b in area.get('initial_boxes',[]))})
    return json.dumps(normalized, sort_keys=True, separators=(',',':'))


def controlled_checks(before, repeat, after, old, repeated, new):
    """A same-binary control diagnoses nondeterminism, never excuses it."""
    phases=('initial','complete','restart')
    runs=(before,repeat,after)
    lifecycle=all(tuple(p['name'] for p in r['phases'])==phases
        and all(p.get('normal_stop') is True and type(p.get('exit_code')) is int and p['exit_code']==0
                for p in r['phases']) for r in runs)
    matched=(lifecycle and before['jar_sha256']==repeat['jar_sha256']==BASE_JAR_SHA
        and all(r['seed']==SEED and r['pack_sha256']==before['pack_sha256'] for r in runs)
        and all(plan_signature(r['areas'])==plan_signature(before['areas']) for r in runs)
        and bool(before.get('requests'))
        and before['requests']==repeat['requests']==after['requests'])
    repeat_diff=ore_delta(old,repeated)
    stable=matched and len(old)>=200 and repeat_diff['changed_positions']==0
    transitions=all(len(r.get('ore_transitions',[]))==2
        and all(d.get('changed_positions')==0 for d in r['ore_transitions']) for r in runs)
    return {'execution_protocol_match':matched,
            'baseline_repeatability':{**repeat_diff,'same_binary':before['jar_sha256']==repeat['jar_sha256'],
                                     'pass':stable},
            'ore_phase_stability':transitions,
            'candidate_vs_repeated_baseline':compare_ore(repeated,new)}


def controlled_gate(report):
    return (report.get('ore',{}).get('pass') is True
        and report.get('candidate_vs_repeated_baseline',{}).get('pass') is True
        and report.get('execution_protocol_match') is True
        and report.get('baseline_repeatability',{}).get('pass') is True
        and report.get('ore_phase_stability') is True
        and report.get('dry_mines_pass') is True
        and report.get('tree_observation',{}).get('reduced_in_sample') is True)


def make_server(observer):
    class Server(observer.Server):
        def load_dimension(self, chunks, dimension, dwell=0):
            require(dimension in DIMENSIONS, 'invalid dimension')
            selected=sorted(set(map(tuple,chunks)))
            require(1<=len(selected)<=324, 'unbounded runtime sample')
            for offset in range(0,len(selected),32):
                batch=selected[offset:offset+32]; start=len(self.text()); probes={}
                for x,z in batch:
                    self.send(f'execute in {dimension} run forceload add {x*16} {z*16}')
                    self.token+=1; probes[f'R12_LOADED_{self.token}_{x}_{z}']=(x,z)
                pending=set(probes); end=time.monotonic()+240
                while pending and time.monotonic()<end:
                    for token in sorted(pending):
                        x,z=probes[token]
                        self.send(f'execute in {dimension} if loaded {x*16} 0 {z*16} run say {token}')
                    time.sleep(1); text=self.text()[start:]
                    require(not re.search(self.COMMAND_ERROR,text), 'chunk-load command failed: '+text[-1000:])
                    pending={t for t in pending if not re.search(self.marker_pattern(t),text)}
                    require(self.p.poll() is None, 'server exited during chunk loading')
                require(not pending, 'chunk load did not complete')
                if dwell: time.sleep(dwell) # Forceloaded mine chunks receive ordinary fluid ticks.
                for x,z in batch: self.send(f'execute in {dimension} run forceload remove {x*16} {z*16}')
            print('LOADED, not saved-verified:',dimension,len(selected),flush=True)
    return Server


def generate(root, observer, nbt, jar, packs, out, label, source_sha, plan=None):
    work=root/'.work'/('field-r12-paired-'+label)
    work.mkdir(parents=True,exist_ok=False)
    installed=work/'world/datapacks'; installed.mkdir(parents=True)
    hashes={name:observer.sha(path) for name,path in packs.items()}
    for name,path in packs.items(): shutil.copyfile(path,installed/name)
    (work/'eula.txt').write_text('eula=true\n') # CI-only disposable world.
    (work/'server.properties').write_text(f'level-name=world\nlevel-seed={SEED}\n'
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n'
        'online-mode=false\nenforce-secure-profile=false\nserver-ip=127.0.0.1\nserver-port=25596\n'
        'view-distance=2\nsimulation-distance=2\nspawn-protection=0\nenable-status=false\npause-when-empty-seconds=-1\n')
    region=work/'world/dimensions/minecraft/overworld/region'
    evidence={'label':label,'source_sha':source_sha,'seed':SEED,'jar_sha256':observer.sha(jar),
              'pack_sha256':hashes,'phases':[], 'areas':[], 'requests':[], 'ore_transitions':[]}
    observer.write_json(out/(label+'-plan.json'),evidence)
    Server=make_server(observer)
    def phase(name, action):
        require(observer.sha(jar)==evidence['jar_sha256'] and all(observer.sha(installed/n)==h for n,h in hashes.items()),'binary/pack changed')
        item={'name':name,'normal_stop':False,'exit_code':None}; evidence['phases'].append(item)
        server=Server(jar,work,out/(label+'-'+name+'.log'))
        try:
            server.wait(r'Done \(',timeout=300); server.disable_random_ticks(); action(server)
            item['exit_code']=server.stop(); item['normal_stop']=type(item['exit_code']) is int and item['exit_code']==0
            require(item['normal_stop'], 'nonzero server stop')
        except Exception as ex:
            item['error']=f'{type(ex).__name__}: {ex}'; raise
        finally:
            server.close(); observer.write_json(out/(label+'-plan.json'),evidence)
        return item
    def locate(server, kind, target, x, z):
        result=server.locate(kind,target,x,z)
        evidence['requests'].append({'phase':evidence['phases'][-1]['name'],
            'operation':'locate','kind':kind,'target':target,'origin':[x,z], 'result':list(result)})
        return result
    def load_area(server, chunks, dimension, dwell=0):
        selected=[list(p) for p in sorted(set(map(tuple,chunks)))]
        evidence['requests'].append({'phase':evidence['phases'][-1]['name'],
            'operation':'load','dimension':dimension,'chunks':selected,'dwell':dwell})
        server.load_dimension(selected,dimension,dwell)
    def census(item):
        roots={}
        for area in evidence['areas']:
            if area['kind']=='forest':
                roots.update(saved_volume(observer,nbt,region,area['chunks'],item).roots)
        found=resources(observer.Volume(roots))
        name=f"ore-census-{label}-{item['name']}.json"
        observer.write_json(out/name,{'schema':1,'seed':SEED,'label':label,'phase':item['name'],
            'source_sha':source_sha,'jar_sha256':evidence['jar_sha256'],'pack_sha256':hashes,
            'records':[[*pos,kind] for pos,kind in sorted(found.items())]})
        item['ore_census_file']=name; item['ore_census_sha256']=observer.sha(out/name)
        return found
    def transition(name, previous, current):
        difference=ore_delta(previous,current)
        filename=f'ore-transition-{label}-{name}.json'
        observer.write_json(out/filename,difference)
        evidence['ore_transitions'].append({k:v for k,v in difference.items() if k!='changes'}
            | {'file':filename,'sha256':observer.sha(out/filename)})

    initials=[]
    def initial(server):
        for target,origin in zip(observer.FORESTS,((0,0),(12000,0),(-12000,0))):
            x,z=locate(server,'biome',target,*origin); cx,cz=x//16,z//16
            chunks=[(a,b) for b in range(cz-2,cz+3) for a in range(cx-2,cx+3)]
            load_area(server,chunks,DIMENSIONS[0])
            evidence['areas'].append({'kind':'forest','target':target,'located_xz':[x,z],'chunks':chunks})
        for target in MINE_TARGETS:
            x,z=locate(server,'structure',target,8192,8192); cx,cz=x//16,z//16
            chunks=[(a,b) for b in range(cz-2,cz+3) for a in range(cx-2,cx+3)]
            load_area(server,chunks,DIMENSIONS[0]); initials.append((target,x,z,chunks))
    first=phase('initial',initial)
    for area in evidence['areas']: saved_volume(observer,nbt,region,area['chunks'],first)
    for target,x,z,chunks in initials:
        volume=saved_volume(observer,nbt,region,chunks,first); found=[]
        for point,doc in volume.roots.items():
            raw=doc.get('structures',{}).get('starts',{}).get(target)
            if isinstance(raw,dict) and raw.get('id')==target:
                pieces=[box_values(c.get('BB')) for c in raw.get('Children',[])]
                found.append(((point[0]-x//16)**2+(point[1]-z//16)**2,point,pieces))
        require(bool(found), 'located mine not saved: '+target)
        _,point,pieces=min(found)
        evidence['areas'].append({'kind':'mine','target':target,'located_xz':[x,z],
            'start_chunk':list(point),'initial_boxes':[list(p) for p in pieces],
            'chunks':[list(p) for p in sorted(coverage(list(pieces),2))]})
    observer.write_json(out/(label+'-plan.json'),evidence)
    # Locate and initial mine coverage must be reproduced, not bypassed by a
    # supplied plan. A changed selection fails instead of silently moving areas.
    if plan is not None:
        require(plan_signature(evidence['areas'])==plan_signature(plan), 'replayed area selection differs from baseline')
    initial_ores=census(first)
    def complete(server):
        for area in evidence['areas']:
            load_area(server,area['chunks'],DIMENSIONS[0],5 if area['kind']=='mine' else 0)
        load_area(server,[(x,z) for x in range(-196,-193) for z in range(-394,-391)],DIMENSIONS[1])
    second=phase('complete',complete)
    complete_ores=census(second)
    transition('initial-to-complete',initial_ores,complete_ores)
    # All roles, including the unchanged-binary control, use identical phases.
    second=phase('restart',complete)
    final_ores=census(second)
    transition('complete-to-restart',complete_ores,final_ores)
    result=[]; forest_roots={}
    for area in evidence['areas']:
        volume=saved_volume(observer,nbt,region,area['chunks'],second)
        if area['kind']=='mine': result.append(mine_evidence(volume,area,label=='candidate'))
        else:
            result.append({'target':area['target'],**observer.observed_components(volume)})
            forest_roots.update(volume.roots)
    nether=work/'world/dimensions/minecraft/the_nether/region'
    roofs=0
    for x in range(-196,-193):
        for z in range(-394,-391):
            doc=nbt.read_chunk_nbt(nether,x,z)
            require(doc.get('Status')=='minecraft:full' and (doc.get('xPos'),doc.get('zPos'))==(x,z),'Nether not FULL')
            sections={s['Y']:s for s in doc['sections'] if 'block_states' in s}
            require(32 in sections,'Nether roof section missing')
            states=observer.unpack_section(sections[32])
            require(all(s['Name']=='minecraft:bedrock' for s in states[:256]),'Nether roof512 mismatch')
            require(all(s['Name'] in observer.AIR for s in states[256:]),'non-air above Nether roof')
            roofs+=256
    evidence['observations']=result; evidence['nether_roof_cells']=roofs
    observer.write_json(out/(label+'-plan.json'),evidence)
    return evidence,final_ores


def package(out, jar, packs, report, source_sha, run_id, observer):
    require(report.get('paired_gate_pass') is True and report.get('production_ready') is False, 'candidate not eligible for manual test package')
    require(controlled_gate(report), 'missing or failed controlled comparisons')
    require(report.get('source_sha')==source_sha and observer.sha(jar)==report.get('candidate_jar_sha256'), 'bundle source/JAR mismatch')
    require(set(packs)=={'NeverOverworld.zip','NeverNether.zip'} and all(observer.sha(p)==report.get('pack_sha256',{}).get(n) for n,p in packs.items()), 'bundle pack mismatch')
    smoke=(out/'build-smoke.log').read_text()
    for marker in ('PASS FieldR12Smoke checks=', 'PASS TreePreservationSmoke checks=', 'PASS NeverNetherFieldCleanupR15Smoke checks=', 'BUILD SUCCESSFUL'):
        require(marker in smoke, 'missing native acceptance: '+marker)
    name='NeverFolia-FIELD-R12-TEST-'+source_sha[:7]+'.zip'; dest=out/name
    payload={'server.jar':jar.read_bytes()}
    for n,p in packs.items(): payload['world/datapacks/'+n]=p.read_bytes()
    payload['server.properties']=(f'level-name=world\nlevel-seed={SEED}\n'
        'initial-enabled-packs=vanilla,file/NeverOverworld.zip,file/NeverNether.zip\n').encode()
    for p in out.iterdir():
        if p.suffix in ('.json','.log','.txt') and p.is_file(): payload['evidence/'+p.name]=p.read_bytes()
    payload['README-RU.txt']=('FIELD-R12: тестовый комплект для НОВОГО мира, Java 25.\n'
        'Включены NeverOverworld и NeverNether; NeverEnd не включён.\n'
        'Оба датапака уже находятся в world/datapacks; установите до первого запуска.\n'
        'Запуск: java -Xms1G -Xmx4G -jar server.jar --nogui\n'
        'Подтверждайте EULA только при согласии. Старый мир, level.dat и lock-файлы не переносите.\n'
        'Новые стоящие деревья проверяются до размещения; поваленные разрешены в воде.\n'
        'Оставшаяся руда уменьшена примерно вдвое; шахты защищены по частям структуры.\n'
        'Существующие чанки не восстанавливаются. Production-ready=false.\n'
        'Один seed и ограниченная выборка не подтверждают все биомы и внешний вид шахт/деревень.\n').encode()
    payload['BUILD-INFO.json']=(json.dumps({'source_sha':source_sha,'workflow_run':run_id,'production_ready':False,
        'paired_gate_pass':True,'new_world_required':True,'nether_included':True,
        'natural_fallen_frequency_accepted':False,'village_visual_review_required':True},indent=2)+'\n').encode()
    import hashlib
    payload['SHA256SUMS.txt']=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in sorted(payload.items())).encode()
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for n,b in sorted(payload.items()): archive.writestr(n,b)
    with zipfile.ZipFile(dest) as archive: require(archive.testzip() is None,'output ZIP damaged')
    return {'path':name,'sha256':observer.sha(dest),'production_ready':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('jar','baseline-jar','overworld','nether','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-sha',required=True); p.add_argument('--run-id',type=int,required=True)
    a=p.parse_args(); require(re.fullmatch('[0-9a-f]{40}',a.source_sha),'full source SHA required')
    root=Path(__file__).resolve().parents[1]
    observer=load('r12_observer',root/'scripts/probe-never-overworld-trees-villages-r1.py'); nbt=observer.load_nbt(root)
    require(observer.sha(a.baseline_jar)==BASE_JAR_SHA,'wrong baseline JAR')
    out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    require(not (out/'paired-r12.json').exists(),'existing evidence must not be overwritten')
    packs={'NeverOverworld.zip':a.overworld.resolve(),'NeverNether.zip':a.nether.resolve()}
    report={'schema':2,'seed':SEED,'source_sha':a.source_sha,'baseline_sha':BASE_SHA,'production_ready':False,
            'paired_gate_pass':False,'new_world_required':True}
    try:
        before,old=generate(root,observer,nbt,a.baseline_jar.resolve(),packs,out,'baseline',BASE_SHA)
        repeated,again=generate(root,observer,nbt,a.baseline_jar.resolve(),packs,out,'baseline-repeat',BASE_SHA,before['areas'])
        after,new=generate(root,observer,nbt,a.jar.resolve(),packs,out,'candidate',a.source_sha,before['areas'])
        controls=controlled_checks(before,repeated,after,old,again,new)
        # Full censuses and every delta remain diagnostic even on failure.
        observer.write_json(out/'ore-repeatability-r12.json',controls['baseline_repeatability'])
        for label,ref in (('baseline',old),('baseline-repeat',again)):
            observer.write_json(out/f'ore-candidate-vs-{label}-r12.json',ore_delta(ref,new))
        report.update(controls)
        report['baseline_repeatability']={k:v for k,v in controls['baseline_repeatability'].items() if k!='changes'}

        report['candidate_jar_sha256']=after['jar_sha256']
        report['baseline_jar_sha256']=before['jar_sha256']
        report['pack_sha256']=after['pack_sha256']
        report['ore']=compare_ore(old,new)
        mines=[x for x in after['observations'] if 'fluid_examples' in x]
        report['mines']=mines
        report['dry_mines_pass']=len(mines)==len(MINE_TARGETS) and all(x['counts'].get('fluid_cells',0)==0 and x['counts'].get('air_cells',0)>=20 for x in mines)
        oldtrees=sum(x.get('counts',{}).get('wholly_submerged_components',0) for x in before['observations'])
        newtrees=sum(x.get('counts',{}).get('wholly_submerged_components',0) for x in after['observations'])
        report['tree_observation']={'baseline_submerged_components':oldtrees,'candidate_submerged_components':newtrees,
            'reduced_in_sample':oldtrees>0 and newtrees<oldtrees,'individual_tree_identity_proven':False}
        report['limitations']=['One seed; paired three 5x5 forest areas and two mine variants.',
            'Baseline is independently repeated; asynchronous completion timing is not claimed identical. Any differing ore positions still reject acceptance.',
            'Tree components are observations, not before-placement decisions or identities. Native feature tests are separate.',
            'Nine Nether chunks check joint startup, FULL saving and roof/padding only; not a new full Nether acceptance.',
            'Mine rock-shell aesthetics and village visuals require in-game review.']
        report['paired_gate_pass']=controlled_gate(report)
        require(report['paired_gate_pass'],'paired observation rejected; see report, no accepted bundle produced')
    except Exception as error:
        report['error']=f'{type(error).__name__}: {error}'; raise
    finally:
        observer.write_json(out/'paired-r12.json',report)
    bundle=package(out,a.jar.resolve(),packs,report,a.source_sha,a.run_id,observer)
    observer.write_json(out/'paired-r12-bundle.json',bundle)
    print(json.dumps({'report':report,'bundle':bundle},indent=2))

if __name__=='__main__': main()
