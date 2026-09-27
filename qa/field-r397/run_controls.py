#!/usr/bin/env python3
"""Seven isolated Java runs; preserves R395/R396 binaries and user worlds.
R395's original runner supplies launch/stop, plugin compilation and saved-region IO.
This wrapper adds fresh-result validation, complete state hashes and controls.
No gameplay acceptance is implied by successfully collecting diagnostic evidence.
"""
from pathlib import Path
import collections,contextlib,hashlib,importlib.util,json,sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'qa/field-r395'))
from control_contract import TARGETS, validate_observation, success_marker
REQUIRED={'baseline','baseline_repeat','baseline_reverse','candidate_off','candidate','restart','reverse'}
PAIRS={'baseline_repeat':('baseline','baseline_repeat'),'baseline_reverse':('baseline','baseline_reverse'),'candidate_disabled':('baseline','candidate_off'),'candidate_reverse':('candidate','reverse'),'candidate_restart':('candidate','restart')}
FIELDS=('water_hashes','block_state_hashes','full_state_hashes')

def need(ok,message):
    if not ok:raise ValueError(message)

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def encode_state(state,cache):
    need(isinstance(state,dict) and isinstance(state.get('Name'),str),'Missing saved state')
    props=state.get('Properties',{})
    need(isinstance(props,dict) and all(isinstance(k,str) and isinstance(v,str) for k,v in props.items()),'Invalid state properties')
    key=(state['Name'],tuple(sorted(props.items())))
    if key not in cache:
        raw=json.dumps(key,separators=(',',':'),ensure_ascii=True).encode('utf-8')
        cache[key]=len(raw).to_bytes(4,'big')+raw
    return cache[key]

def compare(phases):
    missing=sorted(REQUIRED-set(phases))
    failed=sorted(k for k in REQUIRED&set(phases) if phases[k].get('pass') is not True)
    report={'pass':False,'diagnostic_complete':not missing and not failed,'missing_phases':missing,'failed_phases':failed,'comparisons':{},'snapshot_vs_saved':{}}
    if missing or failed:return report
    keys={f'{x},{z}' for x,z in TARGETS}
    for name in sorted(REQUIRED):
        saved=phases[name]['saved']
        for field in FIELDS:
            need(set(saved.get(field,{}))==keys,'Incomplete hash coverage: '+name+' '+field)
        need(set(saved.get('chunk_block_counts',{}))==keys,'Incomplete census coverage')
    for label,(left,right) in PAIRS.items():
        a=phases[left]['saved'];b=phases[right]['saved']
        report['comparisons'][label]={field:sorted(k for k in keys if a[field][k]!=b[field][k]) for field in FIELDS}
    for name in sorted(REQUIRED):
        phase=phases[name];saved=phase['saved'];differences=[]
        for row in phase['observed']['chunks']:
            key=f"{row['chunk_x']},{row['chunk_z']}"
            water=row['water_sha256']!=saved['water_hashes'][key]
            census=collections.Counter(row['block_counts'])!=collections.Counter(saved['chunk_block_counts'][key])
            if water or census:differences.append({'chunk':key,'water_changed':water,'counts_changed':census})
        report['snapshot_vs_saved'][name]=differences
    report['pass']=not any(v for c in report['comparisons'].values() for v in c.values()) and not any(report['snapshot_vs_saved'].values())
    report['scope']='Exact Name/Properties hashes; full=-512..511, water/band=-511..128. No entities/block-entity NBT. Snapshot drift can reflect simulation and is not by itself a generation bug.'
    return report

def main():
    legacy=load(ROOT/'qa/field-r395/run_runtime.py','r397_legacy')
    original_persisted=legacy.persisted
    def persisted(folder,rows,name):
        saved=original_persisted(folder,rows,name)
        observer=legacy.load('r397_observer_'+name,ROOT/'scripts/probe-never-overworld-trees-villages-r1.py')
        paired=legacy.load('r397_paired_'+name,ROOT/'scripts/probe-never-overworld-paired-r12.py')
        volume=paired.saved_volume(observer,observer.load_nbt(ROOT),folder/'world/dimensions/minecraft/overworld/region',[(r['chunk_x'],r['chunk_z']) for r in rows],{'normal_stop':True,'exit_code':0})
        full_hashes={};band_hashes={};chunk_counts={};cache={}
        for row in rows:
            cx,cz=row['chunk_x'],row['chunk_z'];key=f'{cx},{cz}'
            full=hashlib.sha256();band=hashlib.sha256();counts=collections.Counter()
            for sy in range(-32,32):
                states=volume.section((cx,sy,cz));need(len(states)==4096,'Incomplete saved section')
                for i,state in enumerate(states):
                    raw=encode_state(state,cache);full.update(raw)
                    y=sy*16+(i>>8)
                    if -511<=y<=128:band.update(raw);counts[state['Name']]+=1
            need(sum(counts.values())==640*256,'Incomplete saved census')
            full_hashes[key]=full.hexdigest();band_hashes[key]=band.hexdigest();chunk_counts[key]=dict(counts)
        saved.update({'full_state_hashes':full_hashes,'block_state_hashes':band_hashes,'chunk_block_counts':chunk_counts})
        legacy.save(legacy.OUT/(name+'-saved.json'),saved)
        return saved
    legacy.persisted=persisted
    def phase(name,folder,jar,enabled,reverse=False):
        # A previous restart report is moved, never used as evidence for this Java process.
        previous=folder/'plugins/R395Qa/result.json'
        archive=legacy.OUT/(name+'-previous-result.json')
        if previous.exists() or previous.is_symlink():
            need(previous.is_file() and not previous.is_symlink(),'Unexpected old report type')
            need(not archive.exists(),'Previous evidence destination already exists')
            previous.rename(archive)
        with (legacy.OUT/(name+'-runner.log')).open('w') as log, contextlib.redirect_stdout(log):
            result=legacy.phase(name,folder,jar,enabled,reverse)
        try:
            need(previous.is_file() and not previous.is_symlink(),'No fresh result from current Java process')
            fresh=json.loads(previous.read_text())
            validate_observation(fresh,reverse)
            need(result.get('observed')==fresh,'Runner observation differs from fresh result')
            markers=[line for line in (legacy.OUT/(name+'.log')).read_text().splitlines() if 'R395 NATURAL QA' in line]
            need(len(markers)==1 and success_marker(markers[0]),'No unique current PASS marker')
            result['fresh_report_verified']=True
        except Exception as error:
            result['pass']=False;result['freshness_error']=repr(error)
        legacy.save(legacy.OUT/(name+'-phase.json'),result)
        print('R397_PHASE '+json.dumps({'name':name,'pass':result.get('pass'),'error':result.get('error'),'freshness_error':result.get('freshness_error'),'exit_code':result.get('exit_code')}),flush=True)
        return result
    build=json.loads((legacy.OUT/'build.json').read_text())
    need(legacy.sha(ROOT/'baseline/server.jar')==legacy.BASE,'Wrong baseline core')
    need(legacy.sha(ROOT/'candidate/server.jar')==build['candidate_core_sha256'],'Wrong candidate core')
    need(legacy.sha(ROOT/'candidate/NeverOverworld.zip')==legacy.PACK and legacy.sha(ROOT/'candidate/NeverNether.zip')==legacy.NETHER,'Wrong paired packs')
    plugin=legacy.prepare_plugin()
    report={'schema':1,'production_accepted':False,'core_changed_by_this_qa':False,'inputs':{'baseline_core':legacy.BASE,'candidate_core':build['candidate_core_sha256'],'overworld':legacy.PACK,'nether':legacy.NETHER},'phases':{}}
    for name,binary,enabled,reverse in (
        ('baseline',ROOT/'baseline/server.jar',False,False),
        ('baseline_repeat',ROOT/'baseline/server.jar',False,False),
        ('baseline_reverse',ROOT/'baseline/server.jar',False,True),
        ('candidate_off',ROOT/'candidate/server.jar',False,False),
        ('candidate',ROOT/'candidate/server.jar',True,False),
        ('reverse',ROOT/'candidate/server.jar',True,True)):
        folder=legacy.setup(name,plugin)
        report['phases'][name]=phase(name,folder,binary,enabled,reverse)
        if name=='candidate' and report['phases'][name].get('pass') is True:
            report['phases']['restart']=phase('restart',folder,binary,True,False)
        legacy.save(legacy.OUT/'r397-controls.json',report)
    report['controls']=compare(report['phases'])
    report['diagnostic_complete']=report['controls']['diagnostic_complete']
    added=report['phases'].get('candidate',{}).get('proof',{}).get('added_air_to_water',0)
    report['bounded_regression_pass']=report['controls']['pass'] and added>0
    legacy.save(legacy.OUT/'r397-controls.json',report)
    summary={k:v for k,v in report.items() if k!='phases'}
    summary['phase_status']={k:v.get('pass') for k,v in report['phases'].items()}
    summary['candidate_added_air_to_water']=added
    legacy.save(legacy.OUT/'r397-summary.json',summary)
    print('R397_RESULT '+json.dumps(summary,separators=(',',':')),flush=True)
    return 0 if report['bounded_regression_pass'] else 2

if __name__=='__main__':raise SystemExit(main())
